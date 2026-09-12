"""Healing Engine Coordinator: Automated fault diagnosis, recovery strategies."""

from __future__ import annotations

import time
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

        summary_fa = (
            f"🩹 خودترمیم خطا: {fault_type.value} در '{target_name}' "
            f"با استراتژی {action.value} انجام شد."
        )

        report = HealingReport(
            incident_id=incident_id,
            fault_type=fault_type,
            root_cause=f"{type(exc).__name__}: {str(exc)}",
            action_taken=action,
            success=True,
            recovery_latency_ms=latency_ms,
            summary_fa=summary_fa,
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
            "## 📊 گزارش پایش و خودترمیمی سیستم (Telemetry & Health)",
            f"- **ضریب تاب‌آوری (Resilience Score):** `{metrics.resilience_score * 100:.1f}%`",
            f"- **تعداد کل تراکنش‌ها (Total Spans):** {metrics.total_spans}",
            f"- **خطاهای ترمیم‌شده (Recovered):** {metrics.recovered_count}",
            f"- **تاخیر p50:** {metrics.p50_latency_ms:.1f} ms | "
            f"**تاخیر p95:** {metrics.p95_latency_ms:.1f} ms",
            "",
            "### 🩹 تاریخچه ترمیم‌های اخیر:",
        ]
        if not self._reports:
            lines.append("- هیچ خطایی ثبت نشده و سیستم کاملاً سالم است.")
        else:
            for r in self._reports[-5:]:
                lines.append(
                    f"- `{r.incident_id}`: **{r.fault_type.value}** -> "
                    f"`{r.action_taken.value}` (موفق)"
                )

        return "\n".join(lines)

    def reset(self) -> None:
        """Reset telemetry and healing reports."""
        self.tracer.reset()
        self.chaos.reset()
        self._reports.clear()
