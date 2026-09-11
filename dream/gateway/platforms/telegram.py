"""Telegram platform adapter with inline keyboard approvals and voice message support."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.request import Request, urlopen

from dream.gateway.platforms.base import BasePlatformAdapter
from dream.gateway.types import (
    ButtonOption,
    IncomingMessage,
    InteractivePrompt,
    MessageType,
    OutgoingMessage,
    PlatformType,
)

logger = logging.getLogger(__name__)

MAX_TELEGRAM_MSG_LEN = 4000
POLL_TIMEOUT_SECS = 25


class TelegramAdapter(BasePlatformAdapter):
    """Adapter for Telegram Bot API with inline keyboards and long polling."""

    def __init__(
        self,
        bot_token: str,
        api_base_url: str = "https://api.telegram.org",
        message_handler: Callable[[IncomingMessage], Any] | None = None,
        interaction_handler: Callable[[Any], Any] | None = None,
    ) -> None:
        super().__init__(PlatformType.TELEGRAM, message_handler, interaction_handler)
        self.bot_token = bot_token
        self.api_base_url = api_base_url.rstrip("/")
        self._running = False
        self._poll_thread: threading.Thread | None = None
        self._last_update_id = 0

    def connect(self) -> bool:
        """Verify bot credentials and start background long-polling."""
        if not self.bot_token:
            logger.error("Telegram bot token is empty.")
            return False

        # Verify bot token via getMe
        res = self._api_call("getMe")
        if not res or not res.get("ok"):
            logger.error(f"Telegram getMe failed: {res}")
            return False

        bot_info = res.get("result", {})
        logger.info(f"Telegram connected as @{bot_info.get('username')}")

        self.is_connected = True
        self._running = True
        self._poll_thread = threading.Thread(
            target=self._polling_worker,
            name="TelegramPollWorker",
            daemon=True,
        )
        self._poll_thread.start()
        return True

    def disconnect(self) -> None:
        """Stop long-polling and disconnect."""
        self._running = False
        self.is_connected = False
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2.0)

    def send_message(self, message: OutgoingMessage) -> bool:
        """Format and transmit message to Telegram user/chat."""
        chat_id = message.target.recipient_id
        text = message.text

        # Split long messages into Telegram chunks
        chunks = self._chunk_text(text, MAX_TELEGRAM_MSG_LEN)
        success = True

        for i, chunk in enumerate(chunks):
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": chunk,
            }
            if message.reply_to_message_id and i == 0:
                payload["reply_to_message_id"] = message.reply_to_message_id

            # Attach inline keyboard on the final chunk if interactive prompt is present
            if message.interactive and i == len(chunks) - 1:
                keyboard = self._build_inline_keyboard(message.interactive.options)
                payload["reply_markup"] = json.dumps({"inline_keyboard": keyboard})

            res = self._api_call("sendMessage", payload)
            if not res or not res.get("ok"):
                success = False

        return success

    def send_interactive_prompt(self, target_id: str, prompt: InteractivePrompt) -> bool:
        """Send an inline interactive button prompt."""
        text = f"*{prompt.title}*\n\n{prompt.description}"
        keyboard = self._build_inline_keyboard(prompt.options)
        payload = {
            "chat_id": target_id,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": json.dumps({"inline_keyboard": keyboard}),
        }
        res = self._api_call("sendMessage", payload)
        return bool(res and res.get("ok"))

    def _build_inline_keyboard(self, options: list[ButtonOption]) -> list[list[dict[str, str]]]:
        """Convert button options into Telegram inline keyboard rows."""
        rows: list[list[dict[str, str]]] = []
        current_row: list[dict[str, str]] = []

        for opt in options:
            label = (
                f"{opt.label_fa} | {opt.label_en}"
                if opt.label_fa != opt.label_en
                else opt.label_en
            )
            btn = {
                "text": label,
                "callback_data": opt.payload,
            }
            current_row.append(btn)
            if len(current_row) >= 2:
                rows.append(current_row)
                current_row = []

        if current_row:
            rows.append(current_row)
        return rows

    def _chunk_text(self, text: str, max_length: int) -> list[str]:
        """Partition lengthy text at line breaks or word boundaries."""
        if len(text) <= max_length:
            return [text]

        chunks = []
        remaining = text
        while len(remaining) > max_length:
            split_idx = remaining.rfind("\n", 0, max_length)
            if split_idx == -1:
                split_idx = remaining.rfind(" ", 0, max_length)
            if split_idx == -1:
                split_idx = max_length

            chunks.append(remaining[:split_idx].strip())
            remaining = remaining[split_idx:].strip()

        if remaining:
            chunks.append(remaining)
        return chunks

    def _api_call(self, method: str, data: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Perform standard HTTPS API call to Telegram."""
        url = f"{self.api_base_url}/bot{self.bot_token}/{method}"
        try:
            if data is not None:
                encoded_data = json.dumps(data).encode("utf-8")
                req = Request(
                    url,
                    data=encoded_data,
                    headers={"Content-Type": "application/json"},
                )
            else:
                req = Request(url)

            with urlopen(req, timeout=35.0) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except Exception as exc:
            logger.error(f"Telegram API call '{method}' failed: {exc}")
            return None

    def _polling_worker(self) -> None:
        """Background thread for Telegram long-polling."""
        while self._running:
            try:
                updates = self._api_call(
                    "getUpdates",
                    {
                        "offset": self._last_update_id + 1,
                        "timeout": POLL_TIMEOUT_SECS,
                        "allowed_updates": ["message", "callback_query"],
                    },
                )
                if not updates or not updates.get("ok"):
                    time.sleep(2.0)
                    continue

                for update in updates.get("result", []):
                    self._process_update(update)

            except Exception as exc:
                logger.error(f"Error in Telegram polling loop: {exc}")
                time.sleep(3.0)

    def _process_update(self, update: dict[str, Any]) -> None:
        """Process a single Telegram update dictionary."""
        update_id = update.get("update_id", 0)
        if update_id > self._last_update_id:
            self._last_update_id = update_id

        # 1. Handle incoming chat message
        if "message" in update:
            msg_data = update["message"]
            sender = msg_data.get("from", {})
            chat = msg_data.get("chat", {})
            text = msg_data.get("text", "")

            msg_type = MessageType.TEXT
            if "voice" in msg_data:
                msg_type = MessageType.VOICE

            incoming = IncomingMessage(
                message_id=str(msg_data.get("message_id")),
                platform=PlatformType.TELEGRAM,
                sender_id=str(sender.get("id")),
                sender_name=sender.get("first_name", "User"),
                text=text,
                channel_id=str(chat.get("id")),
                message_type=msg_type,
                raw_payload=msg_data,
            )

            if self.message_handler:
                self.message_handler(incoming)

        # 2. Handle interactive button callback queries
        elif "callback_query" in update:
            cb_data = update["callback_query"]
            sender = cb_data.get("from", {})
            payload = cb_data.get("data", "")
            cb_id = cb_data.get("id")

            # Acknowledge callback query
            self._api_call("answerCallbackQuery", {"callback_query_id": cb_id})

            if self.interaction_handler:
                self.interaction_handler({
                    "platform": PlatformType.TELEGRAM,
                    "sender_id": str(sender.get("id")),
                    "payload": payload,
                    "raw": cb_data,
                })
