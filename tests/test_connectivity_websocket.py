"""RFC 6455 client tests against a local asyncio WebSocket server."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import socket

import pytest

from dream.connectivity.websocket import WebSocketClosed, WebSocketError, connect

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _accept(key: str) -> str:
    digest = hashlib.sha1((key + _GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _frame(opcode: int, payload: bytes, *, fin: bool = True) -> bytes:
    """Build an unmasked server frame."""
    first = (0x80 if fin else 0x00) | opcode
    length = len(payload)
    header = bytearray([first])
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header.extend(length.to_bytes(2, "big"))
    else:
        header.append(127)
        header.extend(length.to_bytes(8, "big"))
    return bytes(header) + payload


async def _read_client_frame(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    """Read one masked client frame (unmasking it)."""
    head = await reader.readexactly(2)
    opcode = head[0] & 0x0F
    length = head[1] & 0x7F
    if length == 126:
        length = int.from_bytes(await reader.readexactly(2), "big")
    elif length == 127:
        length = int.from_bytes(await reader.readexactly(8), "big")
    mask = await reader.readexactly(4)
    payload = await reader.readexactly(length)
    return opcode, bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))


class _EchoProtocol:
    """The behaviour the test server runs after the handshake."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer

    async def run(self) -> None:
        while True:
            opcode, payload = await _read_client_frame(self.reader)
            if opcode == 0x8:  # close: answer and finish
                self.writer.write(_frame(0x8, payload[:2]))
                await self.writer.drain()
                break
            if opcode == 0x9:  # ping → pong
                self.writer.write(_frame(0xA, payload))
                await self.writer.drain()
                continue
            if opcode == 0x1:
                self.writer.write(_frame(0x1, payload))
                await self.writer.drain()


class _ScriptedProtocol:
    """Runs a fixed frame script handed in by the test."""

    #: Frames to write once connected; subclasses may override run() instead.
    script: list[bytes] = []

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer

    async def run(self) -> None:
        for frame in self.script:
            self.writer.write(frame)
            await self.writer.drain()


async def _start_server(handler) -> tuple[asyncio.AbstractServer, int]:
    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readline()  # request line
        headers: dict[str, str] = {}
        while True:
            line = await reader.readline()
            if line in {b"\r\n", b"\n", b""}:
                break
            name, separator, value = line.decode("ascii", "replace").partition(":")
            if separator:
                headers[name.strip().lower()] = value.strip()
        key = headers.get("sec-websocket-key", "")
        accept = _accept(key)
        writer.write(
            (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
            ).encode("ascii")
        )
        await writer.drain()
        await handler(reader, writer).run()
        writer.close()

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    return server, port


async def _connect(port: int, **kwargs):
    return await connect(f"ws://127.0.0.1:{port}/", **kwargs)


def test_text_and_json_round_trip():
    async def scenario() -> None:
        server, port = await _start_server(_EchoProtocol)
        try:
            ws = await _connect(port)
            await ws.send_text("hello connectivity")
            assert await ws.recv_text() == "hello connectivity"
            await ws.send_json({"op": 2, "d": {"token": "x"}})
            assert await ws.recv_json() == {"op": 2, "d": {"token": "x"}}
            await ws.close()
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_iterator_yields_text_messages():
    async def scenario() -> None:
        server, port = await _start_server(_EchoProtocol)
        try:
            ws = await _connect(port)
            for word in ("one", "two", "three"):
                await ws.send_text(word)
            received = []
            async for text in ws:
                received.append(text)
                if len(received) == 3:
                    await ws.close()
            assert received == ["one", "two", "three"]
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_ping_is_answered_and_long_payloads_round_trip():
    async def scenario() -> None:
        class PingThenEcho(_ScriptedProtocol):
            async def run(self) -> None:  # pragma: no cover - tiny shim
                self.writer.write(_frame(0x9, b"probe"))
                await self.writer.drain()
                opcode, payload = await _read_client_frame(self.reader)
                assert opcode == 0xA and payload == b"probe"  # client ponged
                big = "ز" * 70000  # 140 KB of UTF-8 → 64-bit length path
                self.writer.write(_frame(0x1, big.encode("utf-8")))
                await self.writer.drain()

        server, port = await _start_server(PingThenEcho)
        try:
            ws = await _connect(port)
            text = await ws.recv_text()
            assert text == "ز" * 70000
            await ws.close()
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_fragmented_message_is_reassembled():
    async def scenario() -> None:
        class Fragments(_ScriptedProtocol):
            async def run(self) -> None:  # pragma: no cover - tiny shim
                payload = b"fragmented message"
                self.writer.write(_frame(0x1, payload[:6], fin=False))
                self.writer.write(_frame(0x0, payload[6:], fin=True))
                await self.writer.drain()

        server, port = await _start_server(Fragments)
        try:
            ws = await _connect(port)
            assert await ws.recv_text() == "fragmented message"
            await ws.close()
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_peer_close_surfaces_code_and_reason():
    async def scenario() -> None:
        class Closer(_ScriptedProtocol):
            async def run(self) -> None:  # pragma: no cover - tiny shim
                self.writer.write(_frame(0x8, (1000).to_bytes(2, "big") + b"bye"))
                await self.writer.drain()

        server, port = await _start_server(Closer)
        try:
            ws = await _connect(port)
            with pytest.raises(WebSocketClosed) as exc:
                await ws.recv_text()
            assert exc.value.code == 1000
            assert exc.value.reason == "bye"
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_handshake_rejection_raises():
    async def scenario() -> None:
        async def _refuse(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            await reader.readline()  # consume the request line; respond immediately
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(_refuse, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        try:
            with pytest.raises(WebSocketError):
                await _connect(port)
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_invalid_url_and_unreachable_host_raise():
    with pytest.raises(WebSocketError):
        asyncio.run(connect("http://example.com/"))
    # A port with nothing listening fails fast.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    with pytest.raises(WebSocketError):
        asyncio.run(connect(f"ws://127.0.0.1:{port}/", timeout=2))
