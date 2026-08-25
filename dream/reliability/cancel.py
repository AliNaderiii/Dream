"""Composable cooperative cancellation tokens.

A stale UI flag is never enough: every blocked path must check a real token
and yield a cancelled signal. This module **adapts** P4
``dream.agentmodes.cancel.CancellationToken`` and P1 research
``threading.Event`` stop flags without rewriting those owners.

Public waits are hard-capped. A client cannot pass ``wait(1e9)``.
"""

from __future__ import annotations

import subprocess
import threading
import time
import weakref
from collections.abc import Callable
from typing import Any

# Hard cap for any public wait. A client cannot pass an unbounded timeout.
MAX_WAIT_SECONDS = 30.0

__all__ = [
    "MAX_WAIT_SECONDS",
    "CancelToken",
    "OperationCancelled",
    "adapt_agentmodes",
    "adapt_research_stop",
    "clamp_wait",
]


class OperationCancelled(Exception):
    """Cooperative cancellation. The operation stopped because a token fired."""

    def __init__(
        self,
        message: str = "operation cancelled",
        *,
        reason: str | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.name = name


def clamp_wait(
    value: float | None,
    *,
    default: float = MAX_WAIT_SECONDS,
    hard_max: float = MAX_WAIT_SECONDS,
) -> float:
    """Clamp a public wait/timeout so a client cannot hang the engine."""
    if value is None:
        return float(default)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    if number != number:  # NaN
        return float(default)
    if number < 0.0:
        return 0.0
    if number > hard_max:
        return float(hard_max)
    return number


class CancelToken:
    """Cooperative cancel flag that composes across async, threads, and processes.

    Children inherit a parent's cancel. Linked P4 tokens and research Events
    are polled on every check and are themselves signalled when this token
    fires, so a ``/stop`` is a real token, not a UI decoration.
    """

    def __init__(
        self,
        *,
        name: str = "cancel",
        parent: CancelToken | None = None,
    ) -> None:
        self.name = name
        self._event = threading.Event()
        self._reason: str | None = None
        self.cancelled_at: float | None = None
        self._lock = threading.Lock()
        self._children: list[weakref.ref[CancelToken]] = []
        self._on_cancel: list[Callable[[CancelToken], None]] = []
        self._linked: list[Any] = []
        self._parent = parent
        if parent is not None:
            parent._register_child(self)
            if parent.is_cancelled():
                self.cancel(reason=parent.reason)

    def _register_child(self, child: CancelToken) -> None:
        with self._lock:
            self._children.append(weakref.ref(child))

    @property
    def reason(self) -> str | None:
        return self._reason

    def child(self, name: str | None = None) -> CancelToken:
        """Return a token that cancels when this one does."""
        label = name if name is not None else f"{self.name}.child"
        return CancelToken(name=label, parent=self)

    def on_cancel(self, callback: Callable[[CancelToken], None]) -> None:
        """Register a callback. Fired immediately if already cancelled."""
        fire_now = False
        with self._lock:
            if self._event.is_set():
                fire_now = True
            else:
                self._on_cancel.append(callback)
        if fire_now:
            callback(self)

    def link_event(self, event: threading.Event) -> None:
        """Compose with a ``threading.Event`` (P1 ``research.stop``)."""
        with self._lock:
            self._linked.append(event)
        if self.is_cancelled():
            event.set()

    def link_agentmodes(self, token: Any) -> None:
        """Compose with P4 ``dream.agentmodes.cancel.CancellationToken``."""
        with self._lock:
            self._linked.append(token)
        if self.is_cancelled() and hasattr(token, "cancel"):
            token.cancel()

    def link_subprocess(self, proc: subprocess.Popen[Any]) -> None:
        """Terminate *proc* when this token fires (SIGTERM, then SIGKILL)."""

        def _kill(_tok: CancelToken) -> None:
            if proc.poll() is not None:
                return
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass

        self.on_cancel(_kill)

    def cancel(self, reason: str | None = None) -> None:
        """Fire this token, every child, and every linked foreign token."""
        callbacks: list[Callable[[CancelToken], None]]
        children: list[CancelToken]
        linked: list[Any]
        with self._lock:
            if self._event.is_set():
                return
            self._reason = reason or "cancelled"
            self.cancelled_at = time.time()
            self._event.set()
            callbacks = list(self._on_cancel)
            children = [child for ref in self._children if (child := ref()) is not None]
            linked = list(self._linked)
        for item in linked:
            if isinstance(item, threading.Event):
                item.set()
            elif hasattr(item, "cancel"):
                try:
                    item.cancel()
                except Exception:
                    pass
        for child in children:
            child.cancel(reason=self._reason)
        for callback in callbacks:
            try:
                callback(self)
            except Exception:
                pass

    def is_cancelled(self) -> bool:
        if self._event.is_set():
            return True
        parent = self._parent
        if parent is not None and parent.is_cancelled():
            self.cancel(reason=parent.reason)
            return True
        for item in list(self._linked):
            if isinstance(item, threading.Event) and item.is_set():
                self.cancel(reason="linked event")
                return True
            checker = getattr(item, "is_cancelled", None)
            if callable(checker) and checker():
                self.cancel(reason="linked token")
                return True
        return False

    def throw_if_cancelled(self) -> None:
        """Raise :class:`OperationCancelled` when this token has fired."""
        if self.is_cancelled():
            raise OperationCancelled(
                f"{self.name} cancelled: {self._reason or 'cancelled'}",
                reason=self._reason,
                name=self.name,
            )

    # Cooperative alias used by loops that already say ``token.check()``.
    check = throw_if_cancelled

    def wait(self, timeout: float | None = None) -> bool:
        """Block until cancelled or *timeout* (clamped) elapses.

        Returns ``True`` if the token is cancelled. Never waits longer than
        :data:`MAX_WAIT_SECONDS`.
        """
        timeout = clamp_wait(timeout)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                return self.is_cancelled()
            slice_s = remaining if remaining < 0.05 else 0.05
            if self._event.wait(slice_s):
                return True
            if self.is_cancelled():
                return True

    def as_event(self) -> threading.Event:
        """The underlying ``Event`` (set when this token fires)."""
        return self._event

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cancelled": self.is_cancelled(),
            "cancelled_at": self.cancelled_at,
            "reason": self._reason,
            "live": True,
        }

    def clear(self) -> None:
        """Reset this token only (not parents). Intended for tests."""
        with self._lock:
            self._event.clear()
            self._reason = None
            self.cancelled_at = None

    @classmethod
    def from_agentmodes(cls, token: Any, *, name: str = "agentmodes") -> CancelToken:
        """Wrap a P4 ``CancellationToken`` without modifying that module."""
        out = cls(name=name)
        out.link_agentmodes(token)
        return out

    @classmethod
    def from_research_stop(
        cls, event: threading.Event, *, name: str = "research.stop"
    ) -> CancelToken:
        """Wrap a P1 research ``cancelled`` Event without modifying research."""
        out = cls(name=name)
        out.link_event(event)
        return out

    @classmethod
    def compose(cls, *tokens: CancelToken, name: str = "compose") -> CancelToken:
        """A token that fires when any of *tokens* fires."""
        out = cls(name=name)
        for source in tokens:

            def _forward(fired: CancelToken, dest: CancelToken = out) -> None:
                dest.cancel(reason=fired.reason)

            source.on_cancel(_forward)
        return out


def adapt_agentmodes(token: Any, *, name: str = "agentmodes") -> CancelToken:
    """Public adapter for P4 ``dream.agentmodes.cancel.CancellationToken``."""
    return CancelToken.from_agentmodes(token, name=name)


def adapt_research_stop(
    event: threading.Event, *, name: str = "research.stop"
) -> CancelToken:
    """Public adapter for P1 ``RunContext.cancelled`` / ``session.cancel``."""
    return CancelToken.from_research_stop(event, name=name)
