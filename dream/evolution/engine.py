"""Evolutionary Orchestrator and Meta-Agent Policy Controller."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from dream.evolution.arena import StrategyEvolutionArena
from dream.evolution.distiller import HeuristicDistiller
from dream.evolution.types import (
    EvolutionMutationType,
    EvolutionReport,
    ExperiencePlayback,
)

logger = logging.getLogger(__name__)


class EvolutionEngine:
    """Coordinates experience replay, heuristic distillation, and strategy evolution."""

    def __init__(
        self,
        arena: StrategyEvolutionArena | None = None,
        distiller: HeuristicDistiller | None = None,
    ) -> None:
        self.arena = arena or StrategyEvolutionArena()
        self.distiller = distiller or HeuristicDistiller()
        self._playbacks: list[ExperiencePlayback] = []
        self._reports: list[EvolutionReport] = []
        self._seed_default_playbacks()

    def _seed_default_playbacks(self) -> None:
        """Seed sample execution playbacks for initial distillation."""
        pb1 = ExperiencePlayback(
            playback_id="pb_001",
            user_prompt="ساعت کنونی تهران را بگو و جذر ۲۵۶ را حساب کن.",
            tool_sequence=["get_datetime", "calculate"],
            final_response="ساعت ۱۴:۳۰ است و جذر ۲۵۶ برابر با ۱۶ می‌باشد.",
            success=True,
            reward_score=0.95,
        )
        pb2 = ExperiencePlayback(
            playback_id="pb_002",
            user_prompt="خلاصه یادداشت‌های پروژه را نمایش بده.",
            tool_sequence=["list_notes"],
            final_response="فهرست یادداشت‌های فعال استخراج شد.",
            success=True,
            reward_score=0.88,
        )
        self._playbacks.extend([pb1, pb2])

    def record_playback(
        self,
        user_prompt: str,
        tool_sequence: list[str],
        final_response: str,
        success: bool,
        reward_score: float,
    ) -> ExperiencePlayback:
        """Record a new trajectory for future distillation."""
        pb = ExperiencePlayback(
            playback_id=f"pb_{uuid.uuid4().hex[:6]}",
            user_prompt=user_prompt,
            tool_sequence=tool_sequence,
            final_response=final_response,
            success=success,
            reward_score=reward_score,
        )
        self._playbacks.append(pb)
        return pb

    def distill_all_heuristics(self) -> list[str]:
        """Extract and de-duplicate all rules from recorded playbacks."""
        return self.distiller.batch_distill(self._playbacks)

    def run_tournament(self, rounds: int = 3) -> EvolutionReport:
        """Run round-robin tournament across top strategy genes."""
        start_time = time.time()
        run_id = f"evo_{uuid.uuid4().hex[:8]}"
        distilled = self.distill_all_heuristics()

        leaderboard = self.arena.get_leaderboard()
        matches_count = 0

        # Execute matches
        for _ in range(rounds):
            for i in range(len(leaderboard)):
                for j in range(i + 1, len(leaderboard)):
                    g_a = leaderboard[i]
                    g_b = leaderboard[j]
                    self.arena.run_pairwise_match(g_a.gene_id, g_b.gene_id)
                    matches_count += 1

        # Apply mutation to champion
        champion = self.arena.get_leaderboard()[0]
        mutations_count = 0
        if distilled:
            self.arena.mutate_gene(
                parent_id=champion.gene_id,
                mutation_type=EvolutionMutationType.HEURISTIC_RULE_ADDITION,
                new_heuristic=distilled[0],
            )
            mutations_count += 1

        updated_board = self.arena.get_leaderboard()
        top_strat = updated_board[0]
        duration_ms = (time.time() - start_time) * 1000

        summary_fa = (
            f"🧬 تورنمنت تکاملی پایان یافت: {matches_count} مسابقه با موفقیت انجام شد. "
            f"استراتژی برتر '{top_strat.name}' با ریتینگ Elo `{top_strat.elo_rating:.1f}` "
            f"و {mutations_count} جهش جدید ثبت گردید."
        )

        report = EvolutionReport(
            run_id=run_id,
            generation=top_strat.generation,
            total_matches=matches_count,
            top_strategy=top_strat,
            leaderboard=updated_board,
            mutations_applied=mutations_count,
            distilled_rules=distilled,
            summary_fa=summary_fa,
            duration_ms=duration_ms,
        )

        self._reports.append(report)
        return report

    def format_policy_markdown(self) -> str:
        """Render distilled operational policy in formatted Markdown."""
        board = self.arena.get_leaderboard()
        rules = self.distill_all_heuristics()

        lines = [
            "## 🧬 خط‌مشی تکاملی و قوانین تقطیرشده عامل Dream (Evolutionary Policy)",
            "### 🏆 لیدربورد استراتژی‌های برتر بر اساس Elo Rating:",
        ]
        for idx, g in enumerate(board, 1):
            lines.append(
                f"{idx}. **{g.name}** (`{g.gene_id}`) — Elo: `{g.elo_rating:.1f}` "
                f"| برد/باخت: `{g.wins}/{g.losses}` | نسل: `{g.generation}`"
            )

        lines.extend([
            "",
            "### 📜 قوانین و هیوریستیک‌های تقطیرشده از تجربیات موفق:",
        ])
        if rules:
            for r in rules:
                lines.append(f"- {r}")
        else:
            lines.append("- قانونی هنوز ثبت نشده است.")

        return "\n".join(lines)

    def get_status(self) -> dict[str, Any]:
        """Return operational state and counts."""
        board = self.arena.get_leaderboard()
        return {
            "total_playbacks": len(self._playbacks),
            "total_strategy_genes": len(board),
            "top_strategy": board[0].to_dict() if board else None,
            "total_tournament_runs": len(self._reports),
        }

    def reset(self) -> None:
        """Reset evolution state."""
        self._playbacks.clear()
        self._reports.clear()
        self.arena = StrategyEvolutionArena()
        self._seed_default_playbacks()
