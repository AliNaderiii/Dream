"""Fast Mode controller for low-latency agent execution and model route gating."""

from __future__ import annotations

import threading
from enum import Enum
from typing import Any


class FastMode(str, Enum):
    """Execution latency and model routing profiles."""

    AUTO = "auto"      # Dynamically switch between lightweight & full reasoning models
    COLD = "cold"      # Maximum reasoning depth, full context retention
    TURBO = "turbo"    # Low-latency mode with aggressive token pruning and concise output


class FastModeController:
    """Thread-safe controller managing global and per-session Fast Mode settings."""

    def __init__(self, default_mode: FastMode = FastMode.AUTO) -> None:
        self._lock = threading.RLock()
        self._mode = default_mode
        self._session_modes: dict[str, FastMode] = {}

    @property
    def mode(self) -> FastMode:
        with self._lock:
            return self._mode

    def set_mode(self, mode: FastMode | str, session_id: str | None = None) -> FastMode:
        """Update active Fast Mode globally or for a specific session."""
        val = FastMode(mode) if isinstance(mode, str) else mode
        with self._lock:
            if session_id:
                self._session_modes[session_id] = val
            else:
                self._mode = val
            return val

    def get_mode(self, session_id: str | None = None) -> FastMode:
        """Retrieve active Fast Mode for session or global fallback."""
        with self._lock:
            if session_id and session_id in self._session_modes:
                return self._session_modes[session_id]
            return self._mode

    def get_execution_params(self, session_id: str | None = None) -> dict[str, Any]:
        """Return tuning parameters for LLM request based on active mode."""
        current = self.get_mode(session_id)
        if current == FastMode.TURBO:
            return {
                "temperature": 0.2,
                "max_tokens": 1024,
                "stream": True,
                "prune_cot": True,
                "latency_priority": "high",
            }
        elif current == FastMode.COLD:
            return {
                "temperature": 0.7,
                "max_tokens": 4096,
                "stream": True,
                "prune_cot": False,
                "latency_priority": "standard",
            }
        else:  # AUTO
            return {
                "temperature": 0.5,
                "max_tokens": 2048,
                "stream": True,
                "prune_cot": False,
                "latency_priority": "adaptive",
            }


_GLOBAL_FAST_MODE_CONTROLLER: FastModeController | None = None


def get_fast_mode_controller() -> FastModeController:
    """Retrieve or initialize singleton FastModeController."""
    global _GLOBAL_FAST_MODE_CONTROLLER
    if _GLOBAL_FAST_MODE_CONTROLLER is None:
        _GLOBAL_FAST_MODE_CONTROLLER = FastModeController()
    return _GLOBAL_FAST_MODE_CONTROLLER


def reset_fast_mode_controller() -> None:
    """Reset global FastModeController for isolated unit testing."""
    global _GLOBAL_FAST_MODE_CONTROLLER
    _GLOBAL_FAST_MODE_CONTROLLER = None
