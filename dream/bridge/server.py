"""The Dream bridge RPC server.

A newline-delimited JSON-RPC 2.0 server that reads requests from stdin and
writes responses/notifications to stdout (see ``docs/bridge/protocol.md``).

Design goals:

* **Robust.** Malformed JSON, oversize payloads, unknown methods, and handler
  exceptions never tear down the connection — each is reported as a single
  error response and the loop continues.
* **Streaming.** A handler that returns an async generator streams its chunks
  as ``stream.*`` notifications, then a final ``result``.
* **Backpressure.** A bounded buffer + concurrency cap keep memory flat under
  load; the frontend is told to retry via ``RESOURCE_EXHAUSTED``.
* **Testable.** Transport is injectable: tests pass a list-backed reader and a
  list-capturing writer instead of stdin/stdout.

Transport is pluggable via :class:`LineReader` / :class:`LineWriter`. The
production wiring (:class:`StdinLineReader`, :class:`StdoutLineWriter`) is used
by :func:`run_stdio` and the ``dream --bridge`` entry point.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
import threading
from collections.abc import AsyncIterator
from typing import Any, Protocol

from dream.bridge.errors import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    RESOURCE_EXHAUSTED,
    error_from_code,
    serialise_error,
)
from dream.bridge.methods import BridgeMethods

logger = logging.getLogger("dream.bridge")

#: Emitted once at startup, before any JSON message.
PROTOCOL_HEADER = "DREAM-PROTOCOL: 1.0"

DEFAULT_MAX_LINE_BYTES = 10 * 1024 * 1024  # 10 MiB, per §1.2
DEFAULT_CONCURRENCY = 16  # §6.1
DEFAULT_QUEUE_CAP = 128  # §6.1


# --------------------------------------------------------------------------- #
# Transport abstractions.
# --------------------------------------------------------------------------- #


class LineWriter(Protocol):
    """Anything the server can send a single framed line through."""

    async def write(self, line: str) -> None: ...


class LineReader(Protocol):
    """An async iterator of incoming lines (no trailing newline)."""

    def __aiter__(self) -> AsyncIterator[str]: ...


class StdoutLineWriter:
    """Writes one line at a time to ``stdout`` under a lock, then flushes.

    A lock is required because the server is concurrent: a streaming handler
    and an unrelated response can race to write. Each ``write`` is one
    ``print``-equivalent and is atomic with respect to other writers.
    """

    def __init__(self, stream=None) -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._lock = threading.Lock()

    async def write(self, line: str) -> None:
        # stdout is line-buffered or block-buffered; a tiny write never blocks
        # meaningfully, but run it off the event loop for uniformity.
        def _emit() -> None:
            with self._lock:
                self._stream.write(line + "\n")
                self._stream.flush()

        await asyncio.to_thread(_emit)


class StdinLineReader:
    """Reads stdin on a daemon thread, feeding a bounded asyncio queue.

    The bound gives real backpressure: when the buffer is full the thread stops
    reading, the OS pipe fills, and the frontend (the writer) blocks on its end
    — so the sidecar never buffers an unbounded backlog in memory.
    """

    def __init__(self, *, maxsize: int = DEFAULT_QUEUE_CAP, stream=None) -> None:
        self._stream = stream if stream is not None else sys.stdin
        self._maxsize = maxsize
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[str | None] | None = None
        self._slots: threading.Semaphore | None = None
        self._thread: threading.Thread | None = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._queue = asyncio.Queue(maxsize=self._maxsize)
        # One slot per buffered line; the reader thread blocks here when full.
        self._slots = threading.Semaphore(self._maxsize)
        self._thread = threading.Thread(target=self._pump, name="bridge-stdin", daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        assert self._loop is not None and self._queue is not None and self._slots is not None
        try:
            for raw in self._stream:
                self._slots.acquire()  # backpressure
                line = raw.rstrip("\n").rstrip("\r")
                self._loop.call_soon_threadsafe(self._queue.put_nowait, line)
        except Exception as exc:  # never let the reader thread die silently
            logger.exception("stdin reader failed: %s", exc)
        finally:
            # Sentinel: None signals EOF to the consumer.
            self._loop.call_soon_threadsafe(self._queue.put_nowait, None)

    def release_slot(self) -> None:
        """Called by the consumer after it has taken a line, to free a buffer slot."""
        if self._slots is not None:
            self._slots.release()

    async def __aiter__(self) -> AsyncIterator[str]:
        assert self._queue is not None
        while True:
            line = await self._queue.get()
            if line is None:
                return
            yield line
            self.release_slot()


# --------------------------------------------------------------------------- #
# The server.
# --------------------------------------------------------------------------- #


class BridgeServer:
    """Wires transport to the method dispatcher with framing and supervision."""

    def __init__(
        self,
        methods: BridgeMethods,
        *,
        reader: LineReader | None = None,
        writer: LineWriter | None = None,
        max_line_bytes: int = DEFAULT_MAX_LINE_BYTES,
        concurrency: int = DEFAULT_CONCURRENCY,
        queue_cap: int = DEFAULT_QUEUE_CAP,
    ) -> None:
        self.methods = methods
        self._reader = reader
        self._writer = writer or StdoutLineWriter()
        self._max_line_bytes = max_line_bytes
        self._concurrency = asyncio.Semaphore(concurrency)
        self._queue_cap = queue_cap
        self._tasks: set[asyncio.Task[Any]] = set()
        self._running = asyncio.Event()
        self._header_sent = False

    # -- public ----------------------------------------------------------- #

    async def serve(self) -> None:
        """Emit the header, then read and dispatch until EOF or shutdown."""
        self._running.set()
        if not self._header_sent:
            await self._writer.write(PROTOCOL_HEADER)
            self._header_sent = True
        if self._reader is None:
            return
        async for line in self._reader:
            if not self._running.is_set():
                break
            # §6.1 backpressure: reject bursts beyond the queue cap rather than
            # growing memory unbounded. The client retries with backoff. The id
            # is left null because the line has not been parsed yet — this is a
            # connection-level resource signal, not a per-request failure.
            if len(self._tasks) >= self._queue_cap:
                await self._send(
                    error_from_code(
                        RESOURCE_EXHAUSTED,
                        "too many in-flight requests; retry with backoff",
                    )
                )
                continue
            task = asyncio.create_task(self._process(line))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        # Drain in-flight tasks on EOF.
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    def request_shutdown(self) -> None:
        self._running.clear()

    async def stop(self) -> None:
        """Stop accepting new lines and drain in-flight work (graceful shutdown)."""
        self.request_shutdown()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    # -- per-line processing ---------------------------------------------- #

    async def _process(self, line: str) -> None:
        await self._handle_line(line)

    async def _handle_line(self, line: str) -> None:
        # §1.2 size guard.
        if len(line.encode("utf-8", "replace")) > self._max_line_bytes:
            await self._send(error_from_code(INVALID_REQUEST, "payload too large"))
            return
        if not line.strip():
            return  # lenient: ignore blank lines

        try:
            message = json.loads(line)
        except ValueError:
            await self._send(error_from_code(PARSE_ERROR, "malformed JSON"))
            return

        if not isinstance(message, dict):
            await self._send(error_from_code(INVALID_REQUEST, "request must be a JSON object"))
            return

        request_id = message.get("id")
        is_request = "id" in message
        method = message.get("method")

        if message.get("jsonrpc") not in ("2.0", None):
            await self._send(
                error_from_code(INVALID_REQUEST, "jsonrpc must be \"2.0\"", request_id=request_id)
            )
            return
        if not isinstance(method, str) or not method:
            await self._send(
                error_from_code(INVALID_REQUEST, "method must be a non-empty string",
                                request_id=request_id)
            )
            return

        handler = self.methods.handlers.get(method)
        if handler is None:
            if is_request:
                await self._send(
                    error_from_code(
                        METHOD_NOT_FOUND, f"method not found: {method}",
                        request_id=request_id, method=method,
                    )
                )
            return

        params = message.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            await self._send(
                error_from_code(INVALID_PARAMS, "params must be an object", request_id=request_id)
            )
            return

        # Bound concurrent handler execution; rejection happens via the slot
        # semaphore already acquired in serve(), so here we only gate CPU.
        async with self._concurrency:
            await self._dispatch(handler, params, method, request_id, is_request)

    async def _dispatch(self, handler, params, method, request_id, is_request) -> None:
        try:
            result = handler(params)  # call synchronously; inspect the return
        except Exception as exc:  # handler raised before returning (sync path)
            if is_request:
                await self._send(serialise_error(exc, request_id))
            return

        try:
            from dream.bridge.streams import Stream, ensure_awaitable

            value = await ensure_awaitable(result)
        except Exception as exc:
            if is_request:
                await self._send(serialise_error(exc, request_id))
            return

        if isinstance(value, Stream):
            await self._run_streaming(value, method, request_id, is_request)
            return

        if is_request:
            await self._send(self._result_response(request_id, value))

    async def _run_streaming(self, stream, method, request_id, is_request) -> None:
        """Drive a :class:`Stream`, emitting stream.* notifications + final result."""
        if is_request:
            await self._send(self._notification("stream.start", {"id": request_id}))
        failed: BaseException | None = None
        try:
            async for chunk in stream.chunks:
                if is_request and isinstance(chunk, dict):
                    payload = {"id": request_id, **chunk}
                    await self._send(self._notification("stream.chunk", payload))
        except BaseException as exc:  # noqa: BLE001 — report every failure
            failed = exc

        if is_request:
            await self._send(self._notification("stream.end", {"id": request_id}))
            if failed is not None:
                await self._send(serialise_error(failed, request_id))
            else:
                await self._send(self._result_response(request_id, stream.final))

    # -- response builders ------------------------------------------------ #

    @staticmethod
    def _result_response(request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _notification(method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "method": method, "params": params}

    async def _send(self, message: dict[str, Any]) -> None:
        try:
            line = json.dumps(message, ensure_ascii=False)
        except (TypeError, ValueError):
            line = json.dumps(
                error_from_code(0, "result was not JSON-serialisable", request_id=message.get("id"))
            )
        await self._writer.write(line)


# --------------------------------------------------------------------------- #
# Test transports.
# --------------------------------------------------------------------------- #


class MemoryLineWriter:
    """Captures every written line — used by the unit/integration tests."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    async def write(self, line: str) -> None:
        self.lines.append(line)


