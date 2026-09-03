"""Telegram adapter: long-polling getUpdates over urllib (no third-party SDK).

Reuses the token validation and redaction helpers from the existing
``dream/telegram.py`` front end so the two surfaces recognise identical
token shapes and never leak them into logs. Commands (``/start``, ``/help``,
``/new_session``, ``/status``, ``/link <code>``) are handled by the gateway;
this adapter only transports normalised messages.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dream.connectivity.base import OnMessage, PlatformAdapter
from dream.connectivity.models import IncomingMessage, utc_now
from dream.reliability.cancel import CancelToken
from dream.reliability.sleep import ainterruptible_sleep
from dream.telegram import (
    _TOKEN_FULL_RE,
    _resolve_api_base_url,
    redact_token,
)

logger = logging.getLogger(__name__)

POLL_TIMEOUT = 25
HTTP_TIMEOUT = 35
ALLOWED_UPDATES = ("message",)
DEFAULT_POLL_INTERVAL = 2.0
BACKOFF_MAX = 30.0


class TelegramConfigurationError(ValueError):
    """A safe-to-display Telegram configuration failure."""


class TelegramNetworkError(RuntimeError):
    """A redacted Telegram API or transport failure."""


class TelegramTransport:
    """Standard-library client for the Bot API subset this adapter uses.

    The injectable seam: unit tests substitute a fake with the same methods.
    """

    def __init__(self, token: str, api_base_url: str | None = None) -> None:
        if not token or _TOKEN_FULL_RE.fullmatch(token) is None:
            raise TelegramConfigurationError("telegram token is missing or malformed")
        base = _resolve_api_base_url(api_base_url)
        self._base_url = f"{base}/bot{token}"

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self._base_url}/{method}",
            data=urlencode(payload).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=HTTP_TIMEOUT) as response:  # nosec B310
                decoded = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise TelegramNetworkError(
                f"Telegram {method} failed: {redact_token(exc)}"
            ) from None
        if not isinstance(decoded, dict) or decoded.get("ok") is not True:
            description = redact_token(decoded.get("description", "request rejected"))
            raise TelegramNetworkError(f"Telegram {method} rejected the request: {description}")
        return decoded

    def get_updates(self, offset: int) -> list[dict[str, Any]]:
        response = self._call(
            "getUpdates",
            {
                "offset": offset,
                "timeout": POLL_TIMEOUT,
                "allowed_updates": json.dumps(list(ALLOWED_UPDATES)),
            },
        )
        result = response.get("result")
        if not isinstance(result, list):
            raise TelegramNetworkError("Telegram getUpdates returned an invalid result")
        return result

    def send_message(self, chat_id: int, text: str) -> None:
        self._call("sendMessage", {"chat_id": chat_id, "text": text})

    def send_chat_action(self, chat_id: int, action: str) -> None:
        self._call("sendChatAction", {"chat_id": chat_id, "action": action})


def _integer_identifier(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdecimal():
        return int(value)
    return None


class TelegramAdapter(PlatformAdapter):
    """Long-polling Telegram bot fed into the gateway router."""

    platform_name = "telegram"
    max_message_length = 4096
    supports_inline = True
    supports_attachments = False
    privacy = "plaintext"

    def __init__(
        self,
        config: dict[str, Any],
        *,
        on_message: OnMessage,
        transport: TelegramTransport | None = None,
    ) -> None:
        super().__init__(config, on_message=on_message)
        self._transport = transport
        self._offset = 0
        self._task: asyncio.Task[Any] | None = None
        self._stop_event = asyncio.Event()

    # -- config ----------------------------------------------------------- #

    def _build_transport(self) -> TelegramTransport:
        if self._transport is not None:
            return self._transport
        token = str(self._config.get("token") or "")
        base = str(self._config.get("api_base_url") or "") or None
        transport = TelegramTransport(token, base)
        self._transport = transport
        return transport

    def _poll_interval(self) -> float:
        try:
            return max(0.0, float(self._config.get("poll_interval", DEFAULT_POLL_INTERVAL)))
        except (TypeError, ValueError):
            return DEFAULT_POLL_INTERVAL

    # -- lifecycle -------------------------------------------------------- #

    async def start(self) -> None:
        if self._task is not None:
            return
        try:
            self._build_transport()
        except TelegramConfigurationError as exc:
            self._mark_error(str(exc))
            raise
        self._stop_event.clear()
        self._status.running = True
        self._status.connected = True
        self._status.error = None
        self._task = asyncio.create_task(self._poll_loop(), name="telegram-poll")

    async def stop(self) -> None:
        self._stop_event.set()
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

    # -- inbound ---------------------------------------------------------- #

    async def _poll_loop(self) -> None:
        failures = 0
        transport = self._build_transport()
        cancel = CancelToken.from_async_event(self._stop_event, name="telegram.poll")
        while not self._stop_event.is_set():
            try:
                updates = await asyncio.to_thread(transport.get_updates, self._offset)
                await self._process_updates(updates)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                failures += 1
                self._mark_error(redact_token(str(exc)), running=True)
                await ainterruptible_sleep(
                    min(BACKOFF_MAX, 2 ** min(failures, 5)), cancel=cancel
                )
                continue
            failures = 0
            await ainterruptible_sleep(self._poll_interval(), cancel=cancel)

    async def _process_updates(self, updates: list[dict[str, Any]]) -> None:
        """Deliver in order and acknowledge each update only after success."""
        ordered: list[tuple[int, dict[str, Any]]] = []
        for update in updates:
            update_id = _integer_identifier(update.get("update_id"))
            if update_id is not None and update_id >= self._offset:
                ordered.append((update_id, update))
        for update_id, update in sorted(ordered, key=lambda pair: pair[0]):
            if update_id < self._offset:
                continue  # duplicate identifier in one batch
            await self._handle_update(update)
            self._offset = max(self._offset, update_id + 1)

    async def _handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat = message.get("chat")
        sender = message.get("from")
        if not isinstance(chat, dict) or not isinstance(sender, dict):
            return
        # Pairing and owner data are private-chat only.  A linked user must
        # not be able to invoke Dream from a group where others can observe.
        if str(chat.get("type", "")) != "private":
            return
        chat_id = _integer_identifier(chat.get("id"))
        user_id = _integer_identifier(sender.get("id"))
        if chat_id is None or user_id is None:
            return
        text = message.get("text")
        caption = message.get("caption")
        body = text if isinstance(text, str) else (caption if isinstance(caption, str) else "")
        if not body.strip():
            return
        timestamp = utc_now()
        raw_date = message.get("date")
        if isinstance(raw_date, int):
            from datetime import datetime, timezone

            timestamp = datetime.fromtimestamp(raw_date, tz=timezone.utc)
        await self.deliver(
            IncomingMessage(
                platform=self.platform_name,
                platform_user_id=str(user_id),
                platform_channel_id=str(chat_id),
                text=body,
                timestamp=timestamp,
                message_id=str(message.get("message_id") or ""),
                raw=dict(update),
            )
        )

    # -- outbound --------------------------------------------------------- #

    async def send_message(self, user_id: str, text: str, attachments: list | None = None) -> None:
        del attachments  # Telegram send path is text-only for this adapter
        transport = self._build_transport()
        chat_id = _integer_identifier(user_id)
        if chat_id is None:
            raise TelegramConfigurationError(f"invalid chat id {user_id!r}")
        safe = redact_token(text)
        await asyncio.to_thread(transport.send_message, chat_id, safe)

    async def send_typing_indicator(self, user_id: str) -> None:
        transport = self._build_transport()
        chat_id = _integer_identifier(user_id)
        if chat_id is None:
            return
        try:
            await asyncio.to_thread(transport.send_chat_action, chat_id, "typing")
        except TelegramNetworkError:
            pass  # cosmetic


__all__ = [
    "TelegramAdapter",
    "TelegramConfigurationError",
    "TelegramNetworkError",
    "TelegramTransport",
]
