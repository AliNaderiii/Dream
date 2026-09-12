"""LLM agent tools and singleton managers for Event-Driven Reactive Engine."""

from __future__ import annotations

import logging
from typing import Any

from dream.reactive.engine import ReactiveEngine, get_reactive_engine
from dream.reactive.types import EventPriority, EventSource, ReactionAction

logger = logging.getLogger(__name__)

_GLOBAL_REACTIVE_ENGINE: ReactiveEngine | None = None


def get_global_reactive_engine() -> ReactiveEngine:
    """Retrieve or initialize singleton ReactiveEngine."""
    global _GLOBAL_REACTIVE_ENGINE
    if _GLOBAL_REACTIVE_ENGINE is None:
        _GLOBAL_REACTIVE_ENGINE = get_reactive_engine()
    return _GLOBAL_REACTIVE_ENGINE


def reset_global_reactive_engine() -> None:
    """Reset global ReactiveEngine instance for test isolation."""
    global _GLOBAL_REACTIVE_ENGINE
    if _GLOBAL_REACTIVE_ENGINE is not None:
        _GLOBAL_REACTIVE_ENGINE.reset()
    _GLOBAL_REACTIVE_ENGINE = None


def reactive_register_rule(
    rule_id: str,
    name_fa: str,
    event_types: list[str],
    condition_key: str = "",
    condition_val: Any = None,
    action_type: str = "workflow_start",
    target: str = "default_handler",
    cooldown_sec: float = 0.0,
) -> dict[str, Any]:
    """Register an autonomous reactive trigger rule.

    Args:
        rule_id: Unique rule identifier.
        name_fa: Persian description of what this rule does.
        event_types: List of event type patterns (e.g. ['github:pull_request.*']).
        condition_key: Optional JSON payload key to inspect.
        condition_val: Optional expected value for the condition key.
        action_type: Type of action ('workflow_start', 'tool_call', 'alert').
        target: Target identifier or tool name.
        cooldown_sec: Minimum seconds between consecutive triggers.
    """
    engine = get_global_reactive_engine()
    action = ReactionAction(action_type=action_type, target=target)
    rule = engine.register_rule(
        rule_id=rule_id,
        name_fa=name_fa,
        event_types=event_types,
        condition_key=condition_key,
        condition_val=condition_val,
        actions=(action,),
        cooldown_sec=cooldown_sec,
    )
    return {
        "success": True,
        "rule": rule.to_dict(),
        "summary_fa": f"قانون واکنشی `{name_fa}` با شناسه `{rule_id}` با موفقیت ثبت شد.",
    }


