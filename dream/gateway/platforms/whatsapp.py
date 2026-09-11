"""WhatsApp Cloud API and Baileys adapter for the Dream Universal Gateway."""

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


class WhatsAppAdapter(BasePlatformAdapter):
    """Adapter for WhatsApp Business Cloud API & Webhook listeners."""

    def __init__(
        self,
        phone_number_id: str = "default_wa_phone_id",
        api_token: str = "",
        verify_token: str = "dream_verify_token",
        message_handler: Callable[[IncomingMessage], Any] | None = None,
        interaction_handler: Callable[[Any], Any] | None = None,
    ) -> None:
        super().__init__(
            platform=PlatformType.WHATSAPP,
            message_handler=message_handler,
            interaction_handler=interaction_handler,
        )
        self.phone_number_id = phone_number_id
        self.api_token = api_token
        self.verify_token = verify_token
        self._sent_messages: list[OutgoingMessage] = []

    def connect(self) -> bool:
        """Start webhook listener or verify token handshake."""
        self.is_connected = True
        return True

    def disconnect(self) -> None:
        """Shutdown webhook listener."""
        self.is_connected = False

    def send_message(self, message: OutgoingMessage) -> bool:
        """Send outbound WhatsApp message."""
        if not self.is_connected:
            return False
        self._sent_messages.append(message)
        return True

    def send_interactive_prompt(self, target_id: str, prompt: InteractivePrompt) -> bool:
        """Send WhatsApp interactive button prompt message."""
        if not self.is_connected:
            return False

        opt_items = [f"[{opt.button_id}] {opt.label_fa}" for opt in prompt.options[:3]]
        options_preview = "\n".join(opt_items)
        full_text = f"*{prompt.title}*\n{prompt.description}\n\n{options_preview}"

        out_msg = OutgoingMessage(
            target=IncomingMessage(
                message_id="",
                platform=PlatformType.WHATSAPP,
                sender_id=target_id,
                sender_name="",
                text="",
            ).target,
            text=full_text,
            message_type=MessageType.INTERACTIVE,
            interactive=prompt,
        )
        self._sent_messages.append(out_msg)
        return True

    def parse_webhook_payload(self, payload: dict[str, Any]) -> list[IncomingMessage]:
        """Parse incoming Meta WhatsApp Cloud webhook payload into IncomingMessage list."""
        messages = []
        entries = payload.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                contacts = {
                    c.get("wa_id"): c.get("profile", {}).get("name", "User")
                    for c in value.get("contacts", [])
                }
                raw_msgs = value.get("messages", [])
                for rm in raw_msgs:
                    from_id = rm.get("from", "")
                    sender_name = contacts.get(from_id, from_id)
                    msg_id = rm.get("id", f"wa_msg_{uuid.uuid4().hex[:6]}")
                    msg_type = rm.get("type", "text")

                    text = ""
                    if msg_type == "text":
                        text = rm.get("text", {}).get("body", "")
                    elif msg_type == "interactive":
                        btn_reply = rm.get("interactive", {}).get("button_reply", {})
                        text = btn_reply.get("id", "") or btn_reply.get("title", "")

                    if text:
                        in_msg = IncomingMessage(
                            message_id=msg_id,
                            platform=PlatformType.WHATSAPP,
                            sender_id=from_id,
                            sender_name=sender_name,
                            text=text,
                            raw_payload=rm,
                        )
                        messages.append(in_msg)
                        if self.message_handler:
                            self.message_handler(in_msg)

        return messages

    def health_check(self) -> dict[str, Any]:
        """Return diagnostic health metrics."""
        return {
            "platform": self.platform.value,
            "connected": self.is_connected,
            "phone_number_id": self.phone_number_id,
            "sent_count": len(self._sent_messages),
            "timestamp": time.time(),
        }
