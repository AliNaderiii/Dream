"""Data models and type definitions for Unified Web Dashboard & Control Tower."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SystemHealthStatus(str, Enum):
    """Overall health state of Dream subsystems."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    MAINTENANCE = "maintenance"


class DashboardTheme(str, Enum):
    """UI Color theme for the dashboard."""

    DARK = "dark"
    LIGHT = "light"
    CYBERPUNK = "cyberpunk"


@dataclass
class SubsystemStatus:
    """Operational health and metric summary for an individual subsystem."""

    name: str
    display_name_fa: str
    status: SystemHealthStatus = SystemHealthStatus.HEALTHY
    uptime_sec: float = 0.0
    active_items_count: int = 0
    total_operations: int = 0
    error_rate_pct: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize status to dictionary."""
        return {
            "name": self.name,
            "display_name_fa": self.display_name_fa,
            "status": self.status.value,
            "uptime_sec": round(self.uptime_sec, 2),
            "active_items_count": self.active_items_count,
            "total_operations": self.total_operations,
            "error_rate_pct": round(self.error_rate_pct, 2),
            "metrics": self.metrics,
        }


@dataclass
class DashboardAlert:
    """Active diagnostic warning or health alert."""

    alert_id: str
    subsystem: str
    severity: str  # "info", "warning", "critical"
    message_fa: str
    timestamp: float = field(default_factory=time.time)
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize alert to dictionary."""
        return {
            "alert_id": self.alert_id,
            "subsystem": self.subsystem,
            "severity": self.severity,
            "message_fa": self.message_fa,
            "timestamp": self.timestamp,
            "resolved": self.resolved,
        }


@dataclass
class ControlTowerSnapshot:
    """Comprehensive snapshot of all agent operations and system state."""

    snapshot_id: str
    timestamp: float = field(default_factory=time.time)
    overall_health: SystemHealthStatus = SystemHealthStatus.HEALTHY
    total_subsystems: int = 0
    healthy_subsystems: int = 0
    subsystems: dict[str, SubsystemStatus] = field(default_factory=dict)
    active_alerts: list[DashboardAlert] = field(default_factory=list)
    token_economics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize snapshot to dictionary."""
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp,
            "overall_health": self.overall_health.value,
            "total_subsystems": self.total_subsystems,
            "healthy_subsystems": self.healthy_subsystems,
            "subsystems": {k: v.to_dict() for k, v in self.subsystems.items()},
            "active_alerts": [a.to_dict() for a in self.active_alerts],
            "token_economics": self.token_economics,
            "metadata": self.metadata,
        }


@dataclass
class DashboardConfig:
    """Configuration parameters for the dashboard visualizer."""

    app_title: str = "Dream Agent Control Tower | برج مراقبت دریم"
    theme: DashboardTheme = DashboardTheme.DARK
    locale: str = "fa"
    refresh_interval_sec: int = 5
    enable_svg_topomap: bool = True
