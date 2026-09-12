"""Autonomous Self-Healing, Chaos Fault Injection & Telemetry Observability Subsystem."""

from __future__ import annotations

from dream.healing.chaos import ChaosSimulator
from dream.healing.engine import HealingEngine
from dream.healing.slash import handle_healing_slash_command
from dream.healing.telemetry import TelemetryTracer
from dream.healing.tools import (
    get_global_healing_engine,
    get_healing_tools,
    healing_diagnose_failure,
    healing_run_chaos_test,
    reset_global_healing_engine,
    telemetry_export_report,
    telemetry_export_spans,
    telemetry_get_health_metrics,
    telemetry_reset_all,
)
from dream.healing.types import (
    FaultType,
    HealingReport,
    RecoveryAction,
    SpanStatus,
    SystemHealthMetrics,
    TelemetrySpan,
)

# Auto-register healing toolset
try:
    from dream.tools.toolsets import Toolset, register_toolset

    register_toolset(
        Toolset(
            name="healing",
            description="Autonomous error diagnosis, self-healing recovery, telemetry, and chaos testing.",
            tools=[
                "healing_diagnose_failure",
                "healing_run_chaos_test",
                "telemetry_get_health_metrics",
                "telemetry_export_report",
                "telemetry_export_spans",
                "telemetry_reset_all",
            ],
            metadata={"category": "healing", "builtin": True},
        )
    )
except Exception:
    pass

__all__ = [
    "ChaosSimulator",
    "FaultType",
    "HealingEngine",
    "HealingReport",
    "RecoveryAction",
    "SpanStatus",
    "SystemHealthMetrics",
    "TelemetrySpan",
    "TelemetryTracer",
    "get_global_healing_engine",
    "get_healing_tools",
    "handle_healing_slash_command",
    "healing_diagnose_failure",
    "healing_run_chaos_test",
    "reset_global_healing_engine",
    "telemetry_export_report",
    "telemetry_export_spans",
    "telemetry_get_health_metrics",
    "telemetry_reset_all",
]