class ListLineReader:
    """Yields a fixed list of lines then stops — used by the tests."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    async def __aiter__(self) -> AsyncIterator[str]:
        for line in self._lines:
            yield line


# --------------------------------------------------------------------------- #
# Entry point.
# --------------------------------------------------------------------------- #


def install_signal_handlers(server: BridgeServer, loop: asyncio.AbstractEventLoop) -> None:
    """Request graceful shutdown on SIGINT/SIGTERM (POSIX; no-op on Windows)."""

    def _handler(*_: Any) -> None:
        logger.info("shutdown signal received")
        loop.call_soon_threadsafe(server.request_shutdown)

    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(sig, _handler)
            except (NotImplementedError, RuntimeError):
                # Windows / non-main thread: fall back to the default handler.
                signal.signal(sig, lambda *a: loop.call_soon_threadsafe(server.request_shutdown))


async def serve_forever(methods: BridgeMethods | None = None, **kwargs: Any) -> None:
    """Run the stdio server until stdin closes or a shutdown signal arrives."""
    methods = methods or BridgeMethods()
    loop = asyncio.get_running_loop()
    reader = StdinLineReader()
    reader.start(loop)
    server = BridgeServer(methods, reader=reader, **kwargs)
    install_signal_handlers(server, loop)
    # The scheduler daemon needs a running loop, so it starts here rather than
    # in the constructor; ``aclose`` stops it (and any live subagent) before the
    # loop goes away.
    methods.start_scheduler()
    try:
        await server.serve()
    finally:
        await methods.aclose()


def run_stdio(argv: list[str] | None = None) -> int:
    """Synchronous entry point used by ``dream --bridge``.

    Returns 0 on clean shutdown. Configurable via env (see method defaults).
    """
    logging.basicConfig(
        level=os_env_log_level(),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(serve_forever())
    except KeyboardInterrupt:
        return 0
    return 0


def os_env_log_level() -> int:
    import os

    level = os.environ.get("DREAM_BRIDGE_LOG", "INFO").upper()
    return getattr(logging, level, logging.INFO)


__all__ = [
    "BridgeServer",
    "LineReader",
    "LineWriter",
    "ListLineReader",
    "MemoryLineWriter",
    "PROTOCOL_HEADER",
    "StdinLineReader",
    "StdoutLineWriter",
    "install_signal_handlers",
    "run_stdio",
    "serve_forever",
]
