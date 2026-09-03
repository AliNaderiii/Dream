"""Cooperative sleep helpers that observe cancellation and never busy-spin.

The synchronous helper uses :class:`~dream.reliability.cancel.CancelToken`'s
threading event as the wake-up primitive, so a cancelled wait returns as soon
as the token fires rather than after a full polling slice. The asynchronous
helper yields to the event loop on every bounded slice and preserves
``asyncio.CancelledError`` semantics for task-driven shutdown.

Cancellation contract
---------------------

When ``cancel`` is provided and it fires, both helpers raise
:class:`~dream.reliability.cancel.OperationCancelled`.  The helper never
converts an ``asyncio.CancelledError`` into a normal success and never swallows
the existing project cancellation exception.
"""

from __future__ import annotations

import asyncio
import math
import time

from dream.reliability.cancel import CancelToken

#: Default polling slice for cancellation checks while sleeping.
DEFAULT_SLEEP_GRANULARITY = 0.05

__all__ = [
    "DEFAULT_SLEEP_GRANULARITY",
    "ainterruptible_sleep",
    "interruptible_sleep",
]


def _coerce_seconds(seconds: float) -> float:
    """Return a non-negative finite sleep length."""
    try:
        value = float(seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("seconds must be a finite number") from exc
    if math.isnan(value) or math.isinf(value):
        raise ValueError("seconds must be a finite number")
    return max(0.0, value)


def _normalize_granularity(granularity: float) -> float:
    """Reject non-positive or non-finite polling granularity."""
    try:
        value = float(granularity)
    except (TypeError, ValueError) as exc:
        raise ValueError("granularity must be a positive finite number") from exc
    if math.isnan(value) or math.isinf(value) or value <= 0.0:
        raise ValueError("granularity must be a positive finite number")
    return value


def interruptible_sleep(
    seconds: float,
    cancel: CancelToken | None = None,
    granularity: float = DEFAULT_SLEEP_GRANULARITY,
) -> None:
    """Sleep for up to *seconds*, stopping promptly when *cancel* fires.

    Durations of zero or less return immediately.  With no cancellation token
    the helper delegates to ``time.sleep`` so existing durations are preserved
    exactly.  With a token it checks before sleeping and then waits in bounded
    slices on the token's threading event; it never spins.
    """
    duration = _coerce_seconds(seconds)
    if duration <= 0.0:
        return
    slice_s = _normalize_granularity(granularity)
    if cancel is None:
        time.sleep(duration)
        return

    cancel.throw_if_cancelled()
    deadline = time.monotonic() + duration
    event = cancel.as_event()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0.0:
            return
        wait_slice = min(remaining, slice_s)
        if event.wait(wait_slice):
            cancel.throw_if_cancelled()
        cancel.throw_if_cancelled()


async def ainterruptible_sleep(
    seconds: float,
    cancel: CancelToken | None = None,
    granularity: float = DEFAULT_SLEEP_GRANULARITY,
) -> None:
    """Async cooperative equivalent of :func:`interruptible_sleep`.

    The helper yields to the event loop on every bounded slice.  An
    ``asyncio.CancelledError`` raised while awaiting propagates unchanged;
    token cancellation raises :class:`OperationCancelled`.
    """
    duration = _coerce_seconds(seconds)
    if duration <= 0.0:
        return
    slice_s = _normalize_granularity(granularity)
    if cancel is None:
        await asyncio.sleep(duration)
        return

    cancel.throw_if_cancelled()
    deadline = time.monotonic() + duration
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0.0:
            return
        wait_slice = min(remaining, slice_s)
        await asyncio.sleep(wait_slice)
        cancel.throw_if_cancelled()
