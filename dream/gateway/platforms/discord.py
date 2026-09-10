"""Discord platform adapter supporting Bot REST API, embeds, and webhook triggers."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any
from urllib.request import Request, urlopen

from dream.gateway.platforms.base import BasePlatformAdapter
from dream.gateway.types import (
    ButtonOption,
    IncomingMessage,
    InteractivePrompt,
    OutgoingMessage,
    PlatformType,
)

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"
MAX_DISCORD_MSG_LEN = 2000


class DiscordAdapter(BasePlatformAdapter):
    """Adapter for Discord Bot API and Webhooks."""

    def __init__(
        self,
        bot_token: str | None = None,
        webhook_url: str | None = None,
        message_handler: Callable[[IncomingMessage], Any] | None = None,
        interaction_handler: Callable[[Any], Any] | None = None,
    ) -> None:
        super().__init__(PlatformType.DISCORD, message_handler, interaction_handler)
        self.bot_token = bot_token
        self.webhook_url = webhook_url

    def connect(self) -> bool:
        """Validate Discord Bot token or Webhook destination."""
        if not self.bot_token and not self.webhook_url:
            logger.error("Discord adapter requires either a bot_token or webhook_url.")
            return False

        if self.bot_token:
            res = self._api_call("GET", "/users/@me")
            if not res or "id" not in res:
                logger.error("Failed to authenticate Discord bot token.")
                return False
            logger.info(f"Discord connected as {res.get('username')}#{res.get('discriminator')}")

        self.is_connected = True
        return True

    def disconnect(self) -> None:
        """Disconnect Discord adapter."""
        self.is_connected = False

    def send_message(self, message: OutgoingMessage) -> bool:
        """Transmit message to Discord channel or user DM."""
        channel_id = message.target.channel_id or message.target.recipient_id
        text = message.text

        # Embed formatting if interactive prompt or rich payload
        payload: dict[str, Any] = {"content": text[:MAX_DISCORD_MSG_LEN]}

        if message.interactive:
            components = self._build_action_rows(message.interactive.options)
            payload["components"] = components

        if self.webhook_url and not self.bot_token:
            return self._send_webhook(payload)

        endpoint = f"/channels/{channel_id}/messages"
        res = self._api_call("POST", endpoint, payload)
        return bool(res and "id" in res)

    def send_interactive_prompt(self, target_id: str, prompt: InteractivePrompt) -> bool:
        """Send interactive components/buttons to Discord."""
        payload = {
            "content": f"**{prompt.title}**\n{prompt.description}",
            "components": self._build_action_rows(prompt.options),
        }
        endpoint = f"/channels/{target_id}/messages"
        res = self._api_call("POST", endpoint, payload)
        return bool(res and "id" in res)

    def handle_incoming_webhook_event(self, data: dict[str, Any]) -> None:
        """Process incoming Discord gateway/webhook payload."""
        event_type = data.get("t")
        event_data = data.get("d", {})

        if event_type == "MESSAGE_CREATE":
            author = event_data.get("author", {})
            if author.get("bot"):
                return

            incoming = IncomingMessage(
                message_id=str(event_data.get("id")),
                platform=PlatformType.DISCORD,
                sender_id=str(author.get("id")),
                sender_name=author.get("username", "DiscordUser"),
                text=event_data.get("content", ""),
                channel_id=str(event_data.get("channel_id")),
                raw_payload=event_data,
            )
            if self.message_handler:
                self.message_handler(incoming)

        elif event_type == "INTERACTION_CREATE":
            interaction_data = event_data.get("data", {})
            member = event_data.get("member", {}).get("user", {})
            if self.interaction_handler:
                self.interaction_handler({
                    "platform": PlatformType.DISCORD,
                    "sender_id": str(member.get("id")),
                    "payload": interaction_data.get("custom_id", ""),
                    "raw": event_data,
                })

    def _build_action_rows(self, options: list[ButtonOption]) -> list[dict[str, Any]]:
        """Construct Discord Action Row components."""
        buttons = []
        for opt in options:
            btn = {
                "type": 2,  # BUTTON component
                "label": f"{opt.label_fa} ({opt.label_en})",
                "style": 1 if opt.style == "primary" else (4 if opt.style == "danger" else 2),
                "custom_id": opt.payload,
            }
            buttons.append(btn)
        return [{"type": 1, "components": buttons}]

    def _send_webhook(self, payload: dict[str, Any]) -> bool:
        """Send payload directly to configured Webhook URL."""
        assert self.webhook_url is not None
        try:
            req = Request(
                self.webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=15.0) as resp:
                return resp.status in (200, 204)
        except Exception as exc:
            logger.error(f"Discord webhook failed: {exc}")
            return False

    def _api_call(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Perform Discord REST API call."""
        if not self.bot_token:
            return None

        url = f"{DISCORD_API_BASE}{endpoint}"
        headers = {
            "Authorization": f"Bot {self.bot_token}",
            "Content-Type": "application/json",
            "User-Agent": "DreamAssistant/1.0",
        }
        try:
            req_data = json.dumps(data).encode("utf-8") if data is not None else None
            req = Request(url, data=req_data, headers=headers, method=method)
            with urlopen(req, timeout=20.0) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except Exception as exc:
            logger.error(f"Discord API call error ({method} {endpoint}): {exc}")
            return None
