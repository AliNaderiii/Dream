"""Discord adapter: gateway WebSocket + REST, standard library only.

* connects to the gateway (Op 10 Hello → Op 2 Identify → Op 11 heartbeat ACK,
  ``compress: false`` so no zlib-stream handling is needed);
* registers a global ``/dream`` slash command via REST when configured;
* answers interactions within the 3-second window using the Deferred (type 5)
  ack, then follows up by PATCHing the ``@original`` webhook message;
* sends messages over REST and can auto-create a private thread per channel.

Both seams — :class:`DiscordHttp` and the ``ws_connect`` callable — are
injectable for unit tests.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dream.connectivity.base import OnMessage, PlatformAdapter
from dream.connectivity.models import Attachment, IncomingMessage
from dream.connectivity.websocket import WebSocketClosed, WebSocketError, connect
from dream.reliability.cancel import CancelToken, OperationCancelled
from dream.reliability.sleep import ainterruptible_sleep

logger = logging.getLogger(__name__)

API_BASE_URL = "https://discord.com/api/v10"
GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"
#: GUILDS | GUILD_MESSAGES | MESSAGE_CONTENT | DIRECT_MESSAGES
INTENTS = (1 << 0) | (1 << 9) | (1 << 15) | (1 << 12)
HEARTBEAT_ACK_GRACE = 2.0

OP_DISPATCH = 0
OP_HEARTBEAT = 1
OP_IDENTIFY = 2
OP_HELLO = 10
OP_HEARTBEAT_ACK = 11

INTERACTION_DEFERRED = 5


class DiscordError(RuntimeError):
    """A Discord API or gateway failure."""


class DiscordHttp:
    """Standard-library REST client for the endpoints this adapter needs."""

    def __init__(self, bot_token: str) -> None:
        if not bot_token:
            raise DiscordError("discord bot_token is missing")
        self.bot_token = str(bot_token)
        self.base_url = API_BASE_URL

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bot {self.bot_token}",
            "User-Agent": "dream-assistant/0.1.0",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _request(
        self, method: str, path: str, payload: Any = None, *, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers = self._headers({"Content-Type": "application/json", **(headers or {})})
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=self._headers(headers or {}),
            method=method,
        )
        try:
            with urlopen(request, timeout=20) as response:  # nosec B310
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise DiscordError(f"Discord HTTP {method} {path} failed: {detail}") from None
        except Exception as exc:
            raise DiscordError(f"Discord HTTP {method} {path} failed: {exc}") from None

    def get_current_application(self) -> dict[str, Any]:
        return self._request("GET", "/oauth2/applications/@me")

    def register_command(self, application_id: str) -> dict[str, Any]:
        """Register the global ``/dream`` slash command (idempotent upsert)."""
        payload = {
            "name": "dream",
            "description": "Talk to Dream, the local assistant.",
            "options": [
                {
                    "name": "message",
                    "description": "What to say to Dream.",
                    "type": 3,
                    "required": True,
                }
            ],
        }
        return self._request(
            "PUT", f"/applications/{application_id}/commands", [payload]
        )

    def send_message(self, channel_id: str, content: str) -> dict[str, Any]:
        return self._request("POST", f"/channels/{channel_id}/messages", {"content": content})

    def send_file(
        self, channel_id: str, filename: str, data: bytes, content: str = ""
    ) -> dict[str, Any]:
        """Upload one attachment via a hand-built multipart/form-data body."""
        boundary = f"----dream{secrets.token_hex(8)}"
        lines: list[bytes] = []
        fields = {"payload_json": json.dumps({"content": content})}
        for name, value in fields.items():
            lines.append(f"--{boundary}\r\n".encode())
            lines.append(
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            )
            lines.append(value.encode("utf-8"))
            lines.append(b"\r\n")
        lines.append(f"--{boundary}\r\n".encode())
        lines.append(
            (
                f'Content-Disposition: form-data; name="files[0]"; filename="{filename}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
        )
        lines.append(data)
        lines.append(f"\r\n--{boundary}--\r\n".encode())
        body = b"".join(lines)
        request = Request(
            f"{self.base_url}/channels/{channel_id}/messages",
            data=body,
            headers=self._headers(
                {"Content-Type": f"multipart/form-data; boundary={boundary}"}
            ),
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:  # nosec B310
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise DiscordError(f"Discord file upload failed: {exc}") from None

    def create_thread(self, channel_id: str, message_id: str, name: str) -> dict[str, Any]:
        return self._request(
            "POST", f"/channels/{channel_id}/messages/{message_id}/threads", {"name": name}
        )

    def respond_interaction(self, interaction_id: str, token: str) -> None:
        """Ack an interaction as Deferred (type 5) inside the 3-second window."""
        self._request(
            "POST",
            f"/interactions/{interaction_id}/{token}/callback",
            {"type": INTERACTION_DEFERRED},
        )

    def edit_interaction(self, application_id: str, token: str, content: str) -> dict[str, Any]:
        """PATCH the deferred interaction's @original webhook message."""
        return self._request(
            "PATCH",
            f"/webhooks/{application_id}/{token}/messages/@original",
            {"content": content},
        )


