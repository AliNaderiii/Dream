"""Minimal RFC 6455 WebSocket client (asyncio, standard library only).

Serves the Discord gateway and Slack Socket Mode, which both need exactly one
WebSocket: text frames in, text/JSON frames out, heartbeat ping/pong, and
clean close. This module intentionally implements the protocol subset those
platforms use rather than the whole RFC:

* client-to-server frames are always masked (§5.3);
* server-to-server masked frames are rejected (§5.1);
* ping (0x9) is answered with pong (0xA) automatically;
* fragmented messages are reassembled, with control frames interleaved;
* payload lengths up to 64-bit are supported, bounded by ``max_message_bytes``.

Tests round-trip frames against a local asyncio echo server
(``tests/test_connectivity_websocket.py``).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import socket
import ssl
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlsplit

#: RFC 6455 §1.3: the fixed GUID used in the Sec-WebSocket-Accept hash.
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

#: Default cap on one reassembled message (16 MiB).
DEFAULT_MAX_MESSAGE_BYTES = 16 * 1024 * 1024

#: How long close() waits for the peer's close handshake before dropping
#: the transport anyway.
CLOSE_TIMEOUT_SECONDS = 5.0

_OP_CONTINUATION = 0x0
_OP_TEXT = 0x1
_OP_BINARY = 0x2
_OP_CLOSE = 0x8
_OP_PING = 0x9
_OP_PONG = 0xA


class WebSocketError(RuntimeError):
    """A protocol, transport, or handshake failure."""


class WebSocketClosed(WebSocketError):
    """The peer closed the connection (``code`` carries its close code)."""

    def __init__(self, code: int = 1006, reason: str = "") -> None:
        super().__init__(f"WebSocket closed: {code} {reason}".strip())
        self.code = code
        self.reason = reason


def _accept_key(client_key: str) -> str:
    """Compute the Sec-WebSocket-Accept value the server must echo."""
    # SHA-1 here is mandated by RFC 6455 §4.2.2 for the opening handshake; it is
    # not a security primitive, so mark it as such for static analysis.
    digest = hashlib.sha1(
        (client_key + _WS_GUID).encode("ascii"), usedforsecurity=False
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def _parse_url(url: str) -> tuple[str, int, str, bool]:
    """Split a ws(s):// URL into (host, port, resource, tls)."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
        raise WebSocketError(f"invalid WebSocket URL: {url!r}")
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    resource = parsed.path or "/"
    if parsed.query:
        resource += f"?{parsed.query}"
    return parsed.hostname, port, resource, parsed.scheme == "wss"