def reactive_ingest_event(
    source: str = "webhook:custom",
    event_type: str = "custom.alert",
    data: dict[str, Any] | None = None,
    priority: str = "normal",
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Manually ingest an event into the reactive event bus.

    Args:
        source: Source identifier (e.g. 'webhook:github', 'db:trigger').
        event_type: Event type string.
        data: Optional payload dictionary.
        priority: Priority ('critical', 'high', 'normal', 'low').
        idempotency_key: Unique key to prevent duplicate executions.
    """
    engine = get_global_reactive_engine()
    try:
        src_enum = EventSource(source)
    except ValueError:
        src_enum = EventSource.WEBHOOK_CUSTOM

    try:
        prio_enum = EventPriority(priority.lower())
    except ValueError:
        prio_enum = EventPriority.NORMAL

    ok, payload = engine.ingest_event(
        source=src_enum,
        event_type=event_type,
        data=data or {},
        priority=prio_enum,
        idempotency_key=idempotency_key,
    )
    return {
        "success": ok,
        "event_id": payload.event_id,
        "status": payload.status.value,
        "event_type": event_type,
    }


def reactive_verify_webhook(
    source_type: str,
    payload_str: str,
    signature_header: str,
    secret: str,
    event_name: str = "generic",
) -> dict[str, Any]:
    """Verify HMAC signature of an incoming webhook payload and ingest it.

    Args:
        source_type: Webhook provider ('github', 'stripe', 'custom').
        payload_str: Raw body string of the HTTP request.
        signature_header: Signature header value (e.g. 'sha256=...').
        secret: Webhook secret key.
        event_name: Name of the event.
    """
    engine = get_global_reactive_engine()
    payload_bytes = payload_str.encode("utf-8")
    ok, message, event = engine.ingest_webhook(
        source_type=source_type,
        payload_bytes=payload_bytes,
        signature_header=signature_header,
        secret=secret,
        event_name=event_name,
    )
    return {
        "success": ok,
        "message": message,
        "event": event.to_dict() if event else None,
    }


def reactive_list_rules() -> dict[str, Any]:
    """Return all registered reactive trigger rules."""
    engine = get_global_reactive_engine()
    return {"success": True, "rules": engine.list_rules()}


def reactive_get_event_history(limit: int = 20) -> dict[str, Any]:
    """Return recent events processed by the event bus.

    Args:
        limit: Max number of history records to return.
    """
    engine = get_global_reactive_engine()
    events = engine.bus.get_history(limit=limit)
    return {
        "success": True,
        "total": len(events),
        "events": [e.to_dict() for e in events],
    }


def reactive_get_metrics() -> dict[str, Any]:
    """Return diagnostic telemetry and report from the reactive engine."""
    engine = get_global_reactive_engine()
    return {
        "success": True,
        "metrics": engine.metrics.to_dict(),
        "report_markdown": engine.export_markdown_report(),
    }


def reactive_reset() -> dict[str, Any]:
    """Reset reactive bus, metrics, and rule pool."""
    reset_global_reactive_engine()
    return {"success": True, "message_fa": "موتور رویدادمحور با موفقیت بازنشانی شد."}


def get_reactive_tools() -> list[dict[str, Any]]:
    """Return tool manifests for LLM registration."""
    return [
        {
            "name": "reactive_register_rule",
            "description": "Register an autonomous event-driven reactive trigger rule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "rule_id": {"type": "string"},
                    "name_fa": {"type": "string"},
                    "event_types": {"type": "array", "items": {"type": "string"}},
                    "condition_key": {"type": "string", "default": ""},
                    "action_type": {"type": "string", "default": "workflow_start"},
                    "target": {"type": "string", "default": "default_handler"},
                },
                "required": ["rule_id", "name_fa", "event_types"],
            },
            "handler": reactive_register_rule,
        },
        {
            "name": "reactive_ingest_event",
            "description": "Publish and ingest an asynchronous event into the event bus.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "default": "webhook:custom"},
                    "event_type": {"type": "string"},
                    "data": {"type": "object"},
                    "priority": {"type": "string", "enum": ["critical", "high", "normal", "low"]},
                    "idempotency_key": {"type": "string"},
                },
                "required": ["event_type"],
            },
            "handler": reactive_ingest_event,
        },
        {
            "name": "reactive_verify_webhook",
            "description": "Verify HMAC-SHA256 signature of incoming webhook and ingest payload.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_type": {"type": "string", "default": "github"},
                    "payload_str": {"type": "string"},
                    "signature_header": {"type": "string"},
                    "secret": {"type": "string"},
                    "event_name": {"type": "string", "default": "generic"},
                },
                "required": ["payload_str", "signature_header", "secret"],
            },
            "handler": reactive_verify_webhook,
        },
        {
            "name": "reactive_list_rules",
            "description": "List all active event-driven reactive rules.",
            "parameters": {"type": "object", "properties": {}},
            "handler": reactive_list_rules,
        },
        {
            "name": "reactive_get_metrics",
            "description": "Retrieve event bus telemetry and Markdown status report.",
            "parameters": {"type": "object", "properties": {}},
            "handler": reactive_get_metrics,
        },
    ]
