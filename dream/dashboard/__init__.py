"""Unified Web Dashboard & Real-Time Agent Control Tower for Dream."""

from __future__ import annotations

from dream.dashboard.aggregator import DashboardAggregator
from dream.dashboard.engine import DashboardEngine, get_dashboard_engine
from dream.dashboard.renderer import DashboardRenderer
from dream.dashboard.slash import handle_dashboard_command
from dream.dashboard.tools import (
    dashboard_export_metrics,
    dashboard_get_alerts,
    dashboard_get_overview,
    dashboard_get_subsystem_telemetry,
    dashboard_render_html,
    dashboard_reset,
    get_dashboard_tools,
    get_global_dashboard_engine,
    reset_global_dashboard_engine,
)
from dream.dashboard.types import (
    ControlTowerSnapshot,
    DashboardAlert,
    DashboardConfig,
    DashboardTheme,
    SubsystemStatus,
    SystemHealthStatus,
)

__all__ = [
    "ControlTowerSnapshot",
    "DashboardAggregator",
    "DashboardAlert",
    "DashboardConfig",
    "DashboardEngine",
    "DashboardRenderer",
    "DashboardTheme",
    "SubsystemStatus",
    "SystemHealthStatus",
    "dashboard_export_metrics",
    "dashboard_get_alerts",
    "dashboard_get_overview",
    "dashboard_get_subsystem_telemetry",
    "dashboard_render_html",
    "dashboard_reset",
    "get_dashboard_engine",
    "get_dashboard_tools",
    "get_global_dashboard_engine",
    "handle_dashboard_command",
    "reset_global_dashboard_engine",
]
