"""Real cancellation tokens. A stale UI flag is never enough."""

from __future__ import annotations

import threading
import time
from typing import Any


class CancellationToken:
    """Engine-side cancel flag that plan/goal loops actually check."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self.cancelled_at: float | None = None

    def cancel(self) -> None:
        if not self._event.is_set():
            self.cancelled_at = time.time()
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float) -> bool:
        return self._event.wait(timeout)

    def clear(self) -> None:
        self._event.clear()
        self.cancelled_at = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "cancelled": self.is_cancelled(),
            "cancelled_at": self.cancelled_at,
            "live": True,
        }
