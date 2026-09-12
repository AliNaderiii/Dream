"""Continuous Alignment Engine, Feedback Collector, and DPO Dataset Exporter."""

from __future__ import annotations

import collections
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from dream.alignment.critique import SelfCritiqueEngine
from dream.alignment.rubric import MultiDimensionalScorer
from dream.alignment.types import (
    AlignmentStats,
    CritiqueReport,
    FeedbackType,
    PreferencePair,
    RubricDimension,
)
from dream.security.pathsafety import is_sensitive_path


class AlignmentEngine:
    """Coordinates preference learning, self-critique, and DPO fine-tuning dataset generation."""

    def __init__(
        self,
        scorer: MultiDimensionalScorer | None = None,
        critique_engine: SelfCritiqueEngine | None = None,
    ) -> None:
        self.scorer = scorer or MultiDimensionalScorer()
        self.critique_engine = critique_engine or SelfCritiqueEngine(self.scorer)
        self._pairs: dict[str, PreferencePair] = {}
        self._feedbacks: list[dict[str, Any]] = []

    def record_feedback(
        self,
        prompt: str,
        response: str,
        feedback_type: FeedbackType = FeedbackType.THUMBS_UP,
        user_comment: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> PreferencePair | None:
        """Record explicit or implicit user feedback and generate preference pair if negative."""
        now = time.time()
        scores = self.scorer.score_response(prompt, response, metadata)
        reward = self.scorer.compute_composite_reward(scores)

        self._feedbacks.append({
            "prompt": prompt,
            "response": response,
            "feedback_type": feedback_type.value,
            "user_comment": user_comment,
            "reward": reward,
            "timestamp": now,
        })

        if feedback_type in (FeedbackType.THUMBS_DOWN, FeedbackType.USER_CORRECTION):
            # Run self-critique to generate a superior chosen response
            _, pair = self.critique_engine.critique_and_refine(prompt, response)
            pair.source = feedback_type
            pair.metadata["user_comment"] = user_comment
            self._pairs[pair.id] = pair
            return pair

        return None

    def critique_response(
        self,
        prompt: str,
        response: str,
    ) -> CritiqueReport:
        """Analyze flaws and refine response, saving preference pair."""
        report, pair = self.critique_engine.critique_and_refine(prompt, response)
        self._pairs[pair.id] = pair
        return report

    def detect_implicit_correction(
        self,
        user_input: str,
        previous_prompt: str,
        previous_response: str,
    ) -> PreferencePair | None:
        """Identify Persian correction phrases and turn previous response into rejected sample."""
        correction_patterns = [
            r"اشتباه (گفتی|کردی|هست)",
            r"نه[،\s]+منظورم این (نبود|نیست)",
            r"دوباره (بررسی کن|بنویس)",
            r"اصلاحش کن",
            r"غلط (است|بود)",
            r"that is incorrect",
            r"you made a mistake",
        ]
        is_corr = any(re.search(pat, user_input, re.IGNORECASE) for pat in correction_patterns)
        if is_corr:
            # Generate refined pair
            combined = f"{previous_prompt} (User Correction: {user_input})"
            report, pair = self.critique_engine.critique_and_refine(combined, previous_response)
            pair.source = FeedbackType.USER_CORRECTION
            self._pairs[pair.id] = pair
            return pair

        return None

    def export_dpo_dataset(
        self,
        file_path: str,
        min_score_delta: float = 0.05,
    ) -> int:
        """Export preference pairs into standard DPO JSONL format with path safety validation."""
        if is_sensitive_path(file_path):
            raise PermissionError(f"Permission denied: '{file_path}' is a sensitive system path.")

        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        valid_pairs = [
            p for p in self._pairs.values() if p.score_delta >= min_score_delta
        ]

        lines = [json.dumps(p.to_dpo_dict(), ensure_ascii=False) for p in valid_pairs]
        path.write_text("\n".join(lines), encoding="utf-8")
        return len(valid_pairs)

    def get_stats(self) -> AlignmentStats:
        """Compute statistical summary of alignment feedback and preference dataset."""
        fb_counts: dict[str, int] = collections.defaultdict(int)
        rewards: list[float] = []

        for fb in self._feedbacks:
            fb_counts[fb["feedback_type"]] += 1
            rewards.append(fb["reward"])

        avg_reward = sum(rewards) / len(rewards) if rewards else 0.85

        dim_sums: dict[str, float] = collections.defaultdict(float)
        dim_counts: dict[str, int] = collections.defaultdict(int)

        for p in self._pairs.values():
            for dim, val in p.rubric_breakdown.items():
                dim_sums[dim] += val
                dim_counts[dim] += 1

        dim_avgs = {
            d: (dim_sums[d] / dim_counts[d])
            for d in dim_sums
        }
        if not dim_avgs:
            dim_avgs = {d.value: 0.90 for d in RubricDimension}

        return AlignmentStats(
            total_pairs=len(self._pairs),
            feedback_count=dict(fb_counts),
            avg_reward_score=avg_reward,
            dimension_averages=dim_avgs,
            export_ready=len(self._pairs) > 0,
        )

    def add_explicit_pair(
        self,
        prompt: str,
        chosen: str,
        rejected: str,
        score_delta: float = 0.2,
    ) -> PreferencePair:
        """Directly insert a curated preference pair."""
        pid = f"dpo_{uuid.uuid4().hex[:10]}"
        pair = PreferencePair(
            id=pid,
            prompt=prompt,
            chosen_response=chosen,
            rejected_response=rejected,
            score_delta=score_delta,
            source=FeedbackType.EXPLICIT_SCORE,
        )
        self._pairs[pid] = pair
        return pair
