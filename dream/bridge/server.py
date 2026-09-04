"""The Dream bridge RPC server.

A newline-delimited JSON-RPC 2.0 server that reads requests from stdin and
writes responses/notifications to stdout (see ``docs/bridge/protocol.md``).

Design goals:

* **Robust.** Malformed JSON, oversize payloads, unknown methods, and handler
  exceptions never tear down the connection — each is reported as a single
  error response and the loop continues.
* **Bounded.** A line is never buffered past :data:`DEFAULT_MAX_LINE_BYTES`:
  the stdin reader discards an oversized line *while reading it* and reports
  it as a marker, so a hostile peer cannot force an allocation. The EOF drain
  is bounded too (:data:`DEFAULT_DRAIN_SECONDS`).
* **Streaming.** A handler that returns a :class:`~dream.bridge.streams.Stream`
  streams its chunks as ``stream.*`` notifications, then a final ``result``.
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
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from dream.bridge.errors import (
    INTERNAL_ERROR,
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
#: Upper bound on the EOF drain (§6.2): in-flight handlers that have not
#: finished by then are cancelled so stdin EOF always ends the process.
DEFAULT_DRAIN_SECONDS = 5.0
#: Longest ``method`` name echoed back in a ``METHOD_NOT_FOUND`` error. The
#: rest of the (untrusted) string never leaves the process.
MAX_ECHOED_METHOD_CHARS = 128


class OversizedLine:
    """Marker yielded by a reader for a line it refused to buffer (§1.2).

    Carries only the observed byte count — never any of the payload.
    """

    __slots__ = ("size",)

    def __init__(self, size: int) -> None:
        self.size = size

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"OversizedLine(size={self.size})"


# --------------------------------------------------------------------------- #
# Transport abstractions.
# --------------------------------------------------------------------------- #


class LineWriter(Protocol):
    """Anything the server can send a single framed line through."""

    async def write(self, line: str) -> None: ...


class LineReader(Protocol):
    """An async iterator of incoming lines (no trailing newline).

    A reader that enforces its own size bound may yield :class:`OversizedLine`
    markers in place of lines it refused to buffer.
    """

    def __aiter__(self) -> AsyncIterator[str | OversizedLine]: ...


class StdoutLineWriter:
    """Writes one line at a time to ``stdout`` under a lock, then flushes.

    A lock is required because the server is concurrent: a streaming handler
    and an unrelated response can race to write. Each ``write`` is one
    ``print``-equivalent and is atomic with respect to other writers.

    Writes run on a **dedicated** single worker thread rather than the default
    executor: the default pool is shared with blocking turns
    (``asyncio.to_thread(dream.run)``) and could otherwise starve responses —
    including heartbeat replies — while every worker is busy.
    """

    def __init__(self, stream=None) -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bridge-stdout")

    async def write(self, line: str) -> None:
        def _emit() -> None:
            with self._lock:
                self._stream.write(line + "\n")
                self._stream.flush()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, _emit)

    def close(self) -> None:
        """Release the writer thread (idempotent)."""
        self._executor.shutdown(wait=False)


class StdinLineReader:
    """Reads stdin on a daemon thread, feeding a bounded asyncio queue.

    The bound gives real backpressure: when the buffer is full the thread stops
    reading, the OS pipe fills, and the frontend (the writer) blocks on its end
    — so the sidecar never buffers an unbounded backlog in memory.

    Size bound (§1.2): lines are read from the **binary** stream with
    ``readline(limit)``. A line longer than ``max_line_bytes`` is discarded up
    to its newline without ever being held in full, and an
    :class:`OversizedLine` marker is queued in its place. Bytes that are not
    valid UTF-8 are replaced rather than allowed to kill the reader thread.
    """

    def __init__(
        self,
        *,
        maxsize: int = DEFAULT_QUEUE_CAP,
        max_line_bytes: int = DEFAULT_MAX_LINE_BYTES,
        stream=None,
    ) -> None:
        self._stream = stream if stream is not None else _binary_stdin()
        self._maxsize = maxsize
        self._max_line_bytes = max_line_bytes
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[str | OversizedLine | None] | None = None
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
        loop, queue, slots = self._loop, self._queue, self._slots
        if loop is None or queue is None or slots is None:
            raise RuntimeError("StdinLineReader.start() must be called before reading")
        try:
            for item in read_bounded_lines(self._stream, self._max_line_bytes):
                slots.acquire()  # backpressure
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception as exc:  # never let the reader thread die silently
            logger.exception("stdin reader failed: %s", type(exc).__name__)
        finally:
            # Sentinel: None signals EOF to the consumer.
            loop.call_soon_threadsafe(queue.put_nowait, None)

    def release_slot(self) -> None:
        """Called by the consumer after it has taken a line, to free a buffer slot."""
        if self._slots is not None:
            self._slots.release()

    async def __aiter__(self) -> AsyncIterator[str | OversizedLine]:
        if self._queue is None:
            raise RuntimeError("StdinLineReader.start() must be called before reading")
        while True:
            line = await self._queue.get()
            if line is None:
                return
            yield line
            self.release_slot()


def _binary_stdin():
    """The byte-level stdin, falling back to the text object when absent."""
    buffer = getattr(sys.stdin, "buffer", None)
    return buffer if buffer is not None else sys.stdin


def read_bounded_lines(stream, max_line_bytes: int):
    """Yield decoded lines from a binary *stream*, never buffering past the bound.

    ``readline(limit)`` returns at most ``limit`` bytes; a chunk that does not
    end in ``\\n`` (and is not the final unterminated line) means the line is
    longer than the bound. The remainder is consumed and dropped chunk by
    chunk, and one :class:`OversizedLine` is yielded instead. The peak memory
    held for any single line is therefore ``max_line_bytes + 1``.

    Text streams are accepted for tests (``limit`` counts characters there).
    """
    limit = max_line_bytes + 1  # +1: room for the newline of a max-size line
    while True:
        chunk = stream.readline(limit)
        if not chunk:
            return  # EOF
        newline = b"\n" if isinstance(chunk, bytes) else "\n"
        if chunk.endswith(newline):
            yield _decode_line(chunk)
            continue
        if len(chunk) < limit:
            # Final line without a trailing newline (§1.2: parsed if non-empty).
            yield _decode_line(chunk)
            return
        # Over the bound: discard the rest of this line without keeping it.
        size = len(chunk)
        while True:
            more = stream.readline(limit)
            if not more:
                yield OversizedLine(size)
                return
            size += len(more)
            if more.endswith(newline):
                break
        yield OversizedLine(size)


def _decode_line(chunk) -> str:
    text = chunk.decode("utf-8", "replace") if isinstance(chunk, bytes) else chunk
    return text.rstrip("\n").rstrip("\r")


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
        drain_seconds: float = DEFAULT_DRAIN_SECONDS,
    ) -> None:
        self.methods = methods
        self._reader = reader
        self._writer = writer or StdoutLineWriter()
        self._max_line_bytes = max_line_bytes
        self._concurrency = asyncio.Semaphore(concurrency)
        self._queue_cap = queue_cap
        self._drain_seconds = drain_seconds
        self._tasks: set[asyncio.Task[Any]] = set()
        self._running = asyncio.Event()
        self._header_sent = False
        self._transport_failed = False

    # -- public ----------------------------------------------------------- #

    async def serve(self) -> None:
        """Emit the header, then read and dispatch until EOF or shutdown."""
        self._running.set()
        if not self._header_sent:
            await self._send_raw(PROTOCOL_HEADER)
            self._header_sent = True
        if self._reader is None:
            return
        try:
            async for line in self._reader:
                if not self._running.is_set():
                    break
                # §6.1 backpressure: reject bursts beyond the queue cap rather
                # than growing memory unbounded. The client retries with
                # backoff. The id is left null because the line has not been
                # parsed yet — this is a connection-level resource signal, not
                # a per-request failure.
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
        finally:
            # Drain in-flight tasks on EOF — bounded (§6.2).
            await self._drain()

    def request_shutdown(self) -> None:
        self._running.clear()

    async def stop(self) -> None:
        """Stop accepting new lines and drain in-flight work (graceful shutdown)."""
        self.request_shutdown()
        await self._drain()

    # -- per-line processing ---------------------------------------------- #

    async def _drain(self) -> None:
        """Wait up to ``drain_seconds`` for in-flight work, then cancel the rest."""
        if not self._tasks:
            return
        pending = set(self._tasks)
        _done, remaining = await asyncio.wait(pending, timeout=self._drain_seconds)
        if remaining:
            logger.warning(
                "bridge: cancelling %d request(s) still in flight after the %.1fs drain",
                len(remaining),
                self._drain_seconds,
            )
            for task in remaining:
                task.cancel()
            await asyncio.gather(*remaining, return_exceptions=True)

    async def _process(self, line: str | OversizedLine) -> None:
        if isinstance(line, OversizedLine):
            await self._send(error_from_code(INVALID_REQUEST, "payload too large"))
            return
        await self._handle_line(line)

    async def _handle_line(self, line: str) -> None:
        # §1.2 size guard for readers that do not enforce the bound themselves.
        # Character count is a lower bound on the byte count, so the encode
        # (a copy) only happens when the line could plausibly be near the cap.
        if len(line) > self._max_line_bytes or (
            len(line) * 4 > self._max_line_bytes
            and len(line.encode("utf-8", "replace")) > self._max_line_bytes
        ):
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

        is_request = "id" in message
        request_id = message.get("id")
        # JSON-RPC 2.0 §4: id is a string, a number, or null. Booleans (a
        # subclass of int in Python), floats, objects and arrays are rejected
        # so an untrusted id can never be echoed back in an unexpected shape.
        if is_request and not _is_valid_id(request_id):
            await self._send(
                error_from_code(INVALID_REQUEST, "id must be a string, an integer, or null")
            )
            return
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
                shown = method[:MAX_ECHOED_METHOD_CHARS]
                await self._send(
                    error_from_code(
                        METHOD_NOT_FOUND, f"method not found: {shown}",
                        request_id=request_id, method=shown,
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
        except asyncio.CancelledError:
            # Shutdown drain or task cancellation: the peer is going away (or
            # has gone); do not attempt a response, and let the cancel propagate.
            raise
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
        except asyncio.CancelledError:
            raise  # never swallow a cancellation — see _dispatch
        except Exception as exc:  # report every handler failure to the peer
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
        # ``allow_nan=False``: ``NaN``/``Infinity`` are not JSON. Emitting them
        # would produce a line the peer cannot parse, which would silently
        # strand the request until the client-side timeout.
        try:
            line = json.dumps(message, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError):
            line = json.dumps(
                error_from_code(
                    INTERNAL_ERROR,
                    "result was not JSON-serialisable",
                    request_id=message.get("id"),
                )
            )
        await self._send_raw(line)

    async def _send_raw(self, line: str) -> None:
        if self._transport_failed:
            return  # the peer is gone; nothing more can be delivered
        try:
            await self._writer.write(line)
        except OSError as exc:
            # Broken pipe / closed stdout: the frontend has gone away. Stop
            # accepting new work; the reader hits EOF shortly after (the
            # supervisor closes both ends together) and ``serve`` returns.
            self._transport_failed = True
            logger.warning("bridge: stdout write failed (%s); shutting down", type(exc).__name__)
            self.request_shutdown()


def _is_valid_id(value: Any) -> bool:
    if value is None or isinstance(value, str):
        return True
    return isinstance(value, int) and not isinstance(value, bool)


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

    def __init__(self, lines: list[str | OversizedLine]) -> None:
        self._lines = list(lines)

    async def __aiter__(self) -> AsyncIterator[str | OversizedLine]:
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
    reader = StdinLineReader(max_line_bytes=kwargs.get("max_line_bytes", DEFAULT_MAX_LINE_BYTES))
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
    # SEC Stage C (G-17): every bridge log line is value-scanned before it
    # reaches stderr — a key must never ride the wire or the logs.
    from dream.security.secrets import install_redaction_filter

    install_redaction_filter("dream")
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
    "OversizedLine",
    "PROTOCOL_HEADER",
    "StdinLineReader",
    "StdoutLineWriter",
    "install_signal_handlers",
    "read_bounded_lines",
    "run_stdio",
    "serve_forever",
]
