"""Comprehensive tests for Unified Web Dashboard & Real-Time Control Tower Subsystem."""

from __future__ import annotations

import json

import pytest

from dream.dashboard.aggregator import DashboardAggregator
from dream.dashboard.engine import DashboardEngine
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
    reset_global_dashboard_engine,
)
from dream.dashboard.types import (
    ControlTowerSnapshot,
    DashboardConfig,
    DashboardTheme,
    SystemHealthStatus,
)
from dream.tools.toolsets import get_toolset


@pytest.fixture(autouse=True)
def cleanup_dashboard() -> None:
    reset_global_dashboard_engine()
    yield
    reset_global_dashboard_engine()


def test_toolset_includes_dashboard() -> None:
    """Verify dashboard toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("dashboard")
    assert ts is not None
    assert ts.name == "dashboard"
    assert "dashboard_get_overview" in ts.tools
    assert "dashboard_render_html" in ts.tools
    assert "dashboard_export_metrics" in ts.tools


def test_dashboard_aggregator_snapshot() -> None:
    """Test telemetry collection across all subsystems and health calculation."""
    agg = DashboardAggregator()
    snap = agg.collect_snapshot()

    assert isinstance(snap, ControlTowerSnapshot)
    assert snap.total_subsystems >= 10
    assert snap.overall_health == SystemHealthStatus.HEALTHY
    assert "swarm" in snap.subsystems
    assert "knowledge" in snap.subsystems
    assert "cache" in snap.subsystems
    assert "duplex" in snap.subsystems
    assert "rbac" in snap.subsystems
    assert "reactive" in snap.subsystems
    assert snap.token_economics["tokens_saved_by_cache"] > 0


def test_dashboard_html_and_svg_rendering() -> None:
    """Test self-contained standalone HTML and SVG dashboard renderer."""
    agg = DashboardAggregator()
    snap = agg.collect_snapshot()

    cfg = DashboardConfig(theme=DashboardTheme.DARK, locale="fa")
    html = DashboardRenderer.render_html(snap, cfg)

    assert "<!DOCTYPE html>" in html
    assert "Dream Agent Control Tower" in html
    assert 'dir="rtl"' in html
    assert "<svg" in html
    assert "Dream Core" in html
    assert "نقشه توپولوژی" in html


def test_dashboard_engine_telemetry_and_reports() -> None:
    """Test DashboardEngine overview, detailed metrics, markdown export, and JSON."""
    engine = DashboardEngine()

    # Overview
    ov = engine.get_overview()
    assert ov["overall_health"] == "healthy"
    assert ov["total_subsystems"] >= 10
    assert "swarm" in ov["subsystems_overview"]

    # Subsystem specific telemetry
    res_swarm = engine.get_subsystem_telemetry("swarm")
    assert res_swarm["success"] is True
    assert res_swarm["subsystem"]["name"] == "swarm"

    res_invalid = engine.get_subsystem_telemetry("non_existent")
    assert res_invalid["success"] is False

    # Markdown export
    md = engine.export_metrics_markdown()
    assert "گزارش وضعیت برج مراقبت دریم" in md
    assert "گراف دانش زمان‌مند" in md

    # JSON export
    js = engine.export_json()
    data = json.loads(js)
    assert "snapshot_id" in data
    assert "subsystems" in data


def test_dashboard_tools_and_slash_commands() -> None:
    """Test Dashboard LLM agent tools and slash command dispatcher."""
    tools = get_dashboard_tools()
    assert len(tools) >= 5

    # 1. Tool: overview
    res_ov = dashboard_get_overview()
    assert res_ov["success"] is True
    assert res_ov["overall_health"] == "healthy"

    # 2. Tool: subsystem
    res_sub = dashboard_get_subsystem_telemetry("cache")
    assert res_sub["success"] is True
    assert "hit_ratio_pct" in res_sub["subsystem"]["metrics"]

    # 3. Tool: render HTML
    res_html = dashboard_render_html(theme="dark", locale="fa")
    assert res_html["success"] is True
    assert "<!DOCTYPE html>" in res_html["html_content"]

    # 4. Tool: export metrics
    res_m = dashboard_export_metrics(format="markdown")
    assert res_m["success"] is True
    assert "برج مراقبت دریم" in res_m["report_markdown"]

    # 5. Tool: alerts
    res_alt = dashboard_get_alerts()
    assert res_alt["success"] is True

    # 6. Slash commands
    s_help = handle_dashboard_command("")
    assert "راهنمای دستورات برج مراقبت" in s_help

    # Slash: overview
    s_ov = handle_dashboard_command("overview")
    assert "خلاصه وضعیت برج مراقبت" in s_ov

    # Slash: subsystem
    s_sub = handle_dashboard_command("subsystem duplex")
    assert "گفتگوی صوتی زنده" in s_sub

    # Slash: html
    s_html = handle_dashboard_command("html dark fa")
    assert "ایجاد شد" in s_html or "تولید شد" in s_html

    # Slash: report
    s_rep = handle_dashboard_command("report")
    assert "ماتریس سلامت" in s_rep

    # Slash: alerts
    s_alt = handle_dashboard_command("alerts")
    assert "هشدار" in s_alt

    # Slash: reset
    s_res = handle_dashboard_command("reset")
    assert "بازنشانی شد" in s_res

    # Tool reset
    t_res = dashboard_reset()
    assert t_res["success"] is True
