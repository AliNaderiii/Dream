"""LLM tool bindings for Autonomous Self-Healing and Observability Engine."""

from __future__ import annotations

from typing import Any

from dream.healing.engine import HealingEngine

_GLOBAL_HEALING_ENGINE: HealingEngine | None = None


def get_global_healing_engine() -> HealingEngine:
    """Get or initialize singleton HealingEngine."""
    global _GLOBAL_HEALING_ENGINE
    if _GLOBAL_HEALING_ENGINE is None:
        _GLOBAL_HEALING_ENGINE = HealingEngine()
    return _GLOBAL_HEALING_ENGINE


def reset_global_healing_engine() -> None:
    """Reset singleton HealingEngine."""
    global _GLOBAL_HEALING_ENGINE
    _GLOBAL_HEALING_ENGINE = None


def healing_diagnose_failure(
    error_message: str,
    target_name: str = "generic_tool",
) -> dict[str, Any]:
    """Diagnose a tool failure or error message and generate a remediation plan."""
    engine = get_global_healing_engine()
    exc = RuntimeError(error_message)
    report = engine.diagnose_and_heal(exc, target_name=target_name)
    return {"success": True, "report": report.to_dict()}


def healing_run_chaos_test(
    fault_type: str = "rate_limit",
    target_name: str = "web_search",
) -> dict[str, Any]:
    """Inject a synthetic failure (rate limit, timeout, schema) to verify self-recovery."""
    engine = get_global_healing_engine()
    report = engine.run_chaos_test(fault_type_str=fault_type, target_name=target_name)
    return {"success": True, "report": report.to_dict()}


def telemetry_get_health_metrics() -> dict[str, Any]:
    """Retrieve operational health metrics, error rates, and latency percentiles."""
    engine = get_global_healing_engine()
    metrics = engine.get_health_metrics()
    return {"success": True, "metrics": metrics.to_dict()}


def telemetry_export_report() -> dict[str, Any]:
    """Export formatted Markdown report of system observability and resilience."""
    engine = get_global_healing_engine()
    report_md = engine.format_telemetry_report()
    return {"success": True, "markdown_report": report_md}


def telemetry_export_spans(limit: int = 50) -> dict[str, Any]:
    """Export recent execution trace spans."""
    engine = get_global_healing_engine()
    spans = engine.tracer.export_spans(limit=limit)
    return {"success": True, "spans": spans}


def telemetry_reset_all() -> dict[str, Any]:
    """Reset telemetry metrics and fault logs."""
    engine = get_global_healing_engine()
    engine.reset()
    return {"success": True, "message": "داده‌های پایش و تلمتری بازنشانی شدند."}


def get_healing_tools() -> list[Any]:
    """Return healing and telemetry tool functions for agent registration."""
    return [
        healing_diagnose_failure,
        healing_run_chaos_test,
        telemetry_get_health_metrics,
        telemetry_export_report,
        telemetry_export_spans,
        telemetry_reset_all,
    ]