class WebSocketConnection:
    """One established WebSocket, owned by the connecting coroutine."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._max_message_bytes = max_message_bytes
        self._close_code: int | None = None
        self._close_reason = ""
        self._peer_closed = False
        #: Set when the peer closes (or EOF); lets close() wait for the
        #: close handshake before dropping the shared transport.
        self._peer_closed_event = asyncio.Event()
        self._reading = False

    # -- state ------------------------------------------------------------ #

    @property
    def closed(self) -> bool:
        return self._close_code is not None or self._writer.is_closing()

    @property
    def close_code(self) -> int | None:
        return self._close_code

    # -- send -------------------------------------------------------------- #

    async def _send_frame(self, opcode: int, payload: bytes = b"") -> None:
        if self.closed:
            raise WebSocketClosed(self._close_code or 1006, "already closed")
        length = len(payload)
        header = bytearray([0x80 | opcode])
        mask = os.urandom(4)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(length.to_bytes(2, "big"))
        else:
            header.append(0x80 | 127)
            header.extend(length.to_bytes(8, "big"))
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self._writer.write(bytes(header) + masked)
        try:
            await self._writer.drain()
        except (ConnectionError, OSError) as exc:
            raise WebSocketClosed(1006, "connection lost while sending") from exc

    async def send_text(self, text: str) -> None:
        """Send one UTF-8 text frame."""
        await self._send_frame(_OP_TEXT, text.encode("utf-8"))

    async def send_json(self, payload: Any) -> None:
        """Send one text frame carrying a JSON-encoded object."""
        await self.send_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    async def ping(self, payload: bytes = b"") -> None:
        await self._send_frame(_OP_PING, payload)

    # -- receive ---------------------------------------------------------- #

    async def recv(self) -> tuple[int, bytes]:
        """Read one complete message; returns ``(opcode, payload)``.

        Text messages return opcode 1 (payload is UTF-8 bytes); binary
        messages return opcode 2. Raises :class:`WebSocketClosed` when the
        peer closes or the transport dies.
        """
        opcode, payload = await self._read_message()
        return opcode, payload

    async def recv_text(self) -> str:
        """Read one text message; binary frames raise :class:`WebSocketError`."""
        opcode, payload = await self._read_message()
        if opcode != _OP_TEXT:
            raise WebSocketError(f"expected a text frame, got opcode {opcode}")
        return payload.decode("utf-8")

    async def recv_json(self) -> Any:
        """Read one text message and parse it as JSON."""
        return json.loads(await self.recv_text())

    async def _read_message(self) -> tuple[int, bytes]:
        """Read one message, tracking whether a read is in flight."""
        self._reading = True
        try:
            return await self._read_message_locked()
        finally:
            self._reading = False

    async def _read_message_locked(self) -> tuple[int, bytes]:
        first_opcode: int | None = None
        fragments: list[bytes] = []
        total = 0
        while True:
            fin, opcode, payload = await self._read_frame()
            if opcode == _OP_PING:
                await self._send_frame(_OP_PONG, payload)
                continue
            if opcode == _OP_PONG:
                continue
            if opcode == _OP_CLOSE:
                self._peer_closed = True
                self._peer_closed_event.set()
                close_code = 1000
                reason = ""
                if len(payload) >= 2:
                    close_code = int.from_bytes(payload[:2], "big")
                    reason = payload[2:].decode("utf-8", "replace")
                # Answer the close handshake, then surface it to the caller.
                try:
                    await self._send_frame(_OP_CLOSE, payload[:2])
                except WebSocketClosed:
                    pass
                self._close_code = close_code
                self._close_reason = reason
                raise WebSocketClosed(close_code, reason)
            if opcode == _OP_CONTINUATION:
                if first_opcode is None:
                    raise WebSocketError("continuation frame without a start frame")
            elif first_opcode is not None:
                raise WebSocketError("new data frame during a fragmented message")
            else:
                first_opcode = opcode
            total += len(payload)
            if total > self._max_message_bytes:
                raise WebSocketError("message exceeds max_message_bytes")
            fragments.append(payload)
            if fin:
                break
        payload = b"".join(fragments)
        if first_opcode == _OP_TEXT:
            payload.decode("utf-8")  # validate early; raises UnicodeDecodeError
        return first_opcode or _OP_TEXT, payload

    async def _read_frame(self) -> tuple[bool, int, bytes]:
        """Read one frame; returns ``(fin, opcode, payload)``."""
        reader = self._reader
        try:
            head = await reader.readexactly(2)
        except asyncio.IncompleteReadError as exc:
            self._peer_closed_event.set()
            raise WebSocketClosed(1006, "connection lost") from exc
        first, second = head
        fin = bool(first & 0x80)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        try:
            if length == 126:
                length = int.from_bytes(await reader.readexactly(2), "big")
            elif length == 127:
                length = int.from_bytes(await reader.readexactly(8), "big")
            if masked:
                await reader.readexactly(4)  # discard the mask; we reject below
            payload = await reader.readexactly(length)
        except asyncio.IncompleteReadError as exc:
            raise WebSocketClosed(1006, "connection lost mid-frame") from exc
        if masked:
            # RFC 6455 §5.1: a server MUST NOT mask frames to the client.
            raise WebSocketError("received a masked frame from the server")
        if opcode not in {
            _OP_CONTINUATION,
            _OP_TEXT,
            _OP_BINARY,
            _OP_CLOSE,
            _OP_PING,
            _OP_PONG,
        }:
            raise WebSocketError(f"unknown opcode {opcode}")
        return fin, opcode, payload

    # -- iteration -------------------------------------------------------- #

    def __aiter__(self) -> AsyncIterator[str]:
        return self

    async def __anext__(self) -> str:
        while True:
            try:
                return await self.recv_text()
            except WebSocketClosed as exc:
                if self._peer_closed:
                    raise StopAsyncIteration from exc
                raise

    # -- close ------------------------------------------------------------ #

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Send a close frame, await the peer's close, then drop the socket.

        Idempotent. Closing an asyncio ``StreamWriter`` tears down both
        directions of the transport, so the peer's close reply (or EOF) is
        waited for first, bounded by :data:`CLOSE_TIMEOUT_SECONDS`.
        """
        if self.closed:
            return
        payload = code.to_bytes(2, "big") + reason.encode("utf-8")
        try:
            await self._send_frame(_OP_CLOSE, payload)
        except WebSocketError:
            pass
        if self._reading:
            # A concurrent reader owns the socket; it will observe the peer's
            # close frame (or EOF) and set the event.
            try:
                await asyncio.wait_for(
                    self._peer_closed_event.wait(), timeout=CLOSE_TIMEOUT_SECONDS
                )
            except TimeoutError:
                pass
        else:
            # No reader in flight: consume frames ourselves until the
            # handshake completes or the bound expires.
            loop = asyncio.get_running_loop()
            deadline = loop.time() + CLOSE_TIMEOUT_SECONDS
            while not self._peer_closed_event.is_set():
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(self._read_message(), timeout=remaining)
                except (WebSocketClosed, WebSocketError, TimeoutError):
                    break
        self._close_code = code
        self._close_reason = reason
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except (ConnectionError, OSError):
            pass


