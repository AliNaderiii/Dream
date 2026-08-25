"""Absolute and relative deadlines, capped public waits, and a hung-task watchdog.

Nothing waits forever. Every public delay/timeout parameter is clamped to a
hard maximum so a client cannot pass ``step_delay=1e9`` and hang the engine.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from dream.reliability.cancel import CancelToken

# Public wait/delay hard caps. Matches the existing plan-step clamp (2 s)
# and a generous but finite outer timeout.
MAX_STEP_DELAY_SECONDS = 2.0
MAX_TIMEOUT_SECONDS = 120.0
MAX_DEADLINE_SECONDS = 600.0

T = TypeVar("T")

__all__ = [
    "MAX_DEADLINE_SECONDS",
    "MAX_STEP_DELAY_SECONDS",
    "MAX_TIMEOUT_SECONDS",
    "Deadline",
    "DeadlineExceeded",
    "Watchdog",
    "clamp_delay",
    "clamp_timeout",
]


class DeadlineExceeded(TimeoutError):
    """A scoped deadline expired. Carries the owner and step that owned it."""

    def __init__(
        self,
        message: str,
        *,
        owner: str,
        step: str,
        deadline_mono: float,
        started_mono: float,
    ) -> None:
        super().__init__(message)
        self.owner = owner
        self.step = step
        self.deadline_mono = deadline_mono
        self.started_mono = started_mono
        self.elapsed = max(0.0, time.monotonic() - started_mono)


def clamp_timeout(
    value: float | None,
    *,
    default: float = 30.0,
    hard_max: float = MAX_TIMEOUT_SECONDS,
    hard_min: float = 0.0,
) -> float:
    """Clamp a public timeout. ``None``, NaN, and garbage become *default*."""
    if value is None:
        return float(default)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    if number != number:  # NaN
        return float(default)
    if number < hard_min:
        return float(hard_min)
    if number > hard_max:
        return float(hard_max)
    return number


def clamp_delay(
    value: float | None,
    *,
    default: float = 0.0,
    hard_max: float = MAX_STEP_DELAY_SECONDS,
) -> float:
    """Clamp an inter-step / inter-chunk delay. Never accepts ``1e9``."""
    return clamp_timeout(value, default=default, hard_max=hard_max, hard_min=0.0)


class Deadline:
    """A monotonic deadline scoped to an owner and a step name."""

    def __init__(
        self,
        *,
        owner: str,
        step: str,
        at_mono: float,
        started_mono: float | None = None,
    ) -> None:
        self.owner = owner
        self.step = step
        self.at_mono = float(at_mono)
        now = time.monotonic()
        self.started_mono = float(started_mono) if started_mono is not None else now

    @classmethod
    def after(
        cls,
        seconds: float,
        *,
        owner: str = "engine",
        step: str = "step",
    ) -> Deadline:
        """Relative deadline from now. *seconds* is clamped to the hard max."""
        seconds = clamp_timeout(
            seconds, default=30.0, hard_max=MAX_DEADLINE_SECONDS, hard_min=0.0
        )
        now = time.monotonic()
        return cls(owner=owner, step=step, at_mono=now + seconds, started_mono=now)

    @classmethod
    def absolute(
        cls,
        at_mono: float,
        *,
        owner: str = "engine",
        step: str = "step",
    ) -> Deadline:
        """Absolute monotonic deadline, capped so it cannot be unbounded."""
        now = time.monotonic()
        try:
            target = float(at_mono)
        except (TypeError, ValueError):
            target = now + 30.0
        if target - now > MAX_DEADLINE_SECONDS:
            target = now + MAX_DEADLINE_SECONDS
        return cls(owner=owner, step=step, at_mono=target, started_mono=now)

    def remaining(self) -> float:
        return max(0.0, self.at_mono - time.monotonic())

    def expired(self) -> bool:
        return time.monotonic() >= self.at_mono

    def throw_if_exceeded(self) -> None:
        if not self.expired():
            return
        elapsed = time.monotonic() - self.started_mono
        raise DeadlineExceeded(
            f"deadline exceeded: owner={self.owner!r} step={self.step!r} "
            f"after {elapsed:.3f}s",
            owner=self.owner,
            step=self.step,
            deadline_mono=self.at_mono,
            started_mono=self.started_mono,
        )

    def child(self, step: str, budget: float | None = None) -> Deadline:
        """A nested deadline that cannot outlive this one."""
        now = time.monotonic()
        if budget is None:
            at_mono = self.at_mono
        else:
            remaining = self.remaining()
            slice_s = clamp_timeout(
                budget, default=remaining, hard_max=max(remaining, 0.0), hard_min=0.0
            )
            at_mono = min(self.at_mono, now + slice_s)
        return Deadline(owner=self.owner, step=step, at_mono=at_mono, started_mono=now)

    def __enter__(self) -> Deadline:
        self.throw_if_exceeded()
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class Watchdog:
    """Cancel a hung task and record the cause.

    The watched callable is *not* forcibly killed (Python threads cannot be);
    the token is fired, ``reaped`` becomes true, and the caller receives
    :class:`DeadlineExceeded` so a UI can show a restart, not a spinner.
    Worker threads are daemons so they cannot keep the process alive.
    """

    def __init__(
        self,
        deadline: Deadline,
        token: CancelToken | None = None,
    ) -> None:
        self.deadline = deadline
        self.token = token or CancelToken(
            name=f"watchdog:{deadline.owner}.{deadline.step}"
        )
        self.cause: str | None = None
        self.reaped = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _mark_reaped(self) -> None:
        if self.reaped:
            return
        self.reaped = True
        self.cause = (
            f"watchdog reaped hung task owner={self.deadline.owner} "
            f"step={self.deadline.step}"
        )
        self.token.cancel(reason=self.cause)

    def start(self) -> Watchdog:
        thread = threading.Thread(
            target=self._run,
            name=f"dream-watchdog-{self.deadline.step}",
            daemon=True,
        )
        self._thread = thread
        thread.start()
        return self

    def _run(self) -> None:
        remaining = self.deadline.remaining()
        if self._stop.wait(timeout=remaining):
            return
        self._mark_reaped()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    def __enter__(self) -> Watchdog:
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    def run(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Run *fn* in a daemon worker; reap it when the deadline expires."""
        slot: dict[str, Any] = {}

        def _target() -> None:
            try:
                slot["value"] = fn(*args, **kwargs)
            except BaseException as exc:
                slot["exc"] = exc

        worker = threading.Thread(
            target=_target,
            name=f"dream-watched-{self.deadline.step}",
            daemon=True,
        )
        self.start()
        worker.start()
        try:
            while worker.is_alive():
                worker.join(timeout=0.05)
                if self.token.is_cancelled() or self.deadline.expired():
                    self._mark_reaped()
                    break
        finally:
            self.stop()
        if "exc" in slot:
            raise slot["exc"]
        if "value" in slot:
            return slot["value"]
        self._mark_reaped()
        self.deadline.throw_if_exceeded()
        self.token.throw_if_cancelled()
        raise DeadlineExceeded(
            f"deadline exceeded: owner={self.deadline.owner!r} "
            f"step={self.deadline.step!r}",
            owner=self.deadline.owner,
            step=self.deadline.step,
            deadline_mono=self.deadline.at_mono,
            started_mono=self.deadline.started_mono,
        )

    async def run_async(self, awaitable: Awaitable[T]) -> T:
        """Await *awaitable* until the deadline; cancel it and record the cause."""
        self.start()
        timeout = max(0.001, self.deadline.remaining())
        try:
            return await asyncio.wait_for(awaitable, timeout=timeout)
        except asyncio.TimeoutError as exc:
            self._mark_reaped()
            raise DeadlineExceeded(
                f"deadline exceeded: owner={self.deadline.owner!r} "
                f"step={self.deadline.step!r} after {timeout:.3f}s",
                owner=self.deadline.owner,
                step=self.deadline.step,
                deadline_mono=self.deadline.at_mono,
                started_mono=self.deadline.started_mono,
            ) from exc
        except asyncio.CancelledError:
            self.token.cancel(reason="async cancelled")
            raise
        finally:
            self.stop()


def race_deadline(
    token: CancelToken,
    deadline: Deadline,
) -> None:
    """Raise the first of cancel / deadline. Used at step boundaries."""
    token.throw_if_cancelled()
    deadline.throw_if_exceeded()
