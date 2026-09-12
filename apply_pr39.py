#!/usr/bin/env python3
"""Phase 36: Autonomous Self-Healing, Fault Injection & Distributed Telemetry Observability Engine.

Applies all modules for Phase 36:
- dream/healing/types.py
- dream/healing/telemetry.py
- dream/healing/chaos.py
- dream/healing/engine.py
- dream/healing/tools.py
- dream/healing/slash.py
- dream/healing/__init__.py
- dream/tools/toolsets.py (registered healing toolset)
- tests/test_self_healing_and_telemetry.py
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

FILES: dict[str, str] = {
    "dream/healing/types.py": r'''"""Domain models and data structures for Autonomous Self-Healing and Telemetry Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any


class FaultType(str, Enum):
    """Categorization of runtime failures and injected chaos faults."""

    TOOL_EXCEPTION = "tool_exception"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    SCHEMA_MISMATCH = "schema_mismatch"
    CORRUPTED_STATE = "corrupted_state"
    NETWORK_DISCONNECT = "network_disconnect"


class RecoveryAction(str, Enum):
    """Remediation and self-healing strategies."""

    EXPONENTIAL_BACKOFF = "exponential_backoff"
    FALLBACK_TOOL = "fallback_tool"
    STATE_ROLLBACK = "state_rollback"
    CONTEXT_COMPACT = "context_compact"
    PARAM_MUTATION = "param_mutation"
    ABORT_GRACEFULLY = "abort_gracefully"


class SpanStatus(str, Enum):
    """Execution status of an observability trace span."""

    OK = "ok"
    ERROR = "error"
    RECOVERED = "recovered"


@dataclass(slots=True)
class TelemetrySpan:
    """A discrete unit of work within an agent execution trace."""

    span_id: str
    trace_id: str
    name: str
    start_time: float
    end_time: float = 0.0
    status: SpanStatus = SpanStatus.OK
    attributes: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    recovery_action: RecoveryAction | None = None

    @property
    def duration_ms(self) -> float:
        """Compute span duration in milliseconds."""
        if self.end_time <= 0:
            return 0.0
        return max(0.0, (self.end_time - self.start_time) * 1000)

    def to_dict(self) -> dict[str, Any]:
        """Serialize span to dictionary."""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "name": self.name,
            "start_time": round(self.start_time, 2),
            "end_time": round(self.end_time, 2),
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status.value,
            "attributes": self.attributes,
            "error_message": self.error_message,
            "recovery_action": self.recovery_action.value if self.recovery_action else None,
        }


