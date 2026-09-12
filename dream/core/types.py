"""Data models and type definitions for Dream Agent Kernel Lifecycle."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class KernelState(str, Enum):
    """Lifecycle operational state of the Dream agent kernel."""

    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    HOT_RELOADING = "hot_reloading"
    SHUTTING_DOWN = "shutting_down"
    SHUTDOWN = "shutdown"


class SubsystemLoadStatus(str, Enum):
    """Loading status of a lazy-loaded subsystem."""

    REGISTERED_LAZY = "registered_lazy"
    INSTANTIATING = "instantiating"
    ACTIVE = "active"
    FAILED = "failed"


@dataclass
class SubsystemDescriptor:
    """Metadata descriptor of a lazy-loaded Dream subsystem."""

    name: str
    display_name_fa: str
    factory_path: str
    status: SubsystemLoadStatus = SubsystemLoadStatus.REGISTERED_LAZY
    load_time_ms: float = 0.0
    total_invocations: int = 0
    last_invoked_timestamp: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize descriptor to dictionary."""
        return {
            "name": self.name,
            "display_name_fa": self.display_name_fa,
            "factory_path": self.factory_path,
            "status": self.status.value,
            "load_time_ms": round(self.load_time_ms, 2),
            "total_invocations": self.total_invocations,
            "last_invoked": (
                round(self.last_invoked_timestamp, 2) if self.last_invoked_timestamp else None
            ),
            "metadata": self.metadata,
        }


@dataclass
class KernelLifecycleSnapshot:
    """Snapshot of kernel state, memory metrics, and loaded subsystems."""

    kernel_id: str
    state: KernelState
    uptime_sec: float
    cold_start_time_ms: float
    total_subsystems_registered: int
    active_subsystems_loaded: int
    subsystems: dict[str, SubsystemDescriptor] = field(default_factory=dict)
    memory_profile: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize snapshot to dictionary."""
        return {
            "kernel_id": self.kernel_id,
            "state": self.state.value,
            "uptime_sec": round(self.uptime_sec, 2),
            "cold_start_time_ms": round(self.cold_start_time_ms, 2),
            "total_subsystems_registered": self.total_subsystems_registered,
            "active_subsystems_loaded": self.active_subsystems_loaded,
            "subsystems": {k: v.to_dict() for k, v in self.subsystems.items()},
            "memory_profile": self.memory_profile,
            "timestamp": round(self.timestamp, 2),
        }
