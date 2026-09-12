"""Unit and integration tests for Autonomous Self-Healing, Chaos Fault Injection & Telemetry."""

from __future__ import annotations

import pytest

from dream.healing import (
    ChaosSimulator,
    FaultType,
    HealingEngine,
    RecoveryAction,
    SpanStatus,
    TelemetryTracer,
    handle_healing_slash_command,
    healing_diagnose_failure,
    healing_run_chaos_test,
    reset_global_healing_engine,
    telemetry_export_report,
    telemetry_get_health_metrics,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_healing_engine() -> None:
    reset_global_healing_engine()
    yield
    reset_global_healing_engine()


def test_toolset_includes_healing() -> None:
    """Verify healing toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("healing")
    assert ts is not None
    assert "healing_diagnose_failure" in ts.tools
    assert "healing_run_chaos_test" in ts.tools
    assert "telemetry_get_health_metrics" in ts.tools
    assert "healing" in BUILTIN_TOOLSETS


def test_telemetry_span_lifecycle_and_metrics() -> None:
    """Verify span tracking, status updates, and resilience score calculation."""
    tracer = TelemetryTracer()

    # Span 1: OK
    s1 = tracer.start_span("tool_search", {"query": "deep learning"})
    tracer.end_span(s1.span_id, status=SpanStatus.OK)

    # Span 2: Recovered
    s2 = tracer.start_span("api_call")
    tracer.record_recovery(s2.span_id, RecoveryAction.EXPONENTIAL_BACKOFF)
    tracer.end_span(s2.span_id, status=SpanStatus.RECOVERED)

    metrics = tracer.compute_health_metrics()
    assert metrics.total_spans == 2
    assert metrics.error_count == 0
    assert metrics.recovered_count == 1
    assert metrics.resilience_score == 1.0


def test_chaos_simulator_fault_injection() -> None:
    """Verify chaos simulator raises appropriate synthetic exceptions."""
    chaos = ChaosSimulator()

    exc_rate = chaos.simulate_fault(FaultType.RATE_LIMIT, "llm_gateway")
    assert isinstance(exc_rate, ConnectionError)
    assert "429" in str(exc_rate)

    exc_timeout = chaos.simulate_fault(FaultType.TIMEOUT, "database_query")
    assert isinstance(exc_timeout, TimeoutError)

    history = chaos.get_injected_history()
    assert len(history) == 2


def test_healing_engine_diagnosis_and_remediation() -> None:
    """Verify fault classification, recovery planning, and report generation."""
    engine = HealingEngine()

    # Rate limit -> Exponential backoff
    rep1 = engine.diagnose_and_heal(
        exc=ConnectionError("HTTP 429 Too Many Requests"),
        target_name="search_engine",
    )
    assert rep1.fault_type == FaultType.RATE_LIMIT
    assert rep1.action_taken == RecoveryAction.EXPONENTIAL_BACKOFF
    assert rep1.success is True

    # Schema mismatch -> Param mutation
    rep2 = engine.diagnose_and_heal(
        exc=ValueError("Schema validation failed: unexpected parameter 'foo'"),
        target_name="parser_tool",
    )
    assert rep2.fault_type == FaultType.SCHEMA_MISMATCH
    assert rep2.action_taken == RecoveryAction.PARAM_MUTATION

    # Run full chaos test
    chaos_rep = engine.run_chaos_test("timeout", "web_crawler")
    assert chaos_rep.fault_type == FaultType.TIMEOUT
    assert chaos_rep.action_taken == RecoveryAction.FALLBACK_TOOL


def test_telemetry_percentile_latencies() -> None:
    """Verify p50 and p95 latency percentiles."""
    tracer = TelemetryTracer()

    for i in range(10):
        span = tracer.start_span(f"op_{i}")
        # Mark end time with custom span attributes
        tracer.end_span(span.span_id, status=SpanStatus.OK)

    metrics = tracer.compute_health_metrics()
    assert metrics.total_spans == 10
    assert metrics.p50_latency_ms >= 0.0
    assert metrics.p95_latency_ms >= 0.0


def test_healing_tools_and_slash_commands() -> None:
    """Verify LLM agent tools and /heal, /chaos, /telemetry slash commands."""
    # Tool: diagnose failure
    res_diag = healing_diagnose_failure(
        error_message="TimeoutError: 15.0s exceeded during file download",
        target_name="downloader",
    )
    assert res_diag["success"] is True
    assert res_diag["report"]["fault_type"] == "timeout"

    # Tool: run chaos test
    res_chaos = healing_run_chaos_test(fault_type="rate_limit", target_name="api")
    assert res_chaos["success"] is True
    assert res_chaos["report"]["action_taken"] == "exponential_backoff"

    # Tool: get metrics
    res_met = telemetry_get_health_metrics()
    assert res_met["success"] is True
    assert res_met["metrics"]["total_spans"] >= 1

    # Tool: export report
    res_rep = telemetry_export_report()
    assert res_rep["success"] is True
    assert "Telemetry & Health" in res_rep["markdown_report"]

    # Slash: /heal
    slash_heal = handle_healing_slash_command("/heal Socket closed unexpectedly")
    assert "خودترمیم" in slash_heal

    # Slash: /chaos
    slash_chaos = handle_healing_slash_command("/chaos timeout web_crawler")
    assert "آزمایش آشوب" in slash_chaos

    # Slash: /telemetry
    slash_tel = handle_healing_slash_command("/telemetry")
    assert "Telemetry & Health" in slash_tel

    # Slash: /telemetry reset
    slash_reset = handle_healing_slash_command("/telemetry reset")
    assert "بازنشانی شد" in slash_reset
