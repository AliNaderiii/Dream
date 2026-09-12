"""Token Quota management, sliding-window rate limiting, and consumption tracker."""

from __future__ import annotations

import time
from typing import Any

from dream.rbac.types import QuotaUsage, Tenant


class QuotaManager:
    """Enforces token budgets and sliding-window rate limits per tenant."""

    @staticmethod
    def clean_sliding_window(usage: QuotaUsage, current_time: float | None = None) -> None:
        """Prune timestamps older than 60 seconds from sliding window counters."""
        now = current_time or time.time()
        one_min_ago = now - 60.0

        usage.minute_request_timestamps = [
            ts for ts in usage.minute_request_timestamps if ts >= one_min_ago
        ]
        usage.minute_token_counts = [
            (ts, cnt) for ts, cnt in usage.minute_token_counts if ts >= one_min_ago
        ]

    @classmethod
    def check_rate_limit(
        cls,
        tenant: Tenant,
        estimated_tokens: int = 100,
        current_time: float | None = None,
    ) -> tuple[bool, str]:
        """Verify whether incoming request exceeds RPM or TPM limits.

        Returns:
            Tuple of (is_allowed, reason_fa)
        """
        now = current_time or time.time()
        usage = tenant.usage
        config = tenant.quota

        cls.clean_sliding_window(usage, now)

        # Check RPM
        current_rpm = len(usage.minute_request_timestamps)
        if current_rpm >= config.requests_per_minute:
            limit_rpm = config.requests_per_minute
            return False, f"تعداد درخواست‌ها از سقف مجاز ({limit_rpm} RPM) فراتر رفته است."

        # Check TPM
        current_tpm = sum(cnt for _, cnt in usage.minute_token_counts)
        if (current_tpm + estimated_tokens) > config.tokens_per_minute:
            limit_tpm = config.tokens_per_minute
            return False, f"حجم توکن درخواستی از سقف مجاز ({limit_tpm} TPM) فراتر رفته است."

        return True, "نرخ درخواست مجاز است."

    @classmethod
    def check_token_budget(
        cls,
        tenant: Tenant,
        requested_tokens: int = 0,
    ) -> tuple[bool, str]:
        """Verify whether token request is within monthly and daily budgets."""
        usage = tenant.usage
        config = tenant.quota

        # Check daily
        if (usage.daily_tokens_used + requested_tokens) > config.daily_token_budget:
            return False, f"سهمیه روزانه توکن ({config.daily_token_budget:,}) به پایان رسیده است."

        # Check monthly
        if (usage.monthly_tokens_used + requested_tokens) > config.monthly_token_budget:
            return False, f"سهمیه ماهانه توکن ({config.monthly_token_budget:,}) به پایان رسیده است."

        return True, "بودجه توکن مجاز است."

    @classmethod
    def record_consumption(
        cls,
        tenant: Tenant,
        tokens: int,
        is_tool_call: bool = False,
        current_time: float | None = None,
    ) -> dict[str, Any]:
        """Record consumed tokens, update sliding window, and increment counters."""
        now = current_time or time.time()
        usage = tenant.usage

        cls.clean_sliding_window(usage, now)

        usage.monthly_tokens_used += tokens
        usage.daily_tokens_used += tokens
        usage.total_requests += 1
        usage.last_request_timestamp = now
        usage.minute_request_timestamps.append(now)
        usage.minute_token_counts.append((now, tokens))

        if is_tool_call:
            usage.tool_calls_count += 1

        rem_month = max(0, tenant.quota.monthly_token_budget - usage.monthly_tokens_used)
        rem_day = max(0, tenant.quota.daily_token_budget - usage.daily_tokens_used)

        return {
            "tenant_id": tenant.tenant_id,
            "tokens_recorded": tokens,
            "monthly_used": usage.monthly_tokens_used,
            "daily_used": usage.daily_tokens_used,
            "monthly_remaining": rem_month,
            "daily_remaining": rem_day,
        }
