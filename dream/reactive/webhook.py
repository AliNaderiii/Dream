"""HMAC verification and normalization for incoming webhook payloads."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Any

from dream.reactive.types import EventPayload, EventPriority, EventSource


class WebhookVerifier:
    """Security verifier and normalizer for incoming HTTP webhooks."""

    @staticmethod
    def verify_hmac_sha256(
        payload_bytes: bytes,
        signature_header: str,
        secret: str,
        header_prefix: str = "sha256=",
    ) -> bool:
        """Verify HMAC-SHA256 signature against webhook payload in constant time."""
        if not signature_header or not secret:
            return False

        sig = signature_header
        if header_prefix and sig.startswith(header_prefix):
            sig = sig[len(header_prefix) :]

        expected_sig = hmac.new(
            key=secret.encode("utf-8"),
            msg=payload_bytes,
            digestmod=hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(sig.strip().lower(), expected_sig.strip().lower())

    @staticmethod
    def normalize_github_webhook(
        event_name: str,
        payload_dict: dict[str, Any],
        delivery_id: str = "",
    ) -> EventPayload:
        """Normalize a GitHub webhook payload into standard EventPayload."""
        action = payload_dict.get("action", "")
        event_type = f"github:{event_name}.{action}" if action else f"github:{event_name}"

        priority = EventPriority.NORMAL
        if event_name in ("security_advisory", "deployment_status"):
            priority = EventPriority.HIGH
        elif event_name in ("issues", "pull_request") and action in ("opened", "closed"):
            priority = EventPriority.HIGH

        event_id = delivery_id or f"evt-gh-{uuid.uuid4().hex[:8]}"
        return EventPayload(
            event_id=event_id,
            source=EventSource.WEBHOOK_GITHUB,
            event_type=event_type,
            data=payload_dict,
            priority=priority,
            idempotency_key=event_id,
        )

    @staticmethod
    def normalize_custom_webhook(
        event_type: str,
        payload_dict: dict[str, Any],
        idempotency_key: str = "",
        priority: EventPriority = EventPriority.NORMAL,
    ) -> EventPayload:
        """Normalize generic or custom webhook payloads."""
        event_id = idempotency_key or f"evt-cust-{uuid.uuid4().hex[:8]}"
        return EventPayload(
            event_id=event_id,
            source=EventSource.WEBHOOK_CUSTOM,
            event_type=event_type,
            data=payload_dict,
            priority=priority,
            idempotency_key=event_id,
        )
