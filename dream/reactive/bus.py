"""In-memory Pub-Sub Event Bus with priority ordering and idempotency deduplication."""

from __future__ import annotations

import fnmatch
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from dream.reactive.types import EventPayload, EventPriority, EventStatus


class EventBus:
    """Pub-Sub event broker managing event queues, deduplication, and listeners."""

    def __init__(self, history_capacity: int = 1000, idempotency_ttl_sec: float = 3600.0) -> None:
        self.history_capacity = history_capacity
        self.idempotency_ttl_sec = idempotency_ttl_sec
        self._listeners: dict[str, list[Callable[[EventPayload], Any]]] = {}
        self._idempotency_cache: dict[str, float] = {}
        self._event_history: deque[EventPayload] = deque(maxlen=history_capacity)
        self._queues: dict[EventPriority, deque[EventPayload]] = {
            EventPriority.CRITICAL: deque(),
            EventPriority.HIGH: deque(),
            EventPriority.NORMAL: deque(),
            EventPriority.LOW: deque(),
        }

    def subscribe(self, pattern: str, callback: Callable[[EventPayload], Any]) -> None:
        """Subscribe a handler callback to event types matching pattern."""
        if pattern not in self._listeners:
            self._listeners[pattern] = []
        self._listeners[pattern].append(callback)

    def publish(self, event: EventPayload) -> bool:
        """Ingest and publish an event to matching subscribers.

        Returns:
            True if event was processed/enqueued, False if dropped due to duplicate.
        """
        now = time.time()
        self._clean_idempotency_cache(now)

        # Idempotency check
        if event.idempotency_key:
            if event.idempotency_key in self._idempotency_cache:
                event.status = EventStatus.DROPPED
                event.metadata["drop_reason"] = "duplicate_idempotency_key"
                self._event_history.append(event)
                return False
            self._idempotency_cache[event.idempotency_key] = now

        event.status = EventStatus.PROCESSING
        self._queues[event.priority].append(event)
        self._event_history.append(event)

        # Dispatch to matching subscribers
        self._dispatch_event(event)
        event.status = EventStatus.PROCESSED
        return True

    def _dispatch_event(self, event: EventPayload) -> None:
        """Invoke all matching pattern subscribers for the event."""
        for pattern, handlers in self._listeners.items():
            if pattern == "*" or fnmatch.fnmatch(event.event_type, pattern):
                for handler in handlers:
                    try:
                        handler(event)
                    except Exception as exc:
                        event.metadata["handler_error"] = str(exc)

    def _clean_idempotency_cache(self, current_time: float) -> None:
        """Evict expired idempotency keys."""
        cutoff = current_time - self.idempotency_ttl_sec
        expired = [k for k, ts in self._idempotency_cache.items() if ts < cutoff]
        for k in expired:
            del self._idempotency_cache[k]

    def get_history(self, limit: int = 50) -> list[EventPayload]:
        """Return most recent events in history."""
        return list(self._event_history)[-limit:]

    def clear(self) -> None:
        """Purge all event queues, cache, and history."""
        self._listeners.clear()
        self._idempotency_cache.clear()
        self._event_history.clear()
        for q in self._queues.values():
            q.clear()
