"""Domain models and data structures for Autonomous Self-Healing and Telemetry Engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
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
