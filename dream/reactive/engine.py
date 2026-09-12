"""Master Reactive Engine orchestrating events, webhook ingestion, and autonomous rules."""

from __future__ import annotations

import fnmatch
import json
import time
from typing import Any

from dream.reactive.bus import EventBus
from dream.reactive.types import (
    EventPayload,
    EventPriority,
    EventSource,
    ReactionAction,
    ReactiveMetrics,
    ReactiveRule,
)
from dream.reactive.webhook import WebhookVerifier


class ReactiveEngine:
    """Central engine managing the pub-sub bus, webhook security, and reactive triggers."""

    def __init__(self) -> None:
        self.bus = EventBus()
        self.verifier = WebhookVerifier()
        self._rules: dict[str, ReactiveRule] = {}
        self.metrics = ReactiveMetrics()
        self._init_event_listener()
        self._init_default_rules()

    def _init_event_listener(self) -> None:
        """Subscribe internal dispatcher to all incoming events."""
        self.bus.subscribe("*", self._on_event_received)

    def _init_default_rules(self) -> None:
        """Seed standard out-of-the-box reactive rules."""
        rule_gh = ReactiveRule(
            rule_id="rule_gh_pr_review",
            name_fa="بررسی خودکار پول ریکوئست جدید گیت‌هاب",
            event_types=("github:pull_request.opened", "github:pull_request.reopened"),
            condition_key="action",
            condition_val="opened",
            actions=(
                ReactionAction(
                    action_type="workflow_start",
                    target="code_review_workflow",
                    payload={"auto_review": True},
                ),
            ),
        )
        self._rules[rule_gh.rule_id] = rule_gh

    def register_rule(
        self,
        rule_id: str,
        name_fa: str,
        event_types: list[str] | tuple[str, ...],
        condition_key: str = "",
        condition_val: Any = None,
        actions: list[dict[str, Any]] | tuple[ReactionAction, ...] | None = None,
        cooldown_sec: float = 0.0,
    ) -> ReactiveRule:
        """Register a new autonomous reaction rule."""
        parsed_actions: list[ReactionAction] = []
        if actions:
            for a in actions:
                if isinstance(a, ReactionAction):
                    parsed_actions.append(a)
                elif isinstance(a, dict):
                    parsed_actions.append(
                        ReactionAction(
                            action_type=a.get("action_type", "log"),
                            target=a.get("target", "default"),
                            payload=a.get("payload", {}),
                        )
                    )

        rule = ReactiveRule(
            rule_id=rule_id,
            name_fa=name_fa,
            event_types=tuple(event_types),
            condition_key=condition_key,
            condition_val=condition_val,
            actions=tuple(parsed_actions),
            cooldown_sec=cooldown_sec,
        )
        self._rules[rule_id] = rule
        return rule

    def get_rule(self, rule_id: str) -> ReactiveRule | None:
        """Retrieve rule by ID."""
        return self._rules.get(rule_id)

    def list_rules(self) -> list[dict[str, Any]]:
        """Return list of all registered reactive rules."""
        return [r.to_dict() for r in self._rules.values()]

    def ingest_event(
        self,
        source: EventSource | str,
        event_type: str,
        data: dict[str, Any] | None = None,
        priority: EventPriority = EventPriority.NORMAL,
        idempotency_key: str = "",
    ) -> tuple[bool, EventPayload]:
        """Ingest an external or internal event into the system."""
        self.metrics.total_events_ingested += 1
        if isinstance(source, str):
            try:
                src_enum = EventSource(source)
            except ValueError:
                src_enum = EventSource.USER_MESSAGE
        else:
            src_enum = source

        payload = EventPayload(
            event_id=idempotency_key or f"evt-{int(time.time()*1000)}",
            source=src_enum,
            event_type=event_type,
            data=data or {},
            priority=priority,
            idempotency_key=idempotency_key,
        )

        ok = self.bus.publish(payload)
        if ok:
            self.metrics.total_events_processed += 1
        else:
            self.metrics.total_events_dropped += 1

        return ok, payload

    def ingest_webhook(
        self,
        source_type: str,
        payload_bytes: bytes,
        signature_header: str,
        secret: str,
        event_name: str = "generic",
    ) -> tuple[bool, str, EventPayload | None]:
        """Verify HMAC signature and ingest webhook payload safely."""
        self.metrics.total_webhook_verifications += 1

        if secret:
            is_valid = self.verifier.verify_hmac_sha256(payload_bytes, signature_header, secret)
            if not is_valid:
                self.metrics.failed_webhook_verifications += 1
                return False, "امضای وب‌هوک نامعتبر است (HMAC verification failed).", None

        try:
            payload_dict = json.loads(payload_bytes.decode("utf-8"))
        except Exception as e:
            return False, f"خطا در پارس بدنه وب‌هوک به JSON: {e}", None

        if source_type.lower() == "github":
            event = self.verifier.normalize_github_webhook(event_name, payload_dict)
        else:
            event = self.verifier.normalize_custom_webhook(event_name, payload_dict)

        ok = self.bus.publish(event)
        if ok:
            self.metrics.total_events_processed += 1
            return True, f"وب‌هوک با موفقیت اعتبارسنجی و رویداد `{event.event_type}` ثبت شد.", event
        else:
            self.metrics.total_events_dropped += 1
            return False, "رویداد به دلیل تکراری بودن کلید Idempotency نادیده گرفته شد.", event

    def _on_event_received(self, event: EventPayload) -> None:
        """Internal callback triggered whenever any event is published on the bus."""
        now = time.time()
        for rule in self._rules.values():
            if not rule.enabled:
                continue

            # Check event type matching (supports wildcards)
            matches_type = any(
                pattern == "*" or fnmatch.fnmatch(event.event_type, pattern)
                for pattern in rule.event_types
            )
            if not matches_type:
                continue

            # Check condition key/value
            if rule.condition_key:
                val = event.data.get(rule.condition_key)
                if rule.condition_val is not None and val != rule.condition_val:
                    continue

            # Check cooldown
            if rule.cooldown_sec > 0 and (now - rule.last_triggered_at) < rule.cooldown_sec:
                continue

            # Execute rule trigger
            rule.last_triggered_at = now
            rule.trigger_count += 1
            self.metrics.total_rules_triggered += 1

    def export_markdown_report(self) -> str:
        """Format reactive engine telemetry and active rules into Markdown."""
        lines = [
            "# ⚡ گزارش موتور واکنشی و رویدادمحور (Reactive Engine Status)",
            f"- **تعداد کل رویدادهای دریافتی**: `{self.metrics.total_events_ingested}`",
            f"- **رویدادهای پردازش‌شده**: `{self.metrics.total_events_processed}`",
            f"- **رویدادهای تکراری حذف‌شده**: `{self.metrics.total_events_dropped}`",
            f"- **تعداد فعال‌سازی قوانین**: `{self.metrics.total_rules_triggered}`",
            f"- **اعتبارسنجی‌های وب‌هوک**: `{self.metrics.total_webhook_verifications}`",
            "",
            "## 📋 فهرست قوانین واکنشی فعال:",
            "",
        ]

        if not self._rules:
            lines.append("_هیچ قانونی تعریف نشده است._")
        else:
            for rule in self._rules.values():
                status_icon = "🟢 فعال" if rule.enabled else "⚪ غیرفعال"
                types_str = ", ".join(f"`{t}`" for t in rule.event_types)
                lines.append(f"### • {rule.name_fa} (`{rule.rule_id}`) - {status_icon}")
                lines.append(f"- **الگوهای رویداد**: {types_str}")
                lines.append(f"- **تعداد فراخوانی‌ها**: `{rule.trigger_count}`")
                if rule.condition_key:
                    lines.append(f"- **شرط**: `{rule.condition_key} == {rule.condition_val}`")
                lines.append("")

        return "\n".join(lines)

    def reset(self) -> None:
        """Reset bus, history, metrics, and rules to default seed state."""
        self.bus.clear()
        self._rules.clear()
        self.metrics = ReactiveMetrics()
        self._init_default_rules()


# Global Singleton
_GLOBAL_REACTIVE_ENGINE: ReactiveEngine | None = None


def get_reactive_engine() -> ReactiveEngine:
    """Retrieve global singleton instance of ReactiveEngine."""
    global _GLOBAL_REACTIVE_ENGINE
    if _GLOBAL_REACTIVE_ENGINE is None:
        _GLOBAL_REACTIVE_ENGINE = ReactiveEngine()
    return _GLOBAL_REACTIVE_ENGINE
