"""Comprehensive tests for Autonomous Event-Driven Reactive Engine Subsystem."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from dream.reactive.bus import EventBus
from dream.reactive.engine import ReactiveEngine
from dream.reactive.slash import handle_reactive_command
from dream.reactive.tools import (
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
)
from dream.reactive.webhook import WebhookVerifier
from dream.tools.toolsets import get_toolset


@pytest.fixture(autouse=True)
def cleanup_reactive() -> None:
    reset_global_reactive_engine()
    yield
    reset_global_reactive_engine()


def test_toolset_includes_reactive() -> None:
    """Verify reactive toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("reactive")
    assert ts is not None
    assert ts.name == "reactive"
    assert "reactive_register_rule" in ts.tools
    assert "reactive_ingest_event" in ts.tools
    assert "reactive_verify_webhook" in ts.tools


def test_webhook_hmac_verification() -> None:
    """Test HMAC-SHA256 signature verification and normalization."""
    secret = "super_secret_token_123"
    payload = b'{"action":"opened","pull_request":{"id":123}}'

    # Compute valid signature
    valid_sig = "sha256=" + hmac.new(
        key=secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Valid check
    assert WebhookVerifier.verify_hmac_sha256(payload, valid_sig, secret)

    # Invalid signature
    assert not WebhookVerifier.verify_hmac_sha256(payload, "sha256=wrong_sig", secret)
    assert not WebhookVerifier.verify_hmac_sha256(payload, "", secret)

    # GitHub normalization
    gh_dict = json.loads(payload.decode("utf-8"))
    evt = WebhookVerifier.normalize_github_webhook("pull_request", gh_dict)
    assert evt.event_type == "github:pull_request.opened"
    assert evt.source == EventSource.WEBHOOK_GITHUB
    assert evt.priority == EventPriority.HIGH


def test_event_bus_pub_sub_and_idempotency() -> None:
    """Test EventBus pub-sub routing, duplicate dropping, and history."""
    bus = EventBus(history_capacity=50, idempotency_ttl_sec=10.0)
    received_events: list[EventPayload] = []

    bus.subscribe("github:*", lambda e: received_events.append(e))

    # 1. Publish first event
    evt1 = EventPayload(
        event_id="e1",
        source=EventSource.WEBHOOK_GITHUB,
        event_type="github:push",
        idempotency_key="idemp_1",
    )
    ok1 = bus.publish(evt1)
    assert ok1 is True
    assert len(received_events) == 1
    assert evt1.status == EventStatus.PROCESSED

    # 2. Publish duplicate with same idempotency key
    evt2 = EventPayload(
        event_id="e2",
        source=EventSource.WEBHOOK_GITHUB,
        event_type="github:push",
        idempotency_key="idemp_1",
    )
    ok2 = bus.publish(evt2)
    assert ok2 is False
    assert len(received_events) == 1
    assert evt2.status == EventStatus.DROPPED


def test_reactive_engine_rule_triggering() -> None:
    """Test rule evaluation, condition matching, and cooldown throttling."""
    engine = ReactiveEngine()

    # Register rule for database errors
    engine.register_rule(
        rule_id="rule_db_alert",
        name_fa="هشدار خطای پایگاه‌داده",
        event_types=("db:error", "db:timeout"),
        condition_key="severity",
        condition_val="critical",
        actions=(
            ReactionAction(
                action_type="alert",
                target="ops_channel",
                payload={"notify": True},
            ),
        ),
        cooldown_sec=2.0,
    )

    # 1. Ingest non-matching event (severity = low)
    engine.ingest_event(
        source=EventSource.DATABASE_TRIGGER,
        event_type="db:error",
        data={"severity": "low"},
    )
    rule = engine.get_rule("rule_db_alert")
    assert rule is not None
    assert rule.trigger_count == 0

    # 2. Ingest matching event (severity = critical)
    engine.ingest_event(
        source=EventSource.DATABASE_TRIGGER,
        event_type="db:error",
        data={"severity": "critical"},
    )
    assert rule.trigger_count == 1

    # 3. Ingest matching event immediately during cooldown (should not increment)
    engine.ingest_event(
        source=EventSource.DATABASE_TRIGGER,
        event_type="db:timeout",
        data={"severity": "critical"},
    )
    assert rule.trigger_count == 1


def test_reactive_tools_and_slash_commands() -> None:
    """Test Reactive LLM agent tools and slash command dispatcher."""
    tools = get_reactive_tools()
    assert len(tools) >= 5

    # 1. Tool: register rule
    res_r = reactive_register_rule(
        rule_id="r_custom",
        name_fa="قانون تست",
        event_types=["custom.event.*"],
        action_type="log",
    )
    assert res_r["success"] is True

    # 2. Tool: ingest event
    res_ingest = reactive_ingest_event(
        source="webhook:custom",
        event_type="custom.event.deploy",
        data={"env": "prod"},
    )
    assert res_ingest["success"] is True

    # 3. Tool: verify webhook
    secret = "sec_abc"
    body = '{"event":"user_signup"}'
    sig = "sha256=" + hmac.new(
        key=secret.encode("utf-8"),
        msg=body.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    res_wh = reactive_verify_webhook(
        source_type="custom",
        payload_str=body,
        signature_header=sig,
        secret=secret,
        event_name="signup",
    )
    assert res_wh["success"] is True

    # 4. Tool: list rules
    res_list = reactive_list_rules()
    assert res_list["success"] is True
    assert len(res_list["rules"]) >= 1

    # 5. Tool: history
    res_hist = reactive_get_event_history(limit=5)
    assert res_hist["success"] is True

    # 6. Tool: metrics
    res_m = reactive_get_metrics()
    assert res_m["success"] is True
    assert "گزارش موتور واکنشی" in res_m["report_markdown"]

    # 7. Slash commands
    s_help = handle_reactive_command("")
    assert "راهنمای دستورات موتور واکنشی" in s_help

    # Slash: list
    s_l = handle_reactive_command("rule list")
    assert "قوانین واکنشی" in s_l

    # Slash: ingest
    s_i = handle_reactive_command('ingest github:push {"ref":"refs/heads/main"}')
    assert "ثبت شد" in s_i

    # Slash: history
    s_h = handle_reactive_command("history")
    assert "تاریخچه" in s_h

    # Slash: metrics
    s_met = handle_reactive_command("metrics")
    assert "گزارش موتور واکنشی" in s_met

    # Slash: reset
    s_res = handle_reactive_command("reset")
    assert "ریست شدند" in s_res

    # Tool reset
    t_res = reactive_reset()
    assert t_res["success"] is True
