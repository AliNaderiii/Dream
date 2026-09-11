"""Distributed OpenTelemetry-compatible tracing, span lifecycle, and metrics aggregation."""

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
