"""Data models and type definitions for Autonomous Event-Driven Reactive Engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventPriority(str, Enum):
    """Priority level for incoming asynchronous events."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class EventSource(str, Enum):
    """Source origin of the event."""

    WEBHOOK_GITHUB = "webhook:github"
    WEBHOOK_STRIPE = "webhook:stripe"
    WEBHOOK_CUSTOM = "webhook:custom"
    DATABASE_TRIGGER = "db:trigger"
    FILE_WATCHER = "file:watcher"
    SYSTEM_METRIC = "system:metric"
    CRON_TICK = "cron:tick"
    USER_MESSAGE = "user:message"


class EventStatus(str, Enum):
    """Processing status of an event."""

    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    DROPPED = "dropped"


@dataclass
class EventPayload:
    """Standardized event packet entering the Reactive EventBus."""

    event_id: str
    source: EventSource
    event_type: str
    data: dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL
    idempotency_key: str = ""
    timestamp: float = field(default_factory=time.time)
    status: EventStatus = EventStatus.PENDING
    retry_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to dictionary."""
        return {
            "event_id": self.event_id,
            "source": self.source.value,
            "event_type": self.event_type,
            "data": self.data,
            "priority": self.priority.value,
            "idempotency_key": self.idempotency_key,
            "timestamp": self.timestamp,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "metadata": self.metadata,
        }


@dataclass
class ReactionAction:
    """Executable action triggered in response to a matched event."""

    action_type: str  # e.g. "tool_call", "workflow_start", "alert", "log"
    target: str  # e.g. tool name or workflow id
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize action to dictionary."""
        return {
            "action_type": self.action_type,
            "target": self.target,
            "payload": self.payload,
        }


@dataclass
class ReactiveRule:
    """Autonomous reaction rule matching event patterns and triggering actions."""

    rule_id: str
    name_fa: str
    event_types: tuple[str, ...]
    condition_key: str = ""
    condition_val: Any = None
    actions: tuple[ReactionAction, ...] = field(default_factory=tuple)
    enabled: bool = True
    cooldown_sec: float = 0.0
    last_triggered_at: float = 0.0
    trigger_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize rule to dictionary."""
        return {
            "rule_id": self.rule_id,
            "name_fa": self.name_fa,
            "event_types": list(self.event_types),
            "condition_key": self.condition_key,
            "condition_val": self.condition_val,
            "actions": [a.to_dict() for a in self.actions],
            "enabled": self.enabled,
            "cooldown_sec": self.cooldown_sec,
            "last_triggered_at": self.last_triggered_at,
            "trigger_count": self.trigger_count,
        }


@dataclass
class ReactiveMetrics:
    """Telemetry counters for the event bus and webhook ingestion."""

    total_events_ingested: int = 0
    total_events_processed: int = 0
    total_events_dropped: int = 0
    total_rules_triggered: int = 0
    total_webhook_verifications: int = 0
    failed_webhook_verifications: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize metrics to dictionary."""
        return {
            "total_events_ingested": self.total_events_ingested,
            "total_events_processed": self.total_events_processed,
            "total_events_dropped": self.total_events_dropped,
            "total_rules_triggered": self.total_rules_triggered,
            "total_webhook_verifications": self.total_webhook_verifications,
            "failed_webhook_verifications": self.failed_webhook_verifications,
        }
