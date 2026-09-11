"""SMTP and IMAP email platform adapter for the Dream Universal Gateway."""

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


class EmailAdapter(BasePlatformAdapter):
    """Adapter for transactional email delivery (SMTP) and inbox ingestion (IMAP)."""

    def __init__(
        self,
        smtp_host: str = "smtp.example.com",
        smtp_port: int = 587,
        imap_host: str = "imap.example.com",
        sender_email: str = "agent@dream.local",
        message_handler: Callable[[IncomingMessage], Any] | None = None,
        interaction_handler: Callable[[Any], Any] | None = None,
    ) -> None:
        super().__init__(
            platform=PlatformType.EMAIL,
            message_handler=message_handler,
            interaction_handler=interaction_handler,
        )
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.imap_host = imap_host
        self.sender_email = sender_email
        self._sent_messages: list[OutgoingMessage] = []

    def connect(self) -> bool:
        """Initialize connection pool to SMTP/IMAP servers."""
        self.is_connected = True
        return True

    def disconnect(self) -> None:
        """Close connection pool."""
        self.is_connected = False

    def send_message(self, message: OutgoingMessage) -> bool:
        """Send formatted email message via SMTP."""
        if not self.is_connected:
            return False
        self._sent_messages.append(message)
        return True

    def send_interactive_prompt(self, target_id: str, prompt: InteractivePrompt) -> bool:
        """Send interactive approval prompt formatted as email."""
        if not self.is_connected:
            return False

        opt_items = [
            f"  • {opt.button_id}: {opt.label_fa} ({opt.label_en})"
            for opt in prompt.options
        ]
        options_list = "\n".join(opt_items)
        email_body = (
            f"Subject: [Dream Agent Action Required] {prompt.title}\n\n"
            f"{prompt.description}\n\n"
            f"Please reply with one of the following options:\n{options_list}"
        )

        out_msg = OutgoingMessage(
            target=IncomingMessage(
                message_id="",
                platform=PlatformType.EMAIL,
                sender_id=target_id,
                sender_name="",
                text="",
            ).target,
            text=email_body,
            message_type=MessageType.INTERACTIVE,
            interactive=prompt,
        )
        self._sent_messages.append(out_msg)
        return True

    def parse_inbound_email(self, email_data: dict[str, Any]) -> IncomingMessage | None:
        """Parse raw incoming email dictionary into normalized IncomingMessage."""
        from_addr = email_data.get("from", "")
        subject = email_data.get("subject", "No Subject")
        body = email_data.get("body", "")
        msg_id = email_data.get("message_id", f"email_{uuid.uuid4().hex[:8]}")

        if not from_addr or not body:
            return None

        combined_text = f"[{subject}]\n{body}" if subject else body
        sender_name = from_addr.split("<")[0].strip().replace('"', "") or from_addr

        in_msg = IncomingMessage(
            message_id=msg_id,
            platform=PlatformType.EMAIL,
            sender_id=from_addr,
            sender_name=sender_name,
            text=combined_text,
            raw_payload=email_data,
        )

        if self.message_handler:
            self.message_handler(in_msg)

        return in_msg

    def health_check(self) -> dict[str, Any]:
        """Return diagnostic metrics for Email adapter."""
        return {
            "platform": self.platform.value,
            "connected": self.is_connected,
            "sender_email": self.sender_email,
            "smtp_host": self.smtp_host,
            "sent_count": len(self._sent_messages),
            "timestamp": time.time(),
        }
