"""Autonomous Event-Driven Reactive Engine & Webhook Subsystem for Dream."""

from __future__ import annotations

from dream.reactive.bus import EventBus
from dream.reactive.engine import ReactiveEngine, get_reactive_engine
from dream.reactive.slash import handle_reactive_command
from dream.reactive.tools import (
    get_global_reactive_engine,
    get_reactive_tools,
    reactive_get_event_history,
    reactive_get_metrics,
    reactive_ingest_event,
    reactive_list_rules,
    reactive_register_rule,
    reactive_reset,
    reactive_verify_webhook,
    reset_global_reactive_engine,
)
from dream.reactive.types import (
    EventPayload,
    EventPriority,
    EventSource,
    EventStatus,
    ReactionAction,
    ReactiveMetrics,
    ReactiveRule,
)
from dream.reactive.webhook import WebhookVerifier

__all__ = [
    "EventBus",
    "EventPayload",
    "EventPriority",
    "EventSource",
    "EventStatus",
    "ReactionAction",
    "ReactiveEngine",
    "ReactiveMetrics",
    "ReactiveRule",
    "WebhookVerifier",
    "get_global_reactive_engine",
    "get_reactive_engine",
    "get_reactive_tools",
    "handle_reactive_command",
    "reactive_get_event_history",
    "reactive_get_metrics",
    "reactive_ingest_event",
    "reactive_list_rules",
    "reactive_register_rule",
    "reactive_reset",
    "reactive_verify_webhook",
    "reset_global_reactive_engine",
]
