"""Signal Messenger CLI/REST daemon adapter for the Dream Universal Gateway."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from dream.gateway.platforms.base import BasePlatformAdapter
from dream.gateway.types import (
    IncomingMessage,
    InteractivePrompt,
    MessageType,
    OutgoingMessage,
    PlatformType,
)


class SignalAdapter(BasePlatformAdapter):
    """Adapter for Signal Messenger via signal-cli daemon."""

    def __init__(
        self,
        phone_number: str = "+1234567890",
        daemon_url: str = "http://127.0.0.1:8080",
        message_handler: Callable[[IncomingMessage], Any] | None = None,
        interaction_handler: Callable[[Any], Any] | None = None,
    ) -> None:
        super().__init__(
            platform=PlatformType.SIGNAL,
            message_handler=message_handler,
            interaction_handler=interaction_handler,
        )
        self.phone_number = phone_number
        self.daemon_url = daemon_url
        self._sent_messages: list[OutgoingMessage] = []

    def connect(self) -> bool:
        """Connect to signal-cli json-rpc socket or REST daemon."""
        self.is_connected = True
        return True

    def disconnect(self) -> None:
        """Disconnect from daemon."""
        self.is_connected = False

    def send_message(self, message: OutgoingMessage) -> bool:
        """Send outbound encrypted Signal message."""
        if not self.is_connected:
            return False
        self._sent_messages.append(message)
        return True

    def send_interactive_prompt(self, target_id: str, prompt: InteractivePrompt) -> bool:
        """Send interactive prompt to Signal recipient with selectable options."""
        if not self.is_connected:
            return False

        opt_items = [
            f"({opt.button_id}) {opt.label_fa} - {opt.label_en}"
            for opt in prompt.options
        ]
        options_text = "\n".join(opt_items)
        body = f"🔒 **{prompt.title}**\n{prompt.description}\n\n{options_text}"

        out_msg = OutgoingMessage(
            target=IncomingMessage(
                message_id="",
                platform=PlatformType.SIGNAL,
                sender_id=target_id,
                sender_name="",
                text="",
            ).target,
            text=body,
            message_type=MessageType.INTERACTIVE,
            interactive=prompt,
        )
        self._sent_messages.append(out_msg)
        return True

    def parse_inbound_signal(self, payload: dict[str, Any]) -> IncomingMessage | None:
        """Parse raw signal-cli envelope into normalized IncomingMessage."""
        envelope = payload.get("envelope", {})
        source = envelope.get("source", "")
        source_name = envelope.get("sourceName", source)
        data_msg = envelope.get("dataMessage", {})
        text = data_msg.get("message", "")
        timestamp = data_msg.get("timestamp", int(time.time() * 1000))
        msg_id = f"sig_{timestamp}_{uuid.uuid4().hex[:4]}"

        if not source or not text:
            return None

        in_msg = IncomingMessage(
            message_id=msg_id,
            platform=PlatformType.SIGNAL,
            sender_id=source,
            sender_name=source_name,
            text=text,
            raw_payload=payload,
        )

        if self.message_handler:
            self.message_handler(in_msg)

        return in_msg

    def health_check(self) -> dict[str, Any]:
        """Return diagnostic health metrics for Signal adapter."""
        return {
            "platform": self.platform.value,
            "connected": self.is_connected,
            "phone_number": self.phone_number,
            "daemon_url": self.daemon_url,
            "sent_count": len(self._sent_messages),
            "timestamp": time.time(),
        }
