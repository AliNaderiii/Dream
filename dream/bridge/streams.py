"""Streaming helpers for the Dream bridge.

A handler that wants to stream returns an *async generator*. The server's
dispatcher detects this and turns each ``yield`` into a ``stream.*``
notification, and the generator's return value into the final ``result``
(see ``docs/bridge/protocol.md`` §5.1).

This module provides:

* :func:`is_async_generator` — detect streaming handlers/results.
* :func:`tokenise` — split text into roughly token-sized pieces (word + trailing
  whitespace), language-agnostic so Persian and English chunk the same way.
* :func:`stream_chunks` — the canonical chunker used by ``conversation.send``:
  it runs a blocking producer in a worker thread, splits the produced text into
  token-sized fragments, yields them as chunk payloads, and returns the full
  producer result so the dispatcher can send it as the final ``result``.
"""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from dream.reliability.deadline import MAX_STEP_DELAY_SECONDS, clamp_delay
from dream.reliability.streams import StreamStalledError as StreamStalledError
from dream.reliability.streams import guarded_aiter

#: A chunk payload emitted to the frontend. The server adds the request ``id``
#: and ``session_id`` routing keys before sending.
Chunk = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Stream:
    """A streaming result: an async iterator of chunks plus a final value.

    Async generators cannot ``return`` a value (it is a ``SyntaxError``), so a
    streaming handler returns a :class:`Stream` instead: it runs its blocking
    work up front, hands the tokenised text to ``chunks``, and carries the full
    result as ``final``. The server emits each chunk as a ``stream.chunk``
    notification and sends ``final`` as the JSON-RPC ``result``.
    """

    final: Any
    chunks: AsyncIterator[Chunk]

#: Regex that splits text into a non-whitespace run plus any trailing whitespace,
#: so re-joining the tokens reproduces the original text exactly.
_TOKEN_RE = re.compile(r"\S+\s*|\s+")

#: Default fragment size for hard-splitting an over-long token (a paste with no
#: whitespace). Twelve characters is a comfortable read-ahead for both Latin and
#: Persian text.
DEFAULT_MAX_CHARS = 12


def is_async_generator(value: Any) -> bool:
    """True when *value* is an async generator (i.e. a streaming result)."""
    return inspect.isasyncgen(value)


def tokenise(text: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """Split *text* into roughly token-sized fragments.

    Word boundaries are honoured when present (Latin scripts, or Persian joined
    by spaces/ZWNJ). A single over-long token (no whitespace) is hard-split at
    ``max_chars`` so a giant paste still streams in pieces rather than one blob.
    """
    if not text:
        return []
    fragments: list[str] = []
    for word in _TOKEN_RE.findall(text):
        if len(word) <= max_chars:
            fragments.append(word)
            continue
        fragments.extend(word[i : i + max_chars] for i in range(0, len(word), max_chars))
    return fragments


async def stream_chunks(
    produce: Callable[[], Any],
    *,
    to_text: Callable[[Any], str] | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    delay: float = 0.0,
    stall_timeout: float | None = None,
) -> Stream:
    """Run a blocking ``produce()`` call and return a :class:`Stream` of its text.

    ``produce`` runs in a worker thread (Dream's turn loop is blocking and uses
    threads internally). ``to_text`` extracts the assistant text to stream from
    the producer's result (default: ``str(result)``). The full producer result
    is carried as ``Stream.final`` so the dispatcher can send it as the final
    ``result``; the chunked text becomes ``Stream.chunks``.

    ``delay`` adds an optional inter-chunk await — useful only for tests that
    want to observe ordering; production passes ``0``. The value is clamped
    to :data:`MAX_STEP_DELAY_SECONDS` so a client cannot hang the stream.

    ``stall_timeout`` is opt-in. When set, a quiet producer raises
    :class:`StreamStalledError` instead of spinning forever.
    """
    delay = clamp_delay(delay, hard_max=MAX_STEP_DELAY_SECONDS)
    result = await asyncio.to_thread(produce)
    text = to_text(result) if to_text is not None else str(result)

    async def _chunks() -> AsyncIterator[Chunk]:
        for piece in tokenise(text, max_chars=max_chars):
            yield {"token": piece}
            if delay:
                await asyncio.sleep(delay)

    chunks: AsyncIterator[Chunk] = _chunks()
    if stall_timeout is not None:
        chunks = stream_with_stall_guard(chunks, stall_timeout=stall_timeout)
    return Stream(final=result, chunks=chunks)


async def stream_text(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    delay: float = 0.0,
    stall_timeout: float | None = None,
) -> AsyncIterator[Chunk]:
    """Stream an already-available *text* string.

    Convenience wrapper used by handlers that have the text up front and just
    want it chunked (e.g. echoing a stored reply). ``delay`` is clamped.
    """
    delay = clamp_delay(delay, hard_max=MAX_STEP_DELAY_SECONDS)

    async def _chunks() -> AsyncIterator[Chunk]:
        for piece in tokenise(text, max_chars=max_chars):
            yield {"token": piece}
            if delay:
                await asyncio.sleep(delay)

    chunks: AsyncIterator[Chunk] = _chunks()
    if stall_timeout is not None:
        chunks = stream_with_stall_guard(chunks, stall_timeout=stall_timeout)
    async for piece in chunks:
        yield piece


async def collect(async_iter: AsyncIterator[Any]) -> list[Any]:
    """Materialise an async iterator into a list (test helper)."""
    out: list[Any] = []
    async for item in async_iter:
        out.append(item)
    return out


async def stream_with_stall_guard(
    chunks: AsyncIterator[Chunk],
    *,
    stall_timeout: float = 5.0,
    name: str = "bridge.stream",
) -> AsyncIterator[Chunk]:
    """Additive wrapper: terminate a quiet producer with ``StreamStalledError``.

    Keeps one pending ``__anext__`` (see ``dream.reliability.streams``).
    Existing callers that do not opt in are unchanged.
    """
    async for item in guarded_aiter(
        chunks, stall_timeout=stall_timeout, name=name
    ):
        yield item


def ensure_awaitable(value: Any) -> Awaitable[Any]:
    """Wrap a plain (non-async) handler return value into an awaitable.

    Handlers may be ``async def`` or plain ``def``; the dispatcher normalises
    both to awaitables so a single code path awaits the result.
    """
    if inspect.isawaitable(value):
        return value
    fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
    fut.set_result(value)
    return fut
