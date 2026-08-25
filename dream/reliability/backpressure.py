"""Bounded streaming buffers. Lists stay bounded.

Overflow policy is explicit: drop-oldest, coalesce same-key events, or
reject. Nothing in this module grows without a hard cap.
"""

from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Any

# Hard cap even if a caller asks for a million-slot buffer.
MAX_BUFFER = 10_000
DEFAULT_BUFFER = 256

__all__ = [
    "DEFAULT_BUFFER",
    "MAX_BUFFER",
    "BackpressureError",
    "BoundedBuffer",
    "BoundedList",
    "OverflowPolicy",
]


class OverflowPolicy(str, Enum):
    DROP_OLDEST = "drop_oldest"
    COALESCE = "coalesce"
    REJECT = "reject"


class BackpressureError(Exception):
    """The buffer is full and the policy is ``reject``."""


def _clamp_maxlen(maxlen: int) -> int:
    try:
        value = int(maxlen)
    except (TypeError, ValueError):
        return DEFAULT_BUFFER
    if value < 1:
        return 1
    if value > MAX_BUFFER:
        return MAX_BUFFER
    return value


class BoundedBuffer:
    """A thread-unsafe bounded queue (protect it with the caller's lock).

    ``drop_oldest`` discards the front. ``coalesce`` replaces the last item
    that shares ``key``. ``reject`` raises :class:`BackpressureError`.
    """

    def __init__(
        self,
        maxlen: int = DEFAULT_BUFFER,
        *,
        policy: OverflowPolicy | str = OverflowPolicy.DROP_OLDEST,
    ) -> None:
        self.maxlen = _clamp_maxlen(maxlen)
        self.policy = (
            policy if isinstance(policy, OverflowPolicy) else OverflowPolicy(str(policy))
        )
        self._items: deque[Any] = deque()
        self._keys: deque[Any] = deque()
        self.dropped = 0
        self.coalesced = 0
        self.rejected = 0

    def __len__(self) -> int:
        return len(self._items)

    def clear(self) -> None:
        self._items.clear()
        self._keys.clear()

    def put(self, item: Any, *, key: Any = None) -> bool:
        """Push *item*. Returns ``True`` if it occupies a new slot."""
        if (
            self.policy is OverflowPolicy.COALESCE
            and key is not None
            and key in self._keys
        ):
            # Replace the most recent matching key, keeping list bounded.
            index = len(self._keys) - 1
            while index >= 0:
                if self._keys[index] == key:
                    self._items[index] = item
                    self.coalesced += 1
                    return False
                index -= 1
        if len(self._items) >= self.maxlen:
            if self.policy is OverflowPolicy.REJECT:
                self.rejected += 1
                raise BackpressureError(
                    f"bounded buffer full ({self.maxlen} items); refusing push"
                )
            if self.policy is OverflowPolicy.DROP_OLDEST:
                self._items.popleft()
                self._keys.popleft()
                self.dropped += 1
            elif self.policy is OverflowPolicy.COALESCE:
                # No matching key: drop oldest and append, still bounded.
                self._items.popleft()
                self._keys.popleft()
                self.dropped += 1
        self._items.append(item)
        self._keys.append(key)
        return True

    def get(self) -> Any:
        if not self._items:
            raise IndexError("bounded buffer is empty")
        self._keys.popleft()
        return self._items.popleft()

    def peek(self) -> Any:
        if not self._items:
            raise IndexError("bounded buffer is empty")
        return self._items[0]

    def snapshot(self) -> list[Any]:
        """A *copy* of the items. Length is always ``<= maxlen``."""
        return list(self._items)

    def stats(self) -> dict[str, int | str]:
        return {
            "size": len(self._items),
            "maxlen": self.maxlen,
            "policy": self.policy.value,
            "dropped": self.dropped,
            "coalesced": self.coalesced,
            "rejected": self.rejected,
        }


class BoundedList:
    """A list that silently forgets the oldest items once it hits *maxlen*."""

    def __init__(self, maxlen: int = DEFAULT_BUFFER) -> None:
        self._buf = BoundedBuffer(maxlen, policy=OverflowPolicy.DROP_OLDEST)

    @property
    def maxlen(self) -> int:
        return self._buf.maxlen

    def append(self, item: Any) -> None:
        self._buf.put(item)

    def extend(self, items: Any) -> None:
        for item in items:
            self._buf.put(item)

    def __len__(self) -> int:
        return len(self._buf)

    def __iter__(self) -> Any:
        return iter(self._buf.snapshot())

    def __getitem__(self, index: int) -> Any:
        return self._buf.snapshot()[index]

    def snapshot(self) -> list[Any]:
        return self._buf.snapshot()
