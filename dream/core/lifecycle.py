"""Agent Kernel Lifecycle State Machine and Graceful Hook Manager."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from dream.core.types import KernelState

logger = logging.getLogger(__name__)


class KernelLifecycleManager:
    """Manages operational states, startup transitions, and runtime lifecycle hooks."""

    def __init__(self) -> None:
        self.state: KernelState = KernelState.UNINITIALIZED
        self._start_time: float = 0.0
        self._cold_start_time_ms: float = 0.0
        self._hooks: dict[str, list[Callable[[], None]]] = {
            "on_start": [],
            "on_turn_start": [],
            "on_turn_end": [],
            "on_reload": [],
            "on_shutdown": [],
        }
        self._lock = threading.RLock()

    @property
    def uptime_sec(self) -> float:
        """Calculate active running uptime in seconds."""
        return time.time() - self._start_time if self._start_time > 0 else 0.0

    @property
    def cold_start_time_ms(self) -> float:
        """Time taken to transition from uninitialized to running."""
        return self._cold_start_time_ms

    def register_hook(self, event_name: str, hook_fn: Callable[[], None]) -> None:
        """Register a lifecycle event listener hook."""
        with self._lock:
            if event_name in self._hooks:
                self._hooks[event_name].append(hook_fn)

    def trigger_hooks(self, event_name: str) -> None:
        """Execute all hooks registered for an event."""
        with self._lock:
            for hook in self._hooks.get(event_name, []):
                try:
                    hook()
                except Exception as e:
                    logger.warning("Kernel hook execution failed for '%s': %s", event_name, e)

    def boot(self) -> float:
        """Boot kernel state from uninitialized to running with cold-start timing."""
        with self._lock:
            t0 = time.perf_counter()
            self.state = KernelState.INITIALIZING
            self._start_time = time.time()

            self.trigger_hooks("on_start")

            self.state = KernelState.RUNNING
            t1 = time.perf_counter()
            self._cold_start_time_ms = (t1 - t0) * 1000.0
            return self._cold_start_time_ms

    def pause(self) -> None:
        """Pause kernel execution."""
        with self._lock:
            if self.state == KernelState.RUNNING:
                self.state = KernelState.PAUSED

    def resume(self) -> None:
        """Resume kernel execution."""
        with self._lock:
            if self.state == KernelState.PAUSED:
                self.state = KernelState.RUNNING

    def hot_reload(self) -> dict[str, Any]:
        """Perform zero-downtime hot reload of plugins and configurations."""
        with self._lock:
            prev_state = self.state
            self.state = KernelState.HOT_RELOADING
            t0 = time.perf_counter()

            self.trigger_hooks("on_reload")

            t1 = time.perf_counter()
            reload_duration_ms = (t1 - t0) * 1000.0
            next_st = prev_state if prev_state != KernelState.HOT_RELOADING else KernelState.RUNNING
            self.state = next_st

            return {
                "success": True,
                "reload_duration_ms": round(reload_duration_ms, 2),
                "state": self.state.value,
                "summary_fa": f"بارگذاری مجدد گرم در {reload_duration_ms:.2f}ms انجام شد.",
            }

    def shutdown(self) -> None:
        """Perform graceful teardown of kernel and registered subsystems."""
        with self._lock:
            self.state = KernelState.SHUTTING_DOWN
            self.trigger_hooks("on_shutdown")
            self.state = KernelState.SHUTDOWN

    def reset(self) -> None:
        """Reset lifecycle manager to uninitialized initial state."""
        with self._lock:
            self.state = KernelState.UNINITIALIZED
            self._start_time = 0.0
            self._cold_start_time_ms = 0.0
            for k in self._hooks:
                self._hooks[k].clear()
