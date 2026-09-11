"""Dynamic token and character budget allocation with priority waterfall overflow."""

from __future__ import annotations

from typing import Any

from dream.context.types import ContextFile, ContextTier

TIER_PRIORITY_ORDER = [
    ContextTier.SOUL,
    ContextTier.AGENTS,
    ContextTier.USER,
    ContextTier.MEMORY,
]


class TokenBudgetManager:
    """Manages adaptive token allocation and waterfall overflow across context tiers."""

    def __init__(self, total_max_chars: int = 8000) -> None:
        self.total_max_chars = total_max_chars

    def allocate_budgets(
        self,
        files: dict[ContextTier, ContextFile],
    ) -> dict[ContextTier, int]:
        """Compute waterfall budget allocation so surplus budget flows to lower tiers."""
        allocated: dict[ContextTier, int] = {}
        surplus = 0

        for tier in TIER_PRIORITY_ORDER:
            cfile = files.get(tier)
            base_budget = cfile.default_char_budget if cfile else 2000
            current_len = len(cfile.content) if cfile else 0

            target_budget = base_budget + surplus
            if current_len < target_budget:
                surplus = target_budget - current_len
                allocated[tier] = current_len
            else:
                allocated[tier] = target_budget
                surplus = 0

        # Update files with allocated budgets
        for tier, budget in allocated.items():
            if tier in files:
                files[tier].allocated_char_budget = budget

        return allocated

    def fit_content(self, cfile: ContextFile) -> str:
        """Truncate content cleanly if it exceeds the allocated character budget."""
        budget = cfile.allocated_char_budget
        content = cfile.content

        if len(content) <= budget:
            return content

        notice = "\n\n[... Truncated to fit context budget ...]"
        effective_limit = max(100, budget - len(notice))
        return content[:effective_limit] + notice

    def get_budget_report(
        self,
        files: dict[ContextTier, ContextFile],
    ) -> dict[str, Any]:
        """Generate a breakdown of context file sizes vs allocated budgets."""
        self.allocate_budgets(files)
        report: dict[str, Any] = {
            "total_max_chars": self.total_max_chars,
            "tiers": {},
        }

        total_used = 0
        for tier in TIER_PRIORITY_ORDER:
            cf = files.get(tier)
            if cf:
                used = len(self.fit_content(cf))
                total_used += used
                report["tiers"][tier.value] = {
                    "file": cf.filename,
                    "actual_length": len(cf.content),
                    "allocated_budget": cf.allocated_char_budget,
                    "rendered_length": used,
                }

        report["total_rendered_chars"] = total_used
        report["estimated_tokens"] = round(total_used / 4)
        return report