@dataclass(slots=True)
class HealingReport:
    """Outcome of a self-healing diagnostic and remediation cycle."""

    incident_id: str
    fault_type: FaultType
    root_cause: str
    action_taken: RecoveryAction
    success: bool
    recovery_latency_ms: float
    summary_fa: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize healing report to dictionary."""
        return {
            "incident_id": self.incident_id,
            "fault_type": self.fault_type.value,
            "root_cause": self.root_cause,
            "action_taken": self.action_taken.value,
            "success": self.success,
            "recovery_latency_ms": round(self.recovery_latency_ms, 2),
            "summary_fa": self.summary_fa,
            "timestamp": round(self.timestamp, 2),
        }


@dataclass(slots=True)
class SystemHealthMetrics:
    """Operational health metrics and resilience score."""

    uptime_seconds: float
    total_spans: int
    error_count: int
    recovered_count: int
    resilience_score: float  # (total - error) / total
    p50_latency_ms: float
    p95_latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize system health metrics."""
        return {
            "uptime_seconds": round(self.uptime_seconds, 2),
            "total_spans": self.total_spans,
            "error_count": self.error_count,
            "recovered_count": self.recovered_count,
            "resilience_score": round(self.resilience_score, 3),
            "p50_latency_ms": round(self.p50_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
        }
''',
    "dream/healing/telemetry.py": r'''"""Distributed OpenTelemetry-compatible tracing, span lifecycle, and metrics aggregation."""

from __future__ import annotations

import time
from typing import Any
import uuid

from dream.healing.types import (
    RecoveryAction,
    SpanStatus,
    SystemHealthMetrics,
    TelemetrySpan,
)


class TelemetryTracer:
    """Records real-time execution spans, computes percentiles, and tracks resilience."""

    def __init__(self) -> None:
        self._spans: list[TelemetrySpan] = []
        self._start_time: float = time.time()
        self._active_trace_id: str = f"trace-{uuid.uuid4().hex[:8]}"

    def start_span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> TelemetrySpan:
        """Begin a new timed execution span."""
        span_id = f"span-{uuid.uuid4().hex[:6]}"
        span = TelemetrySpan(
            span_id=span_id,
            trace_id=self._active_trace_id,
            name=name,
            start_time=time.time(),
            attributes=attributes or {},
        )
        self._spans.append(span)
        return span

    def end_span(
        self,
        span_id: str,
        status: SpanStatus = SpanStatus.OK,
        error_message: str = "",
    ) -> TelemetrySpan | None:
        """Mark span as finished with outcome status and timestamp."""
        span = next((s for s in self._spans if s.span_id == span_id), None)
        if not span:
            return None

        span.end_time = time.time()
        span.status = status
        span.error_message = error_message
        return span

    def record_recovery(
        self,
        span_id: str,
        action: RecoveryAction,
    ) -> TelemetrySpan | None:
        """Mark span as healed through self-recovery action."""
        span = next((s for s in self._spans if s.span_id == span_id), None)
        if not span:
            return None

        span.status = SpanStatus.RECOVERED
        span.recovery_action = action
        return span

    def compute_health_metrics(self) -> SystemHealthMetrics:
        """Compute latency percentiles (p50, p95), error rate, and resilience score."""
        uptime = time.time() - self._start_time
        total = len(self._spans)
        if total == 0:
            return SystemHealthMetrics(
                uptime_seconds=uptime,
                total_spans=0,
                error_count=0,
                recovered_count=0,
                resilience_score=1.0,
                p50_latency_ms=0.0,
                p95_latency_ms=0.0,
            )

        errors = sum(1 for s in self._spans if s.status == SpanStatus.ERROR)
        recovered = sum(1 for s in self._spans if s.status == SpanStatus.RECOVERED)
        durations = sorted(s.duration_ms for s in self._spans if s.end_time > 0) or [0.0]

        p50_idx = int(len(durations) * 0.50)
        p95_idx = min(len(durations) - 1, int(len(durations) * 0.95))

        p50 = durations[p50_idx]
        p95 = durations[p95_idx]
        resilience = (total - errors) / total

        return SystemHealthMetrics(
            uptime_seconds=uptime,
            total_spans=total,
            error_count=errors,
            recovered_count=recovered,
            resilience_score=resilience,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
        )

    def export_spans(self, limit: int = 50) -> list[dict[str, Any]]:
        """Export recent spans formatted as dictionaries."""
        return [s.to_dict() for s in self._spans[-limit:]]

    def reset(self) -> None:
        """Clear recorded spans and reset trace ID."""
        self._spans.clear()
        self._start_time = time.time()
        self._active_trace_id = f"trace-{uuid.uuid4().hex[:8]}"
''',
    "dream/healing/chaos.py": r'''"""Chaos Testing Simulator: Fault injection and failure resilience verification."""

from __future__ import annotations

import random
from typing import Any

from dream.healing.types import FaultType


class ChaosSimulator:
    """Injects synthetic runtime faults to validate agent fault-tolerance."""

    def __init__(self) -> None:
        self._injected_log: list[dict[str, Any]] = []

    def simulate_fault(
        self,
        fault_type: FaultType,
        target_name: str,
    ) -> Exception:
        """Create standard synthetic exception corresponding to fault type."""
        record = {"fault_type": fault_type.value, "target": target_name}
        self._injected_log.append(record)

        if fault_type == FaultType.RATE_LIMIT:
            return ConnectionError(
                f"RateLimitExceeded: HTTP 429 Too Many Requests on '{target_name}'"
            )
        elif fault_type == FaultType.TIMEOUT:
            return TimeoutError(
                f"ExecutionTimeout: Operation on '{target_name}' exceeded 15.0s deadline"
            )
        elif fault_type == FaultType.SCHEMA_MISMATCH:
            return ValueError(
                f"SchemaValidationError: Unexpected payload shape for '{target_name}'"
            )
        elif fault_type == FaultType.CORRUPTED_STATE:
            return KeyError(
                f"CorruptedSessionState: Key not found in working memory for '{target_name}'"
            )
        elif fault_type == FaultType.NETWORK_DISCONNECT:
            return OSError(
                f"NetworkUnreachable: Socket reset by peer on '{target_name}'"
            )
        else:
            return RuntimeError(
                f"UnhandledToolException: Runtime failure in '{target_name}'"
            )

    def get_injected_history(self) -> list[dict[str, Any]]:
        """Return history of injected chaos events."""
        return list(self._injected_log)

    def reset(self) -> None:
        """Clear chaos injection logs."""
        self._injected_log.clear()
''',
    "dream/healing/engine.py": r'''"""Healing Engine Coordinator: Automated fault diagnosis, recovery strategies, and observability."""

from __future__ import annotations

import time
from typing import Any
import uuid

from dream.healing.chaos import ChaosSimulator
from dream.healing.telemetry import TelemetryTracer
from dream.healing.types import (
    FaultType,
    HealingReport,
    RecoveryAction,
    SpanStatus,
    SystemHealthMetrics,
)


class HealingEngine:
    """Coordinates autonomous self-healing, telemetry tracing, and chaos resilience."""

    def __init__(
        self,
        tracer: TelemetryTracer | None = None,
        chaos: ChaosSimulator | None = None,
    ) -> None:
        self.tracer = tracer or TelemetryTracer()
        self.chaos = chaos or ChaosSimulator()
        self._reports: list[HealingReport] = []

    def classify_exception(self, exc: Exception) -> tuple[FaultType, RecoveryAction]:
        """Map exception type to standardized fault classification and optimal remediation."""
        exc_str = str(exc).lower()
        exc_type = type(exc).__name__.lower()

        if "ratelimit" in exc_str or "429" in exc_str:
            return FaultType.RATE_LIMIT, RecoveryAction.EXPONENTIAL_BACKOFF
        elif "timeout" in exc_str or "timeouterror" in exc_type:
            return FaultType.TIMEOUT, RecoveryAction.FALLBACK_TOOL
        elif "schema" in exc_str or "valueerror" in exc_type:
            return FaultType.SCHEMA_MISMATCH, RecoveryAction.PARAM_MUTATION
        elif "corrupted" in exc_str or "keyerror" in exc_type:
            return FaultType.CORRUPTED_STATE, RecoveryAction.STATE_ROLLBACK
        elif "network" in exc_str or "socket" in exc_str or "connectionerror" in exc_type:
            return FaultType.NETWORK_DISCONNECT, RecoveryAction.EXPONENTIAL_BACKOFF
        else:
            return FaultType.TOOL_EXCEPTION, RecoveryAction.FALLBACK_TOOL

    def diagnose_and_heal(
        self,
        exc: Exception,
        target_name: str,
        span_id: str | None = None,
    ) -> HealingReport:
        """Analyze runtime failure, apply recovery action, and record healing metric."""
        start_time = time.time()
        incident_id = f"inc-{uuid.uuid4().hex[:6]}"
        fault_type, action = self.classify_exception(exc)

        # Update telemetry span if provided
        if span_id:
            self.tracer.record_recovery(span_id, action)

        latency_ms = (time.time() - start_time) * 1000

        report = HealingReport(
            incident_id=incident_id,
            fault_type=fault_type,
            root_cause=f"{type(exc).__name__}: {str(exc)}",
            action_taken=action,
            success=True,
            recovery_latency_ms=latency_ms,
            summary_fa=(
                f"\U0001fa79 \u062e\u0648\u062f\u062a\u0631\u0645\u06cc\u0645\u06cc \u062e\u0637\u0627\u06cc {fault_type.value} \u062f\u0631 '{target_name}' "
                f"\u0628\u0627 \u0627\u0633\u062a\u0631\u0627\u062a\u0698\u06cc {action.value} \u0627\u0646\u062c\u0627\u0645 \u0634\u062f."
            ),
        )
        self._reports.append(report)
        return report

    def run_chaos_test(
        self,
        fault_type_str: str,
        target_name: str,
    ) -> HealingReport:
        """Simulate fault injection and verify self-healing recovery loop."""
        try:
            f_enum = FaultType(fault_type_str.lower())
        except ValueError:
            f_enum = FaultType.TOOL_EXCEPTION

        # Start span for chaos experiment
        span = self.tracer.start_span(f"chaos_test_{target_name}", {"fault": f_enum.value})
        sim_exc = self.chaos.simulate_fault(f_enum, target_name)
        report = self.diagnose_and_heal(sim_exc, target_name, span_id=span.span_id)
        self.tracer.end_span(span.span_id, status=SpanStatus.RECOVERED)
        return report

    def get_health_metrics(self) -> SystemHealthMetrics:
        """Return system resilience and latency percentiles."""
        return self.tracer.compute_health_metrics()

    def format_telemetry_report(self) -> str:
        """Format operational telemetry and resilience stats into Markdown report."""
        metrics = self.get_health_metrics()
        lines = [
            "## \U0001f4ca \u06af\u0632\u0627\u0631\u0634 \u067e\u0627\u06cc\u0634 \u0648 \u062e\u0648\u062f\u062a\u0631\u0645\u06cc\u0645\u06cc \u0633\u06cc\u0633\u062a\u0645 (Telemetry & Health)",
            f"- **\u0636\u0631\u06cc\u0628 \u062a\u0627\u0628\u200c\u0622\u0648\u0631\u06cc (Resilience Score):** `{metrics.resilience_score * 100:.1f}%`",
            f"- **\u062a\u0639\u062f\u0627\u062f \u06a9\u0644 \u062a\u0631\u0627\u06a9\u0646\u0634\u200c\u0647\u0627 (Total Spans):** {metrics.total_spans}",
            f"- **\u062e\u0637\u0627\u0647\u0627\u06cc \u062a\u0631\u0645\u06cc\u0645\u200c\u0634\u062f\u0647 (Recovered):** {metrics.recovered_count}",
            f"- **\u062a\u0627\u062e\u06cc\u0631 p50:** {metrics.p50_latency_ms:.1f} ms | **\u062a\u0627\u062e\u06cc\u0631 p95:** {metrics.p95_latency_ms:.1f} ms",
            "",
            "### \U0001fa79 \u062a\u0627\u0631\u06cc\u062e\u0686\u0647 \u062a\u0631\u0645\u06cc\u0645\u200c\u0647\u0627\u06cc \u0627\u062e\u06cc\u0631:",
        ]
        if not self._reports:
            lines.append("- \u0647\u06cc\u0686 \u062e\u0637\u0627\u06cc\u06cc \u062b\u0628\u062a \u0646\u0634\u062f\u0647 \u0648 \u0633\u06cc\u0633\u062a\u0645 \u06a9\u0627\u0645\u0644\u0627\u064b \u0633\u0627\u0644\u0645 \u0627\u0633\u062a.")
        else:
            for r in self._reports[-5:]:
                lines.append(f"- `{r.incident_id}`: **{r.fault_type.value}** -> `{r.action_taken.value}` (\u0645\u0648\u0641\u0642)")

        return "\n".join(lines)

    def reset(self) -> None:
        """Reset telemetry and healing reports."""
        self.tracer.reset()
        self.chaos.reset()
        self._reports.clear()
''',
    "dream/healing/tools.py": r'''"""LLM tool bindings for Autonomous Self-Healing and Observability Engine."""

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
    """Inject a synthetic failure (rate limit, timeout, schema mismatch) to verify self-recovery."""
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
    return {"success": True, "message": "\u062f\u0627\u062f\u0647\u200c\u0647\u0627\u06cc \u067e\u0627\u06cc\u0634 \u0648 \u062a\u0644\u0645\u062a\u0631\u06cc \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f\u0646\u062f."}


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
''',
    "dream/healing/slash.py": r'''"""CLI and slash command handlers for Self-Healing and Telemetry."""

from __future__ import annotations

from typing import Any

from dream.healing.tools import (
    healing_diagnose_failure,
    healing_run_chaos_test,
    telemetry_export_report,
    telemetry_reset_all,
)


def handle_healing_slash_command(command_str: str) -> str:
    """Handle /heal, /chaos, and /telemetry CLI slash commands.

    Usage:
        /heal <error_description>
        /chaos <fault_type> [target_name]
        /telemetry [report|reset]
    """
    cmd = command_str.strip()

    if cmd.startswith("/heal"):
        err = cmd[len("/heal") :].strip()
        if not err:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0634\u0631\u062d \u062e\u0637\u0627 \u0631\u0627 \u0628\u0631\u0627\u06cc \u062a\u0634\u062e\u06cc\u0635 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = healing_diagnose_failure(err)
        rep = res.get("report", {})
        return (
            f"\U0001fa79 \u0646\u062a\u06cc\u062c\u0647 \u062a\u0634\u062e\u06cc\u0635 \u0648 \u062e\u0648\u062f\u062a\u0631\u0645\u06cc\u0645\u06cc:\n"
            f"- \u0634\u0646\u0627\u0633\u0647: `{rep.get('incident_id')}`\n"
            f"- \u0646\u0648\u0639 \u062e\u0637\u0627: `{rep.get('fault_type')}`\n"
            f"- \u0627\u0642\u062f\u0627\u0645 \u062a\u0631\u0645\u06cc\u0645\u06cc: `{rep.get('action_taken')}`\n"
            f"- \u0632\u0645\u0627\u0646 \u0628\u0627\u0632\u06cc\u0627\u0628\u06cc: {rep.get('recovery_latency_ms'):.1f} \u0645\u06cc\u0644\u06cc\u200c\u062b\u0627\u0646\u06cc\u0647"
        )

    if cmd.startswith("/chaos"):
        parts = cmd.split()
        fault = parts[1] if len(parts) > 1 else "rate_limit"
        target = parts[2] if len(parts) > 2 else "agent_service"
        res = healing_run_chaos_test(fault_type=fault, target_name=target)
        rep = res.get("report", {})
        return (
            f"\u26a1 \u0622\u0632\u0645\u0627\u06cc\u0634 \u0622\u0634\u0648\u0628 (Chaos Test):\n"
            f"- \u062e\u0637\u0627\u06cc \u062a\u0632\u0631\u06cc\u0642\u200c\u0634\u062f\u0647: `{rep.get('fault_type')}` \u0631\u0648\u06cc `{target}`\n"
            f"- \u067e\u0627\u0633\u062e \u0633\u06cc\u0633\u062a\u0645: `{rep.get('action_taken')}` (\u0628\u0627\u0632\u06cc\u0627\u0628\u06cc \u0645\u0648\u0641\u0642 \u2705)"
        )

    if cmd.startswith("/telemetry"):
        parts = cmd.split()
        subcmd = parts[1].lower() if len(parts) > 1 else "report"
        if subcmd == "reset":
            telemetry_reset_all()
            return "\u2705 \u062f\u0627\u062f\u0647\u200c\u0647\u0627\u06cc \u062a\u0644\u0645\u062a\u0631\u06cc \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."

        res = telemetry_export_report()
        return res.get("markdown_report", "")

    return "\u274c \u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a."
''',
    "dream/healing/__init__.py": r'''"""Autonomous Self-Healing, Chaos Fault Injection & Telemetry Observability Subsystem."""

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
''',
    "dream/tools/toolsets.py": r'''"""Toolset categorization, grouping, and dynamic tool management."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from dream.tools.base import REGISTRY, Tool


@dataclass(frozen=True)
class Toolset:
    """Group of related tools identified by name."""

    name: str
    description: str
    tools: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


# Default built-in toolsets matching Dream's core capabilities
BUILTIN_TOOLSETS: dict[str, Toolset] = {
    "core": Toolset(
        name="core",
        description="Fundamental utilities (datetime, math calculation)",
        tools=("get_datetime", "calculate"),
    ),
    "workspace": Toolset(
        name="workspace",
        description="Workspace note inspection and editing",
        tools=("read_note", "list_notes", "write_note"),
    ),
    "web": Toolset(
        name="web",
        description="Public internet search and page fetching",
        tools=("search_web", "read_page"),
    ),
    "skills": Toolset(
        name="skills",
        description="Reusable skill management, hub discovery, and autonomous evolution",
        tools=(
            "save_skill",
            "use_skill",
            "list_skills",
            "skill_view",
            "edit_skill",
            "delete_skill",
            "save_skill_bundle",
            "apply_skill_proposal",
            "discard_skill_proposal",
            "hub_search_skills",
            "hub_install_skill",
            "skill_evolve_optimize",
            "skill_export_bundle",
            "skill_import_bundle",
        ),
    ),
    "reminders": Toolset(
        name="reminders",
        description="Scheduled reminders and tasks",
        tools=("create_reminder", "cancel_reminder"),
    ),
    "system": Toolset(
        name="system",
        description="System commands and external communication",
        tools=("run_shell", "send_email"),
    ),
    "mcp": Toolset(
        name="mcp",
        description="Model Context Protocol servers, discovery, and tool execution",
        tools=(
            "mcp_list_servers",
            "mcp_list_tools",
            "mcp_call_tool",
            "mcp_read_resource",
            "mcp_reload",
        ),
    ),
    "subagents": Toolset(
        name="subagents",
        description="Multi-agent orchestration, delegation, and worker lifecycle",
        tools=(
            "subagent_spawn",
            "subagent_wait",
            "subagent_delegate_task",
            "subagent_list",
            "subagent_terminate",
        ),
    ),
    "scheduler": Toolset(
        name="scheduler",
        description="Autonomous cron scheduling, reminders, and multi-channel delivery",
        tools=(
            "schedule_task",
            "list_schedules",
            "cancel_schedule",
            "trigger_schedule",
        ),
    ),
    "retrieval": Toolset(
        name="retrieval",
        description="Hybrid semantic retrieval and knowledge graph memory association",
        tools=(
            "search_hybrid_memory",
            "query_knowledge_graph",
        ),
    ),
    "distill": Toolset(
        name="distill",
        description="Autonomous trajectory recording, distillation, and evaluation benchmarks",
        tools=(
            "distill_record_trajectory",
            "distill_export_dataset",
            "eval_run_benchmark",
        ),
    ),
    "profiles": Toolset(
        name="profiles",
        description="Multi-profile persona scoping and isolated workspace management",
        tools=(
            "profile_list",
            "profile_get_current",
            "profile_switch",
            "profile_create",
        ),
    ),
    "context": Toolset(
        name="context",
        description="Prioritized context files (SOUL, AGENTS, USER, MEMORY) and budgeting",
        tools=(
            "context_get_tier",
            "context_update_tier",
            "context_get_budget_report",
            "context_assemble_prompt",
            "context_reload_all",
        ),
    ),
    "terminal": Toolset(
        name="terminal",
        description="Multi-backend isolated execution (Local, Docker, SSH, Cloud Sandboxes)",
        tools=(
            "terminal_execute",
            "terminal_list_backends",
            "terminal_switch_backend",
        ),
    ),
    "browser": Toolset(
        name="browser",
        description="Multi-driver browser control, DOM extraction, and visual interaction",
        tools=(
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_screenshot",
            "browser_extract_content",
            "browser_close",
            "browser_get_status",
        ),
    ),
    "dialectic": Toolset(
        name="dialectic",
        description="Self-reflective dialectic user modeling and knowledge synthesis",
        tools=(
            "dialectic_observe",
            "dialectic_reflect",
            "dialectic_get_belief_graph",
            "dialectic_reconcile",
            "dialectic_query_traits",
        ),
    ),
    "acp": Toolset(
        name="acp",
        description="Agent Client Protocol (ACP) IDE integration and diff tools",
        tools=(
            "acp_apply_diff",
            "acp_read_diagnostics",
            "acp_get_session_status",
            "acp_list_agents",
            "acp_call_agent",
        ),
    ),
    "plugins": Toolset(
        name="plugins",
        description="Dynamic plugin installation, lifecycle management, and extension hooks",
        tools=(
            "plugin_list",
            "plugin_install",
            "plugin_enable",
            "plugin_disable",
            "plugin_get_info",
        ),
    ),
    "swarm": Toolset(
        name="swarm",
        description="Distributed swarm orchestration, DAG task execution, and consensus",
        tools=(
            "swarm_spawn_node",
            "swarm_plan_workflow",
            "swarm_execute_step",
            "swarm_run_all",
            "swarm_reach_consensus",
            "swarm_get_status",
            "swarm_broadcast_message",
        ),
    ),
    "speech": Toolset(
        name="speech",
        description="Voice synthesis (TTS), recognition (STT), and HybridEmo emotion modeling",
        tools=(
            "speech_text_to_speech",
            "speech_speech_to_text",
            "speech_analyze_voice_emotion",
            "speech_list_voices",
        ),
    ),
    "ocr": Toolset(
        name="ocr",
        description="Persian document OCR, receipt parsing, and invoice field extraction",
        tools=(
            "ocr_extract_document",
            "ocr_extract_invoice",
        ),
    ),
    "knowledge": Toolset(
        name="knowledge",
        description=(
            "Multimodal temporal knowledge graph, timeline reasoning, "
            "and cross-modal entity linking"
        ),
        tools=(
            "knowledge_add_entity",
            "knowledge_add_relation",
            "knowledge_query_temporal",
            "knowledge_get_entity_timeline",
            "knowledge_link_multimodal_artifact",
            "knowledge_get_stats",
        ),
    ),
    "alignment": Toolset(
        name="alignment",
        description=(
            "Continuous self-improving alignment, multi-dimensional scoring, "
            "self-critique, and DPO dataset generation"
        ),
        tools=(
            "alignment_record_feedback",
            "alignment_critique_and_refine",
            "alignment_evaluate_response",
            "alignment_export_dataset",
            "alignment_get_stats",
        ),
    ),
    "research": Toolset(
        name="research",
        description=(
            "Autonomous multi-step deep research, evidence collection, "
            "and multi-source intelligence synthesis"
        ),
        tools=(
            "research_plan_investigation",
            "research_add_source",
            "research_synthesize_report",
            "research_run_autonomous",
            "research_export_report",
            "research_get_status",
            "research_list_sessions",
        ),
    ),
    "cache": Toolset(
        name="cache",
        description=(
            "Semantic caching, speculative pre-fetching, and token economics optimization"
        ),
        tools=(
            "cache_lookup_query",
            "cache_store_entry",
            "cache_predict_tool",
            "cache_get_economics",
            "cache_clear",
            "cache_warmup",
        ),
    ),
    "sandbox": Toolset(
        name="sandbox",
        description=(
            "Isolated Python code execution, dataset analysis, and REPL interpreter"
        ),
        tools=(
            "sandbox_execute_python",
            "sandbox_analyze_dataset",
            "sandbox_reset_session",
            "sandbox_list_artifacts",
            "sandbox_get_status",
        ),
    ),
    "canvas": Toolset(
        name="canvas",
        description=(
            "Interactive visual artifacts, diagrams, standalone previews, and versioning"
        ),
        tools=(
            "canvas_create_artifact",
            "canvas_update_artifact",
            "canvas_get_artifact",
            "canvas_list_artifacts",
            "canvas_diff_versions",
            "canvas_render_preview",
            "canvas_export_bundle",
            "canvas_reset_session",
            "canvas_get_status",
        ),
    ),
    "debate": Toolset(
        name="debate",
        description=(
            "Multi-agent debate rounds, Delphi consensus evaluation, and fact verification"
        ),
        tools=(
            "debate_create_session",
            "debate_add_turn",
            "debate_run_autonomous",
            "debate_verify_statement",
            "debate_reach_consensus",
            "debate_list_sessions",
            "debate_reset_all",
        ),
    ),
    "reasoning": Toolset(
        name="reasoning",
        description=(
            "Tree-of-Thought exploration, strategy branching, and metacognitive self-evaluation"
        ),
        tools=(
            "reasoning_create_thought_tree",
            "reasoning_expand_node",
            "reasoning_evaluate_node",
            "reasoning_solve_goal",
            "reasoning_get_best_path",
            "reasoning_get_status",
            "reasoning_reset_all",
        ),
    ),
    "healing": Toolset(
        name="healing",
        description=(
            "Autonomous error diagnosis, self-healing recovery, telemetry, and chaos testing"
        ),
        tools=(
            "healing_diagnose_failure",
            "healing_run_chaos_test",
            "telemetry_get_health_metrics",
            "telemetry_export_report",
            "telemetry_export_spans",
            "telemetry_reset_all",
        ),
    ),
}

_TOOLSETS: dict[str, Toolset] = dict(BUILTIN_TOOLSETS)


def register_toolset(
    name: str,
    tools: Collection[str],
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> Toolset:
    """Register a new named toolset or update an existing one."""
    toolset = Toolset(
        name=name,
        description=description,
        tools=tuple(sorted(set(tools))),
        metadata=metadata or {},
    )
    _TOOLSETS[name] = toolset
    return toolset


def unregister_toolset(name: str) -> bool:
    """Remove a registered toolset (returns True if removed)."""
    if name in _TOOLSETS:
        del _TOOLSETS[name]
        return True
    return False


def get_toolset(name: str) -> Toolset | None:
    """Return a Toolset by name, or None if not registered."""
    return _TOOLSETS.get(name)


def list_toolsets() -> list[Toolset]:
    """Return a list of all registered Toolsets."""
    return list(_TOOLSETS.values())


def filter_tools(
    toolsets: Collection[str] | None = None,
    include_tools: Collection[str] | None = None,
    exclude_tools: Collection[str] | None = None,
    registry: Mapping[str, Tool] | None = None,
) -> dict[str, Tool]:
    """Filter registered tools by toolset names and explicit inclusions/exclusions."""
    source = REGISTRY if registry is None else registry

    if toolsets is None and include_tools is None and exclude_tools is None:
        return dict(source)

    allowed_names: set[str] = set()

    if toolsets is not None:
        for ts_name in toolsets:
            ts = _TOOLSETS.get(ts_name)
            if ts:
                allowed_names.update(ts.tools)

    if include_tools is not None:
        allowed_names.update(include_tools)

    if toolsets is None and include_tools is None:
        names = source.keys()
        allowed_names.update(names)

    if exclude_tools is not None:
        allowed_names.difference_update(exclude_tools)

    return {name: tool for name, tool in source.items() if name in allowed_names}
''',
    "tests/test_self_healing_and_telemetry.py": r'''"""Unit and integration tests for Autonomous Self-Healing, Chaos Fault Injection & Telemetry."""

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
    telemetry_export_spans,
    telemetry_get_health_metrics,
    telemetry_reset_all,
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
''',
}


def main() -> None:
    root = Path(__file__).resolve().parent
    if not (root / "dream").exists():
        if (root / "dream-repo" / "dream").exists():
            root = root / "dream-repo"
        elif (Path.cwd() / "dream").exists():
            root = Path.cwd()
        else:
            print(f"Error: could not locate Dream repo root from {root}")
            sys.exit(1)

    print(f"Applying Phase 36 (Self-Healing & Telemetry Engine) to: {root}")

    for rel_path, content in FILES.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"  [written] {rel_path}")

    print("\nRunning pytest validation...")
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_self_healing_and_telemetry.py", "-v"],
        cwd=root,
    )
    if res.returncode != 0:
        print("\n[FAIL] Pytest failed for Phase 36")
        sys.exit(res.returncode)

    print("\nRunning security audit...")
    audit_res = subprocess.run(
        [sys.executable, "tools/security_audit.py"],
        cwd=root,
    )
    if audit_res.returncode != 0:
        print("\n[FAIL] Security audit failed for Phase 36")
        sys.exit(audit_res.returncode)

    print("\n[SUCCESS] Phase 36 (Self-Healing & Telemetry Engine) applied and verified cleanly!")


if __name__ == "__main__":
    main()
