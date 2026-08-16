"""Signal adapter: shells out to ``signal-cli`` (end-to-end encrypted).

* inbound: a ``receive --json`` poll loop; each JSON envelope's
  ``dataMessage`` becomes an :class:`IncomingMessage`;
* outbound: ``send --message-from-stdin`` so message text never appears in a
  process argument list;
* the binary path is verified at startup — a missing binary fails fast with
  a clear error instead of pretending to run;
* ``privacy == "e2e"``: the gateway strips message content from the log.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from typing import Any

from dream.connectivity.base import OnMessage, PlatformAdapter
from dream.connectivity.models import IncomingMessage, utc_now

logger = logging.getLogger(__name__)

RECEIVE_TIMEOUT_SECONDS = 25
RECEIVE_CYCLE_SLEEP = 0.5
ENVELOPE_KEY = "envelope"


class SignalCliError(RuntimeError):
    """A signal-cli invocation or configuration failure."""


class SignalCli:
    """Standard-library wrapper around the ``signal-cli`` binary (seam)."""

    def __init__(self, path: str, account: str | None = None) -> None:
        self.path = str(path or "signal-cli")
        self.account = account

    def resolve(self) -> str:
        """Return the absolute binary path, raising if it does not exist."""
        resolved = shutil.which(self.path)
        if resolved is None and os.path.isfile(self.path):
            resolved = self.path
        if resolved is None:
            raise SignalCliError(
                f"signal-cli not found at {self.path!r}; install it and set "
                "signal_cli_path in the Signal config"
            )
        return resolved

    def _run(
        self,
        arguments: list[str],
        *,
        stdin_text: str | None = None,
        timeout: int = 60,
    ) -> str:
        binary = self.resolve()
        command = [binary, *arguments]
        if self.account:
            command[1:1] = ["-a", str(self.account)]
        try:
            completed = subprocess.run(
                command,
                input=stdin_text.encode("utf-8") if stdin_text is not None else None,
                capture_output=True,
                timeout=timeout,
                check=True,
            )
        except FileNotFoundError as exc:
            raise SignalCliError(f"signal-cli binary not found: {self.path!r}") from exc
        except subprocess.TimeoutExpired as exc:
            raise SignalCliError("signal-cli timed out") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or b"").decode("utf-8", "replace").strip()
            raise SignalCliError(f"signal-cli failed: {detail or exc}") from exc
        return completed.stdout.decode("utf-8", "replace")

    def receive_json(self, timeout: int = RECEIVE_TIMEOUT_SECONDS) -> str:
        """Run ``receive --json``; returns its stdout (possibly empty)."""
        return self._run(
            ["receive", "--json", "--timeout", str(int(timeout))],
            timeout=int(timeout) + 15,
        )

    def send(self, recipient: str, text: str) -> None:
        """Send via ``--message-from-stdin`` (no message text on argv)."""
        self._run(["send", "--message-from-stdin", str(recipient)], stdin_text=text)


def _parse_envelopes(raw: str) -> list[dict[str, Any]]:
    """Parse signal-cli JSON output (array, single object, or NDJSON)."""
    raw = raw.strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = None
    if isinstance(parsed, list):
        envelopes = [item for item in parsed if isinstance(item, dict)]
    elif isinstance(parsed, dict):
        envelopes = [parsed]
    else:
        envelopes = []
        decoder = json.JSONDecoder()
        position = 0
        while position < len(raw):
            while position < len(raw) and raw[position].isspace():
                position += 1
            if position >= len(raw):
                break
            try:
                item, position = decoder.raw_decode(raw, position)
            except ValueError:
                break
            if isinstance(item, dict):
                envelopes.append(item)
    return envelopes


def _message_text(envelope: dict[str, Any]) -> str:
    """Extract the message body from a receive envelope (tolerant of shapes)."""
    data = envelope.get("dataMessage", {}) or {}
    text = data.get("message")
    if isinstance(text, str):
        return text
    # Older shapes carry the body under "body" or a nested sync message.
    body = data.get("body")
    if isinstance(body, str):
        return body
    sync = data.get("syncMessage", {}) or {}
    sent = sync.get("sentMessage", {}) or {}
    for key in ("message", "body"):
        if isinstance(sent.get(key), str) and sent[key]:
            return sent[key]
    return ""


def _message_source(envelope: dict[str, Any]) -> str:
    for key in ("sourceNumber", "sourceUuid", "source"):
        value = envelope.get(key)
        if value:
            return str(value)
    return ""


class SignalAdapter(PlatformAdapter):
    """signal-cli receive/send loop; content is never logged (e2e)."""

    platform_name = "signal"
    max_message_length = 4096
    supports_inline = True
    supports_attachments = False
    privacy = "e2e"

    def __init__(
        self,
        config: dict[str, Any],
        *,
        on_message: OnMessage,
        cli: SignalCli | None = None,
    ) -> None:
        super().__init__(config, on_message=on_message)
        self._cli = cli
        self._task: asyncio.Task[Any] | None = None
        self._stop_event = asyncio.Event()

    def _build_cli(self) -> SignalCli:
        if self._cli is not None:
            return self._cli
        cli = SignalCli(
            str(self._config.get("signal_cli_path") or "signal-cli"),
            str(self._config.get("account") or "") or None,
        )
        self._cli = cli
        return cli

    async def start(self) -> None:
        if self._task is not None:
            return
        try:
            cli = self._build_cli()
            cli.resolve()  # fail fast: no binary, no adapter
        except SignalCliError as exc:
            self._mark_error(str(exc))
            raise
        if not str(self._config.get("account") or ""):
            self._mark_error("signal account is not configured")
            raise SignalCliError("signal account is required")
        self._stop_event.clear()
        self._status.running = True
        self._status.connected = True
        self._status.error = None
        self._task = asyncio.create_task(self._receive_loop(), name="signal-receive")

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

    async def _receive_loop(self) -> None:
        cli = self._build_cli()
        while not self._stop_event.is_set():
            try:
                raw = await asyncio.to_thread(cli.receive_json, RECEIVE_TIMEOUT_SECONDS)
            except asyncio.CancelledError:
                raise
            except SignalCliError as exc:
                self._mark_error(str(exc), running=True)
                await asyncio.sleep(5.0)
                continue
            for envelope in _parse_envelopes(raw):
                await self._handle_envelope(envelope)
            await asyncio.sleep(RECEIVE_CYCLE_SLEEP)

    async def _handle_envelope(self, envelope: dict[str, Any]) -> None:
        inner = envelope.get(ENVELOPE_KEY, envelope) if isinstance(envelope, dict) else {}
        if not isinstance(inner, dict):
            return
        text = _message_text(inner)
        source = _message_source(inner)
        if not text or not source:
            return
        self._note_activity()
        await self.deliver(
            IncomingMessage(
                platform=self.platform_name,
                platform_user_id=source,
                platform_channel_id=None,
                text=text,
                message_id=str(inner.get("timestamp") or ""),
                timestamp=utc_now(),
                raw=dict(inner),
            )
        )

    # -- outbound ---------------------------------------------------------- #

    async def send_message(self, user_id: str, text: str, attachments: list | None = None) -> None:
        del attachments
        cli = self._build_cli()
        await asyncio.to_thread(cli.send, user_id, text)

    async def send_typing_indicator(self, user_id: str) -> None:
        del user_id  # Signal has no typing indicator over signal-cli


__all__ = [
    "SignalAdapter",
    "SignalCli",
    "SignalCliError",
    "_message_source",
    "_message_text",
    "_parse_envelopes",
]
