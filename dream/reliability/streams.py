"""Guaranteed-terminating async iterators with stall detection.

A producer that goes quiet must not become an infinite spinner. The wrapper
keeps **one** pending ``__anext__`` task: wrapping each poll in
``wait_for(anext(...))`` would cancel the generator on every timeout.

When the producer is silent longer than ``stall_timeout``, the wrapper
raises :class:`StreamStalledError` so a UI can offer a restart.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from typing import TypeVar

from dream.reliability.cancel import CancelToken, OperationCancelled
from dream.reliability.deadline import (
    MAX_TIMEOUT_SECONDS,
    Deadline,
    DeadlineExceeded,
    clamp_timeout,
)

T = TypeVar("T")

DEFAULT_STALL_TIMEOUT = 5.0
HEARTBEAT_MARK = {"type": "heartbeat"}

__all__ = [
    "DEFAULT_STALL_TIMEOUT",
    "HEARTBEAT_MARK",
    "StreamStalledError",
    "guarded_aiter",
    "terminating_aiter",
]


class StreamStalledError(Exception):
    """The producer went silent. The UI should show restart, not a spinner."""

    def __init__(
        self,
        message: str,
        *,
        name: str,
        idle_for: float,
        stall_timeout: float,
    ) -> None:
        super().__init__(message)
        self.name = name
        self.idle_for = idle_for
        self.stall_timeout = stall_timeout


async def guarded_aiter(
    source: AsyncIterator[T],
    *,
    stall_timeout: float = DEFAULT_STALL_TIMEOUT,
    heartbeat_interval: float | None = None,
    emit_heartbeat: bool = False,
    on_heartbeat: Callable[[float], None] | None = None,
    token: CancelToken | None = None,
    deadline: Deadline | None = None,
    name: str = "stream",
) -> AsyncIterator[T]:
    """Yield from *source* until it ends, stalls, is cancelled, or times out.

    A single ``__anext__`` task is kept pending across poll timeouts. The
    generator is cancelled only when this wrapper itself terminates.
    """
    stall_timeout = clamp_timeout(
        stall_timeout,
        default=DEFAULT_STALL_TIMEOUT,
        hard_max=MAX_TIMEOUT_SECONDS,
        hard_min=0.05,
    )
    beat: float | None = None
    if heartbeat_interval is not None:
        beat = clamp_timeout(
            heartbeat_interval,
            default=1.0,
            hard_max=stall_timeout,
            hard_min=0.05,
        )

    pending: asyncio.Task[T] | None = None
    last_yield = time.monotonic()
    last_beat = last_yield
    closed = False

    def _next_timeout() -> float:
        now = time.monotonic()
        stall_left = stall_timeout - (now - last_yield)
        options = [max(0.0, stall_left)]
        if beat is not None:
            options.append(max(0.0, beat - (now - last_beat)))
        if deadline is not None:
            options.append(deadline.remaining())
        return min(options)

    try:
        while True:
            if token is not None:
                token.throw_if_cancelled()
            if deadline is not None:
                deadline.throw_if_exceeded()
            if pending is None:
                pending = asyncio.ensure_future(source.__anext__())
            timeout = _next_timeout()
            now = time.monotonic()
            idle = now - last_yield
            if idle >= stall_timeout:
                raise StreamStalledError(
                    f"stream {name!r} stalled for {idle:.3f}s "
                    f"(limit {stall_timeout:.3f}s)",
                    name=name,
                    idle_for=idle,
                    stall_timeout=stall_timeout,
                )
            done, _pending = await asyncio.wait({pending}, timeout=timeout)
            if pending in done:
                try:
                    item = pending.result()
                except StopAsyncIteration:
                    pending = None
                    return
                pending = None
                last_yield = time.monotonic()
                last_beat = last_yield
                yield item
                continue
            # The wait timed out; the same pending task is still running.
            now = time.monotonic()
            idle = now - last_yield
            if idle >= stall_timeout:
                raise StreamStalledError(
                    f"stream {name!r} stalled for {idle:.3f}s "
                    f"(limit {stall_timeout:.3f}s)",
                    name=name,
                    idle_for=idle,
                    stall_timeout=stall_timeout,
                )
            if deadline is not None and deadline.expired():
                deadline.throw_if_exceeded()
            if token is not None and token.is_cancelled():
                token.throw_if_cancelled()
            if beat is not None and (now - last_beat) >= beat:
                last_beat = now
                if on_heartbeat is not None:
                    on_heartbeat(idle)
                if emit_heartbeat:
                    yield HEARTBEAT_MARK  # type: ignore[misc]
    except (OperationCancelled, DeadlineExceeded, StreamStalledError):
        raise
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            try:
                await pending
            except (asyncio.CancelledError, StopAsyncIteration, Exception):
                pass
        closer = getattr(source, "aclose", None)
        if closer is not None and not closed:
            closed = True
            try:
                await closer()
            except Exception:
                pass


async def terminating_aiter(
    source: AsyncIterator[T],
    *,
    max_items: int = 10_000,
    stall_timeout: float = DEFAULT_STALL_TIMEOUT,
    token: CancelToken | None = None,
    deadline: Deadline | None = None,
    name: str = "stream",
) -> AsyncIterator[T]:
    """Like :func:`guarded_aiter` plus a hard item cap (lists stay bounded)."""
    cap = 1 if max_items < 1 else (10_000 if max_items > 10_000 else int(max_items))
    count = 0
    async for item in guarded_aiter(
        source,
        stall_timeout=stall_timeout,
        token=token,
        deadline=deadline,
        name=name,
    ):
        yield item
        count += 1
        if count >= cap:
            return