def _multipart_payload_text(payload: dict[str, Any]) -> str:
    """First text value from a slash-command option list (fallback: prompt)."""
    for option in payload.get("data", {}).get("options", []) or []:
        value = option.get("value")
        if isinstance(value, str) and value.strip():
            return value
    return ""


class DiscordAdapter(PlatformAdapter):
    """Gateway-WebSocket bot with slash-command interaction support."""

    platform_name = "discord"
    max_message_length = 2000
    supports_inline = True
    supports_attachments = True
    privacy = "plaintext"

    def __init__(
        self,
        config: dict[str, Any],
        *,
        on_message: OnMessage,
        http: DiscordHttp | None = None,
        ws_connect: Any = None,
        clock: Any = None,
    ) -> None:
        super().__init__(config, on_message=on_message)
        self._http = http
        self._ws_connect = ws_connect or connect
        self._clock = clock or (lambda: __import__("time").time())
        self._task: asyncio.Task[Any] | None = None
        self._stop_event = asyncio.Event()
        self._ws = None
        self._heartbeat_ack = asyncio.Event()
        #: user_id -> (application_id, interaction_token) awaiting a follow-up.
        self._pending_interactions: dict[str, tuple[str, str]] = {}
        #: user_id -> last channel they wrote in.
        self._user_channels: dict[str, str] = {}
        #: channel_id -> thread channel id created for replies.
        self._threads: dict[str, str] = {}

    # -- config ----------------------------------------------------------- #

    def _build_http(self) -> DiscordHttp:
        if self._http is not None:
            return self._http
        http = DiscordHttp(str(self._config.get("bot_token") or ""))
        self._http = http
        return http

    # -- lifecycle -------------------------------------------------------- #

    async def start(self) -> None:
        if self._task is not None:
            return
        try:
            http = self._build_http()
        except DiscordError as exc:
            self._mark_error(str(exc))
            raise
        self._stop_event.clear()
        self._status.running = True
        self._status.error = None
        self._task = asyncio.create_task(self._run(), name="discord-gateway")
        if self._config.get("register_commands", True):
            asyncio.create_task(self._register_commands(http), name="discord-commands")

    async def _register_commands(self, http: DiscordHttp) -> None:
        try:
            application_id = str(self._config.get("application_id") or "")
            if not application_id:
                application_id = str(http.get_current_application().get("id") or "")
            if application_id:
                await asyncio.to_thread(http.register_command, application_id)
        except Exception as exc:
            logger.warning("discord command registration failed: %s", exc)

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

    # -- gateway session --------------------------------------------------- #

    async def _run(self) -> None:
        cancel = CancelToken.from_async_event(self._stop_event, name="discord.poll")
        while not self._stop_event.is_set():
            try:
                ws = await self._ws_connect(GATEWAY_URL)
                self._ws = ws
                self._status.connected = True
                await self._session(ws)
            except OperationCancelled:
                raise
            except asyncio.CancelledError:
                raise
            except (WebSocketClosed, WebSocketError, DiscordError) as exc:
                self._mark_error(str(exc), running=True)
                self._status.connected = False
                await ainterruptible_sleep(
                    min(15.0, 1.0 + self._backoff()), cancel=cancel
                )
            except Exception as exc:
                self._mark_error(f"{type(exc).__name__}: {exc}", running=True)
                await ainterruptible_sleep(5.0, cancel=cancel)
            finally:
                self._status.connected = False
                self._ws = None
                if not self._stop_event.is_set():
                    await ainterruptible_sleep(1.0, cancel=cancel)

    _backoff_failures = 0

    def _backoff(self) -> float:
        self._backoff_failures = min(self._backoff_failures + 1, 5)
        return 2 ** self._backoff_failures

    async def _session(self, ws: Any) -> None:
        hello = await ws.recv_json()
        if hello.get("op") != OP_HELLO:
            raise DiscordError("gateway did not send Hello")
        interval = float(hello.get("d", {}).get("heartbeat_interval", 41250)) / 1000.0
        heartbeat = asyncio.create_task(self._heartbeat_loop(ws, interval))
        token = str(self._config.get("bot_token") or "")
        await ws.send_json(
            {
                "op": OP_IDENTIFY,
                "d": {
                    "token": token,
                    "intents": INTENTS,
                    "compress": False,
                    "properties": {
                        "os": "linux",
                        "browser": "dream-assistant",
                        "device": "dream-assistant",
                    },
                },
            }
        )
        try:
            async for raw in ws:
                event = json.loads(raw) if isinstance(raw, str) else raw
                await self._handle_event(event)
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except (asyncio.CancelledError, OperationCancelled):
                pass

    async def _heartbeat_loop(self, ws: Any, interval: float) -> None:
        sequence = 0
        cancel = CancelToken.from_async_event(self._stop_event, name="discord.heartbeat")
        while not self._stop_event.is_set():
            await ainterruptible_sleep(interval, cancel=cancel)
            self._heartbeat_ack.clear()
            await ws.send_json({"op": OP_HEARTBEAT, "d": sequence})
            try:
                await asyncio.wait_for(
                    self._heartbeat_ack.wait(), timeout=interval + HEARTBEAT_ACK_GRACE
                )
            except TimeoutError:
                raise WebSocketError("gateway heartbeat was not acknowledged") from None

    async def _handle_event(self, event: dict[str, Any]) -> None:
        op = event.get("op")
        if op == OP_HEARTBEAT_ACK:
            self._heartbeat_ack.set()
            return
        if op == 9:
            raise WebSocketError("gateway requested re-identification (invalid session)")
        if op != OP_DISPATCH:
            return
        event_type = event.get("t")
        data = event.get("d", {})
        if event_type == "MESSAGE_CREATE":
            await self._handle_message(data)
        elif event_type == "INTERACTION_CREATE":
            await self._handle_interaction(data)

    async def _handle_message(self, data: dict[str, Any]) -> None:
        author = data.get("author", {})
        if author.get("bot"):
            return
        content = data.get("content")
        if not isinstance(content, str) or not content.strip():
            return
        channel_id = str(data.get("channel_id") or "")
        user_id = str(author.get("id") or "")
        if not channel_id or not user_id:
            return
        self._user_channels[user_id] = channel_id
        await self._maybe_create_thread(data)
        attachments = [
            Attachment(
                mime_type=str(item.get("content_type") or "application/octet-stream"),
                filename=item.get("filename"),
                url=item.get("url"),
                size=int(item.get("size") or 0),
            )
            for item in data.get("attachments", []) or []
            if isinstance(item, dict)
        ]
        await self.deliver(
            IncomingMessage(
                platform=self.platform_name,
                platform_user_id=user_id,
                platform_channel_id=channel_id,
                text=content,
                attachments=attachments,
                message_id=str(data.get("id") or ""),
                raw=dict(data),
            )
        )

    async def _maybe_create_thread(self, data: dict[str, Any]) -> None:
        if not self._config.get("auto_thread", False):
            return
        channel_id = str(data.get("channel_id") or "")
        if not channel_id or channel_id in self._threads:
            return
        if data.get("guild_id") is None:
            return  # direct messages are already private
        http = self._build_http()
        name = str(self._config.get("thread_name") or "dream")
        try:
            created = await asyncio.to_thread(
                http.create_thread, channel_id, str(data.get("id") or ""), name
            )
        except DiscordError:
            return
        thread_id = str(created.get("id") or "")
        if thread_id:
            self._threads[channel_id] = thread_id

    async def _handle_interaction(self, data: dict[str, Any]) -> None:
        token = str(data.get("token") or "")
        interaction_id = str(data.get("id") or "")
        application_id = str(data.get("application_id") or "")
        member = data.get("member", {}) or {}
        user = data.get("user", {}) or {}
        user_id = str(user.get("id") or member.get("user", {}).get("id") or "")
        text = _multipart_payload_text(data)
        if not token or not interaction_id or not user_id or not text:
            return
        http = self._build_http()
        try:
            # Type 5 Deferred ack must land within 3 seconds of the event.
            await asyncio.to_thread(http.respond_interaction, interaction_id, token)
        except DiscordError as exc:
            self._mark_error(str(exc), running=True)
            return
        self._pending_interactions[user_id] = (application_id, token)
        self._status.connected = True
        await self.deliver(
            IncomingMessage(
                platform=self.platform_name,
                platform_user_id=user_id,
                platform_channel_id=str(data.get("channel_id") or ""),
                text=text,
                message_id=interaction_id,
                raw=dict(data),
            )
        )

    # -- outbound ---------------------------------------------------------- #

    async def send_message(self, user_id: str, text: str, attachments: list | None = None) -> None:
        http = self._build_http()
        pending = self._pending_interactions.pop(user_id, None)
        if pending is not None:
            application_id, token = pending
            if application_id:
                await asyncio.to_thread(http.edit_interaction, application_id, token, text)
                return
        channel_id = self._threads.get(self._user_channels.get(user_id, ""))
        if channel_id is None:
            channel_id = self._user_channels.get(user_id)
        if channel_id is None:
            channel_id = user_id  # DM fallback: user id is a valid DM channel
        if attachments:
            first = attachments[0]
            if getattr(first, "data", None):
                await asyncio.to_thread(
                    http.send_file,
                    channel_id,
                    getattr(first, "filename", None) or "attachment.bin",
                    first.data,
                    text,
                )
                return
        await asyncio.to_thread(http.send_message, channel_id, text)

    async def send_typing_indicator(self, user_id: str) -> None:
        # Discord's typing endpoint is POST /channels/{id}/typing — a 9-second
        # timer that fires once; the gateway already makes the UX acceptable.
        del user_id


__all__ = ["DiscordAdapter", "DiscordError", "DiscordHttp"]
