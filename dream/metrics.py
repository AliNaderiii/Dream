"""Thread-safe process metrics for Dream.

A tiny, dependency-free counter registry used to observe the durability
extraction pass and other subsystem outcomes without any network calls,
user-content labels, or mutable state shared by reference. Every public method
is typed and thread-safe; ``snapshot`` returns a copy so callers can never
mutate the internal counters.
"""

from __future__ import annotations

from collections import Counter
from threading import Lock

__all__ = [
    "METRIC_EXTRACTION_SUCCESS",
    "METRIC_EXTRACTION_NO_FACTS",
    "METRIC_EXTRACTION_SKIPPED",
    "METRIC_EXTRACTION_PARSE_ERROR",
    "METRIC_EXTRACTION_STORE_ERROR",
    "METRIC_EXTRACTION_ERROR",
    "METRIC_EXTRACTION_ABANDONED",
    "Metrics",
    "metrics",
]

# Stable metric names. These are part of the observability contract for the
# extraction pass and must not be renamed casually; nothing here ever carries
# user content or credentials as a label or value.
METRIC_EXTRACTION_SUCCESS: str = "dream.extraction.success"
METRIC_EXTRACTION_NO_FACTS: str = "dream.extraction.no_facts"
METRIC_EXTRACTION_SKIPPED: str = "dream.extraction.skipped"
METRIC_EXTRACTION_PARSE_ERROR: str = "dream.extraction.parse_error"
METRIC_EXTRACTION_STORE_ERROR: str = "dream.extraction.store_error"
METRIC_EXTRACTION_ERROR: str = "dream.extraction.error"
METRIC_EXTRACTION_ABANDONED: str = "dream.extraction.abandoned"


class Metrics:
    """A lock-guarded counter registry.

    Increments, reads, and snapshots all take the same lock, so concurrent
    emitters (e.g. the background extraction worker thread and the turn that
    waits on it) never corrupt or lose a count. A snapshot is a plain ``dict``
    copy, so the returned mapping shares no mutable state with the registry.
    """

    __slots__ = ("_counters", "_lock")

    def __init__(self) -> None:
        self._counters: Counter[str] = Counter()
        self._lock = Lock()

    def incr(self, name: str, value: int = 1) -> None:
        """Increment ``name`` by ``value`` (default 1), atomically."""
        with self._lock:
            self._counters[name] += value

    def get(self, name: str) -> int:
        """Return the current count for ``name`` (0 when never recorded)."""
        with self._lock:
            return self._counters[name]

    def snapshot(self) -> dict[str, int]:
        """Return a defensive copy of every recorded counter."""
        with self._lock:
            return dict(self._counters)

    def clear(self) -> None:
        """Reset all counters to zero.

        Intended for test isolation and process-local resets, never for
        production hot paths.
        """
        with self._lock:
            self._counters.clear()


# The process-wide registry used by ``dream.agent`` and its extraction worker.
metrics: Metrics = Metrics()
