"""LLM agent tools and singleton managers for Web Dashboard & Control Tower."""

from __future__ import annotations

import logging
from typing import Any

from dream.dashboard.engine import DashboardEngine, get_dashboard_engine

logger = logging.getLogger(__name__)

_GLOBAL_DASHBOARD_ENGINE: DashboardEngine | None = None


def get_global_dashboard_engine() -> DashboardEngine:
    """Retrieve or initialize singleton DashboardEngine."""
    global _GLOBAL_DASHBOARD_ENGINE
    if _GLOBAL_DASHBOARD_ENGINE is None:
        _GLOBAL_DASHBOARD_ENGINE = get_dashboard_engine()
    return _GLOBAL_DASHBOARD_ENGINE


def reset_global_dashboard_engine() -> None:
    """Reset global DashboardEngine instance for test isolation."""
    global _GLOBAL_DASHBOARD_ENGINE
    if _GLOBAL_DASHBOARD_ENGINE is not None:
        _GLOBAL_DASHBOARD_ENGINE.reset()
    _GLOBAL_DASHBOARD_ENGINE = None


def dashboard_get_overview() -> dict[str, Any]:
    """Retrieve executive health summary and subsystem counts across Dream."""
    engine = get_global_dashboard_engine()
    return {"success": True, **engine.get_overview()}


def dashboard_get_subsystem_telemetry(subsystem_name: str) -> dict[str, Any]:
    """Retrieve fine-grained real-time metrics for a specific agent subsystem.

    Args:
        subsystem_name: Name of subsystem (e.g. 'swarm', 'cache', 'duplex', 'rbac').
    """
    engine = get_global_dashboard_engine()
    return engine.get_subsystem_telemetry(subsystem_name)


def dashboard_render_html(
    theme: str = "dark",
    locale: str = "fa",
) -> dict[str, Any]:
    """Render a standalone, self-contained HTML/SVG visual dashboard.

    Args:
        theme: UI theme ('dark', 'light', 'cyberpunk').
        locale: Language layout ('fa' for Persian RTL, 'en' for English).
    """
    engine = get_global_dashboard_engine()
    html_code = engine.render_html(theme=theme, locale=locale)
    return {
        "success": True,
        "theme": theme,
        "locale": locale,
        "html_content": html_code,
        "summary_fa": "داشبورد بصری برج مراقبت با موفقیت تولید شد.",
    }


def dashboard_export_metrics(format: str = "markdown") -> dict[str, Any]:
    """Export aggregated operational telemetry as Markdown or JSON.

    Args:
        format: Output format ('markdown' or 'json').
    """
    engine = get_global_dashboard_engine()
    if format.lower() == "json":
        return {"success": True, "format": "json", "data": engine.export_json()}
    return {
        "success": True,
        "format": "markdown",
        "report_markdown": engine.export_metrics_markdown(),
    }


def dashboard_get_alerts() -> dict[str, Any]:
    """Inspect active diagnostic warnings and anomalies."""
    engine = get_global_dashboard_engine()
    snap = engine.get_snapshot()
    return {
        "success": True,
        "total_alerts": len(snap.active_alerts),
        "alerts": [a.to_dict() for a in snap.active_alerts],
    }


def dashboard_reset() -> dict[str, Any]:
    """Reset telemetry timers and aggregator."""
    reset_global_dashboard_engine()
    return {"success": True, "message_fa": "برج مراقبت داشبورد با موفقیت بازنشانی شد."}


def get_dashboard_tools() -> list[dict[str, Any]]:
    """Return tool manifests for LLM registration."""
    return [
        {
            "name": "dashboard_get_overview",
            "description": "Get an executive status overview of all agent subsystems.",
            "parameters": {"type": "object", "properties": {}},
            "handler": dashboard_get_overview,
        },
        {
            "name": "dashboard_get_subsystem_telemetry",
            "description": "Inspect fine-grained operational metrics for a specific subsystem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subsystem_name": {"type": "string"},
                },
                "required": ["subsystem_name"],
            },
            "handler": dashboard_get_subsystem_telemetry,
        },
        {
            "name": "dashboard_render_html",
            "description": "Generate a standalone interactive HTML/SVG Control Tower dashboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "theme": {
                        "type": "string",
                        "enum": ["dark", "light", "cyberpunk"],
                        "default": "dark",
                    },
                    "locale": {"type": "string", "enum": ["fa", "en"], "default": "fa"},
                },
            },
            "handler": dashboard_render_html,
        },
        {
            "name": "dashboard_export_metrics",
            "description": "Export integrated telemetry table as Markdown or JSON.",
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "default": "markdown",
                    },
                },
            },
            "handler": dashboard_export_metrics,
        },
        {
            "name": "dashboard_get_alerts",
            "description": "Inspect active diagnostic alerts across the system.",
            "parameters": {"type": "object", "properties": {}},
            "handler": dashboard_get_alerts,
        },
    ]
