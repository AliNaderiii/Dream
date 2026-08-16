"""Slack adapter: Socket Mode over the shared RFC 6455 WebSocket client.

The adapter calls ``apps.connections.open`` (app-level token) for the socket
URL, then speaks the Socket Mode envelope protocol:

* ``events_api`` envelopes → typed events (message events become
  :class:`IncomingMessage`); every envelope is acked with its ``envelope_id``;
* ``slash_commands`` envelopes → acked immediately (within Slack's 3-second
  window), then the reply is posted to the command's ``response_url``;
* every other envelope type is acked generically.

Outbound replies normally go through ``chat.postMessage`` (bot token).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dream.connectivity.base import OnMessage, PlatformAdapter
from dream.connectivity.models import IncomingMessage
from dream.connectivity.websocket import WebSocketClosed, WebSocketError, connect

logger = logging.getLogger(__name__)

SLACK_API_BASE_URL = "https://slack.com/api"


class SlackError(RuntimeError):
    """A Slack Web API or Socket Mode failure."""


class SlackApi:
    """Standard-library Web API client for the endpoints this adapter needs."""

    def __init__(self, app_token: str, bot_token: str) -> None:
        if not app_token:
            raise SlackError("slack app_token is missing")
        if not bot_token:
            raise SlackError("slack bot_token is missing")
        self.app_token = str(app_token)
        self.bot_token = str(bot_token)
        self.base_url = SLACK_API_BASE_URL

    def _call(
        self, method: str, payload: dict[str, Any], *, app_level: bool = False
    ) -> dict[str, Any]:
        token = self.app_token if app_level else self.bot_token
        request = Request(
            f"{self.base_url}/{method}",
            data=urlencode(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:  # nosec B310
                decoded = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise SlackError(f"Slack {method} failed: {exc}") from None
        if not isinstance(decoded, dict) or decoded.get("ok") is not True:
            raise SlackError(f"Slack {method} rejected the request: {decoded.get('error')}")
        return decoded

    def connections_open(self) -> dict[str, Any]:
        """Fetch the Socket Mode WebSocket URL (``apps.connections.open``)."""
        return self._call("apps.connections.open", {}, app_level=True)

    def post_message(self, channel: str, text: str) -> dict[str, Any]:
        return self._call("chat.postMessage", {"channel": channel, "text": text})

    def post_response(self, response_url: str, text: str) -> dict[str, Any]:
        """Reply to a slash command by POSTing JSON to its ``response_url``."""
        request = Request(
            response_url,
            data=json.dumps({"text": text, "response_type": "in_channel"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:  # nosec B310
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise SlackError(f"Slack response_url failed: {exc}") from None


class SlackAdapter(PlatformAdapter):
    """Socket Mode bot: event envelopes in, chat.postMessage out."""

    platform_name = "slack"
    max_message_length = 4000
    supports_inline = True
    supports_attachments = False
    privacy = "plaintext"

    def __init__(
        self,
        config: dict[str, Any],
        *,
        on_message: OnMessage,
        api: SlackApi | None = None,
        ws_connect: Any = None,
    ) -> None:
        super().__init__(config, on_message=on_message)
        self._api = api
        self._ws_connect = ws_connect or connect
        self._task: asyncio.Task[Any] | None = None
        self._stop_event = asyncio.Event()
        self._ws = None
        #: user_id -> pending slash-command response_url.
        self._pending_responses: dict[str, str] = {}
        #: user_id -> last channel they wrote in (for chat.postMessage).
        self._user_channels: dict[str, str] = {}

    # -- config ----------------------------------------------------------- #

    def _build_api(self) -> SlackApi:
        if self._api is not None:
            return self._api
        api = SlackApi(
            str(self._config.get("app_token") or ""),
            str(self._config.get("bot_token") or ""),
        )
        self._api = api
        return api

    # -- lifecycle -------------------------------------------------------- #

    async def start(self) -> None:
        if self._task is not None:
            return
        try:
            self._build_api()
        except SlackError as exc:
            self._mark_error(str(exc))
            raise
        self._stop_event.clear()
        self._status.running = True
        self._status.error = None
        self._task = asyncio.create_task(self._run(), name="slack-socket-mode")

    async def stop(self) -> None:
        self._stop_event.set()
        ws = self._ws
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._status.running = False
        self._status.connected = False

    async def _run(self) -> None:
        api = self._build_api()
        while not self._stop_event.is_set():
            try:
                opened = await asyncio.to_thread(api.connections_open)
                url = opened.get("url")
                if not url:
                    raise SlackError("apps.connections.open returned no socket URL")
                ws = await self._ws_connect(str(url))
                self._ws = ws
                self._status.connected = True
                async for raw in ws:
                    envelope = json.loads(raw) if isinstance(raw, str) else raw
                    await self._handle_envelope(envelope)
            except asyncio.CancelledError:
                raise
            except (WebSocketClosed, WebSocketError, SlackError) as exc:
                self._mark_error(str(exc), running=True)
                self._status.connected = False
                await asyncio.sleep(5.0)
            except Exception as exc:
                self._mark_error(f"{type(exc).__name__}: {exc}", running=True)
                await asyncio.sleep(5.0)

    async def _handle_envelope(self, envelope: dict[str, Any]) -> None:
        envelope_type = str(envelope.get("type") or "")
        envelope_id = str(envelope.get("envelope_id") or "")
        if envelope_id and self._ws is not None:
            # Socket Mode: ack every envelope, always, and fast.
            await self._ws.send_json({"envelope_id": envelope_id})
        if envelope_type == "events_api":
            await self._handle_event(envelope.get("payload", {}))
        elif envelope_type == "slash_commands":
            await self._handle_slash_command(envelope.get("payload", {}))

    async def _handle_event(self, payload: dict[str, Any]) -> None:
        event = payload.get("event")
        if not isinstance(event, dict):
            return
        if event.get("type") != "message":
            return
        if event.get("subtype") or event.get("bot_id"):
            return  # skip joins, edits, and other bots
        text = event.get("text")
        if not isinstance(text, str) or not text.strip():
            return
        user_id = str(event.get("user") or "")
        channel = str(event.get("channel") or "")
        if not user_id or not channel:
            return
        self._user_channels[user_id] = channel
        await self.deliver(
            IncomingMessage(
                platform=self.platform_name,
                platform_user_id=user_id,
                platform_channel_id=channel,
                text=text,
                message_id=str(event.get("ts") or event.get("client_msg_id") or ""),
                raw=dict(event),
            )
        )

    async def _handle_slash_command(self, payload: dict[str, Any]) -> None:
        text = str(payload.get("text") or "").strip()
        user_id = str(payload.get("user_id") or "")
        channel = str(payload.get("channel_id") or "")
        response_url = str(payload.get("response_url") or "")
        if not user_id or not text:
            return
        if response_url:
            self._pending_responses[user_id] = response_url
        self._user_channels[user_id] = channel
        await self.deliver(
            IncomingMessage(
                platform=self.platform_name,
                platform_user_id=user_id,
                platform_channel_id=channel,
                text=text,
                message_id=str(payload.get("trigger_id") or ""),
                raw=dict(payload),
            )
        )

    # -- outbound ---------------------------------------------------------- #

    async def send_message(self, user_id: str, text: str, attachments: list | None = None) -> None:
        del attachments
        api = self._build_api()
        response_url = self._pending_responses.pop(user_id, None)
        if response_url:
            await asyncio.to_thread(api.post_response, response_url, text)
            return
        channel = self._user_channels.get(user_id, user_id)
        await asyncio.to_thread(api.post_message, channel, text)

    async def send_typing_indicator(self, user_id: str) -> None:
        # Slack has no API-side typing indicator; nothing to send.
        del user_id


__all__ = ["SlackAdapter", "SlackApi", "SlackError"]