async def connect(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
    max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
) -> WebSocketConnection:
    """Open a WebSocket to *url* (``ws://`` or ``wss://``).

    *headers* are merged into the handshake (used for e.g. Origin). The
    handshake, including the Sec-WebSocket-Accept check, is performed by this
    function before the connection is returned.
    """
    host, port, resource, tls = _parse_url(url)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    handshake = [
        f"GET {resource} HTTP/1.1",
        f"Host: {host}:{port}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key}",
        "Sec-WebSocket-Version: 13",
    ]
    for name, value in (headers or {}).items():
        handshake.append(f"{name}: {value}")
    request = ("\r\n".join(handshake) + "\r\n\r\n").encode("ascii")

    ssl_context = ssl.create_default_context() if tls else None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ssl_context), timeout=timeout
        )
    except (OSError, socket.gaierror) as exc:
        raise WebSocketError(f"could not connect to {url!r}: {exc}") from exc
    except TimeoutError as exc:
        raise WebSocketError(f"connection to {url!r} timed out") from exc

    try:
        writer.write(request)
        await asyncio.wait_for(writer.drain(), timeout=timeout)
        status_line = await asyncio.wait_for(reader.readline(), timeout=timeout)
        if not status_line or b" 101 " not in status_line:
            raise WebSocketError(
                f"upgrade refused: {status_line.decode('ascii', 'replace').strip()}"
            )
        response_headers: dict[str, str] = {}
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=timeout)
            if line in {b"\r\n", b"\n", b""}:
                break
            name, separator, value = line.decode("ascii", "replace").partition(":")
            if separator:
                response_headers[name.strip().lower()] = value.strip()
        expected = _accept_key(key)
        if response_headers.get("sec-websocket-accept") != expected:
            raise WebSocketError("handshake failed: Sec-WebSocket-Accept mismatch")
    except WebSocketError:
        writer.close()
        raise
    except (asyncio.IncompleteReadError, TimeoutError) as exc:
        writer.close()
        raise WebSocketError(f"handshake with {url!r} failed: {exc}") from exc

    return WebSocketConnection(reader, writer, max_message_bytes=max_message_bytes)
