"""Procedural rule extraction and heuristic policy distillation."""

from __future__ import annotations

import re

from dream.evolution.types import ExperiencePlayback
from dream.memory import normalize_fa


class HeuristicDistiller:
    """Distills generalizable operational rules and best practices from execution traces."""

    def distill_from_playback(self, playback: ExperiencePlayback) -> str:
        """Extract a single high-impact heuristic from a successful execution trace."""
        if not playback.success or playback.reward_score < 0.70:
            return "عدم استخراج قانون: عملکرد دارای امتیاز کافی نیست."

        prompt_clean = normalize_fa(playback.user_prompt)
        tools = playback.tool_sequence

        # 1. Chained tool execution heuristics
        if len(tools) >= 2:
            t_chain = " ➔ ".join(tools)
            heuristic = (
                f"قانون زنجیره ابزار: برای درخواست‌های مشابه با الگوی "
                f"«{prompt_clean[:30]}...»، ترکیب بهینه ابزارها شامل [{t_chain}] است."
            )
        elif tools:
            heuristic = (
                f"قانون تک‌ابزار: اجرای مستقیم ابزار '{tools[0]}' "
                f"با بالاترین سرعت پاسخ‌دهی همراه است."
            )
        else:
            heuristic = (
                "قانون پاسخ مستقیم: عدم نیاز به ابزارهای جانبی در سوالات مفهومی صریح."
            )

        playback.distilled_heuristic = heuristic
        return heuristic

    def batch_distill(self, playbacks: list[ExperiencePlayback]) -> list[str]:
        """Distill and de-duplicate rules across a batch of playbacks."""
        rules: list[str] = []
        seen: set[str] = set()

        for pb in playbacks:
            rule = self.distill_from_playback(pb)
            if rule and not rule.startswith("عدم استخراج"):
                norm_rule = re.sub(r"\s+", " ", rule).strip()
                if norm_rule not in seen:
                    seen.add(norm_rule)
                    rules.append(norm_rule)

        return rules
