"""Per-user, per-minute rate limiting for gateway ingress.

The gate counter is the triple ``{platform, user_id, minute}`` (minute = unix
epoch floor). The default allowance of 20 messages per minute is configurable
per platform through the connectivity config's ``rate_limit_per_minute`` key.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RateLimitDecision:
    """Outcome of one gate check, including counters for the UI/log."""

    allowed: bool
    used: int
    limit: int
    retry_after_seconds: float


class RateLimiter:
    """Fixed-minute-window counter over ``(platform, user_id)`` keys."""

    def __init__(self, default_per_minute: int = 20) -> None:
        if default_per_minute < 1:
            raise ValueError("default_per_minute must be at least 1")
        self._default = default_per_minute
        #: per-platform overrides, applied by the gateway from config.
        self._limits: dict[str, int] = {}
        #: (platform, user_id, minute) -> count.
        self._buckets: dict[tuple[str, str, int], int] = {}
        #: (platform, user_id) -> last minute seen, for pruning.
        self._last_minute: dict[tuple[str, str], int] = {}

    # -- configuration --------------------------------------------------- #

    def configure(self, platform: str, per_minute: int | None = None) -> None:
        """Set (or clear) a per-platform allowance; a bad value keeps the old."""
        if per_minute is None:
            self._limits.pop(platform, None)
            return
        if isinstance(per_minute, int) and per_minute >= 1:
            self._limits[platform] = per_minute

    def limit_for(self, platform: str) -> int:
        """The active per-minute allowance for *platform*."""
        return self._limits.get(platform, self._default)

    # -- gating ---------------------------------------------------------- #

    def check(self, platform: str, user_id: str, now: float | None = None) -> RateLimitDecision:
        """Record one inbound message and decide whether it is allowed.

        Side-effect free to call repeatedly; the counter is incremented once
        per call, so callers must gate on the returned ``allowed`` flag rather
        than calling twice.
        """
        stamp = time.time() if now is None else now
        minute = int(stamp // 60)
        limit = self.limit_for(platform)
        key = (platform, user_id)
        previous = self._last_minute.get(key)
        if previous is not None and previous != minute:
            # The window rolled over: drop every bucket this user no longer
            # needs so long-running processes never accumulate counters.
            self._prune(key, minute)
        self._last_minute[key] = minute
        bucket = (platform, user_id, minute)
        used = self._buckets.get(bucket, 0) + 1
        self._buckets[bucket] = used
        remaining_seconds = 60.0 - (stamp - minute * 60)
        return RateLimitDecision(
            allowed=used <= limit,
            used=used,
            limit=limit,
            retry_after_seconds=max(0.0, remaining_seconds),
        )

    def remaining(self, platform: str, user_id: str, now: float | None = None) -> int:
        """How many messages this user may still send in the current minute."""
        stamp = time.time() if now is None else now
        minute = int(stamp // 60)
        used = self._buckets.get((platform, user_id, minute), 0)
        return max(0, self.limit_for(platform) - used)

    def reset(self, platform: str | None = None) -> None:
        """Drop counters for one platform (or all platforms when ``None``)."""
        if platform is None:
            self._buckets.clear()
            self._last_minute.clear()
            return
        for key in list(self._buckets):
            if key[0] == platform:
                del self._buckets[key]
        for key in list(self._last_minute):
            if key[0] == platform:
                del self._last_minute[key]

    def _prune(self, key: tuple[str, str], minute: int) -> None:
        platform, user_id = key
        for bucket in list(self._buckets):
            if bucket[0] == platform and bucket[1] == user_id and bucket[2] != minute:
                del self._buckets[bucket]

    def to_dict(self) -> dict[str, Any]:
        """A compact snapshot for ``gateway.status`` (counters, not content)."""
        by_platform: dict[str, dict[str, int]] = {}
        for (platform, user_id, minute), count in self._buckets.items():
            if int(time.time() // 60) != minute:
                continue
            by_platform.setdefault(platform, {})[user_id] = count
        return {"limits": dict(self._limits), "default": self._default, "active": by_platform}
