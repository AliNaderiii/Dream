"""Slack platform adapter with Block Kit formatting and Slash Command routing."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any
from urllib.request import Request, urlopen

from dream.gateway.platforms.base import BasePlatformAdapter
from dream.gateway.types import (
    IncomingMessage,
    InteractivePrompt,
    OutgoingMessage,
    PlatformType,
)

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"


class SlackAdapter(BasePlatformAdapter):
    """Adapter for Slack Web API, Webhooks, and Block Kit."""

    def __init__(
        self,
        bot_token: str | None = None,
        webhook_url: str | None = None,
        message_handler: Callable[[IncomingMessage], Any] | None = None,
        interaction_handler: Callable[[Any], Any] | None = None,
    ) -> None:
        super().__init__(PlatformType.SLACK, message_handler, interaction_handler)
        self.bot_token = bot_token
        self.webhook_url = webhook_url

    def connect(self) -> bool:
        """Validate Slack credentials."""
        if not self.bot_token and not self.webhook_url:
            logger.error("Slack adapter requires bot_token or webhook_url.")
            return False

        if self.bot_token:
            res = self._api_call("auth.test")
            if not res or not res.get("ok"):
                logger.error("Failed to authenticate Slack bot token.")
                return False
            logger.info(f"Slack connected to team {res.get('team')} as {res.get('user')}")

        self.is_connected = True
        return True

    def disconnect(self) -> None:
        """Disconnect Slack adapter."""
        self.is_connected = False

    def send_message(self, message: OutgoingMessage) -> bool:
        """Transmit message to Slack channel or user."""
        channel_id = message.target.channel_id or message.target.recipient_id
        text = message.text

        payload: dict[str, Any] = {
            "channel": channel_id,
            "text": text,
        }

        if message.interactive:
            payload["blocks"] = self._build_block_kit(message.interactive)

        if self.webhook_url and not self.bot_token:
            return self._send_webhook(payload)

        res = self._api_call("chat.postMessage", payload)
        return bool(res and res.get("ok"))

    def send_interactive_prompt(self, target_id: str, prompt: InteractivePrompt) -> bool:
        """Send interactive Block Kit buttons to Slack."""
        payload = {
            "channel": target_id,
            "text": prompt.title,
            "blocks": self._build_block_kit(prompt),
        }
        res = self._api_call("chat.postMessage", payload)
        return bool(res and res.get("ok"))

    def handle_slash_command(self, form_data: dict[str, str]) -> dict[str, Any]:
        """Process an incoming Slack slash command (e.g. /dream query)."""
        user_id = form_data.get("user_id", "unknown")
        user_name = form_data.get("user_name", "user")
        channel_id = form_data.get("channel_id")
        command_text = form_data.get("text", "")
        command = form_data.get("command", "/dream")

        full_text = f"{command} {command_text}".strip()
        incoming = IncomingMessage(
            message_id=form_data.get("trigger_id", "slack_cmd"),
            platform=PlatformType.SLACK,
            sender_id=user_id,
            sender_name=user_name,
            text=full_text,
            channel_id=channel_id,
            raw_payload=form_data,
        )

        if self.message_handler:
            self.message_handler(incoming)

        return {
            "response_type": "in_channel",
            "text": f"⏳ درخواست در حال پردازش است... / Processing `{command}`...",
        }

    def _build_block_kit(self, prompt: InteractivePrompt) -> list[dict[str, Any]]:
        """Construct Slack Block Kit layout."""
        elements = []
        for opt in prompt.options:
            btn = {
                "type": "button",
                "text": {"type": "plain_text", "text": f"{opt.label_fa} | {opt.label_en}"},
                "value": opt.payload,
                "action_id": opt.button_id,
            }
            if opt.style == "primary":
                btn["style"] = "primary"
            elif opt.style == "danger":
                btn["style"] = "danger"
            elements.append(btn)

        return [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{prompt.title}*\n{prompt.description}"},
            },
            {"type": "actions", "elements": elements},
        ]

    def _send_webhook(self, payload: dict[str, Any]) -> bool:
        """Send message via Incoming Webhook URL."""
        assert self.webhook_url is not None
        try:
            req = Request(
                self.webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=15.0) as resp:
                return resp.status == 200
        except Exception as exc:
            logger.error(f"Slack webhook failed: {exc}")
            return False

    def _api_call(self, method: str, data: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Invoke Slack Web API method."""
        if not self.bot_token:
            return None

        url = f"{SLACK_API_BASE}/{method}"
        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        try:
            req_data = json.dumps(data).encode("utf-8") if data is not None else None
            req = Request(url, data=req_data, headers=headers, method="POST")
            with urlopen(req, timeout=20.0) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except Exception as exc:
            logger.error(f"Slack API error ({method}): {exc}")
            return None
