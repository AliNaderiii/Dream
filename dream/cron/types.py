"""Type definitions for scheduled tasks, delivery targets, and execution records."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeliveryTargetConfig:
    """Outbound destination for scheduled execution results."""

    platform: str = "local"  # "local", "telegram", "discord", "slack", "webhook"
    target_id: str = ""      # recipient_id, channel_id, or webhook URL
    extra_params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "target_id": self.target_id,
            "extra_params": self.extra_params,
        }

    @classmethod
    def from_str(cls, text: str) -> DeliveryTargetConfig:
        """Parse 'platform:target_id' string (e.g. 'telegram:12345678')."""
        clean = text.strip()
        if ":" in clean:
            plat, _, tid = clean.partition(":")
            return cls(platform=plat.strip().lower(), target_id=tid.strip())
        return cls(platform=clean.lower(), target_id="")


@dataclass
class ScheduledTaskRecord:
    """Observable record of a persistent scheduled task."""

    id: str
    prompt: str
    cron_expr: str
    description: str
    delivery: DeliveryTargetConfig
    name: str = ""
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_run_at: float | None = None
    next_run_at: float | None = None
    runs_count: int = 0
    last_status: str = "pending"
    last_result: str | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name or f"task_{self.id[:6]}",
            "prompt": self.prompt,
            "cron_expr": self.cron_expr,
            "description": self.description,
            "delivery": self.delivery.to_dict(),
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_run_at": self.last_run_at,
            "next_run_at": self.next_run_at,
            "runs_count": self.runs_count,
            "last_status": self.last_status,
            "last_result": self.last_result,
            "last_error": self.last_error,
        }
