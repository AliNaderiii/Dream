"""Resource Watchdog: CPU quotas, memory limits, and output bounding."""

from __future__ import annotations

from dream.sandbox.isolation.types import ResourceQuota


class ResourceWatchdog:
    """Enforces execution deadlines, limits output buffer sizes, and monitors quotas."""

    def __init__(self, quota: ResourceQuota | None = None) -> None:
        self.quota = quota or ResourceQuota()

    def clamp_output(self, text: str) -> str:
        """Truncate text exceeding output byte quota."""
        max_bytes = self.quota.max_output_bytes
        encoded = text.encode("utf-8")
        if len(encoded) <= max_bytes:
            return text
        truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
        return truncated + "\n... [Output Truncated by Resource Watchdog]"

    def check_duration_quota(self, duration_ms: float) -> bool:
        """Verify execution duration is within allotted CPU limit."""
        return (duration_ms / 1000.0) <= self.quota.max_cpu_time_sec
