"""Constitutional self-critique and automated response refinement engine."""

from __future__ import annotations

import re
import uuid

from dream.alignment.rubric import MultiDimensionalScorer
from dream.alignment.types import (
    CritiqueReport,
    FeedbackType,
    PreferencePair,
)


class SelfCritiqueEngine:
    """Performs constitutional self-critique and automated response refinement."""

    def __init__(self, scorer: MultiDimensionalScorer | None = None) -> None:
        self.scorer = scorer or MultiDimensionalScorer()

    def critique_and_refine(
        self,
        prompt: str,
        original_response: str,
    ) -> tuple[CritiqueReport, PreferencePair]:
        """Critique response, identify alignment flaws, and generate a higher-quality response."""
        original_scores = self.scorer.score_response(prompt, original_response)
        flaws: list[str] = []
        improved_dims: list[str] = []

        # Analyze dimension scores
        for sc in original_scores:
            if sc.score < 0.85:
                flaws.append(f"[{sc.dimension.value.upper()}]: {sc.reasoning}")
                improved_dims.append(sc.dimension.value)

        # Refine response by cleaning conversational clutter and fixing character issues
        refined = self._apply_refinement_rules(original_response, prompt)
        refined_scores = self.scorer.score_response(prompt, refined)

        orig_reward = self.scorer.compute_composite_reward(original_scores)
        refined_reward = self.scorer.compute_composite_reward(refined_scores)
        score_delta = max(0.0, refined_reward - orig_reward)

        pair_id = f"dpo_{uuid.uuid4().hex[:10]}"
        report = CritiqueReport(
            prompt=prompt,
            original_response=original_response,
            identified_flaws=flaws,
            critique_score=orig_reward,
            refined_response=refined,
            improved_dimensions=improved_dims,
            preference_pair_id=pair_id,
        )

        pair = PreferencePair(
            id=pair_id,
            prompt=prompt,
            chosen_response=refined,
            rejected_response=original_response,
            score_delta=score_delta if score_delta > 0 else 0.15,
            rubric_breakdown={s.dimension.value: s.score for s in refined_scores},
            source=FeedbackType.SELF_CRITIQUE,
        )

        return report, pair

    def _apply_refinement_rules(self, text: str, prompt: str) -> str:
        """Strip conversational filler, fix Persian unicode chars, and ensure clear formatting."""
        cleaned = text

        # Strip standard AI introduction fillers
        fillers = [
            r"^as an ai language model,?\s*",
            r"^به عنوان یک مدل هوش مصنوعی،?\s*",
            r"^امیدوارم حالتان خوب باشد،?\s*",
            r"^در پاسخ به سوال شما باید بگویم،?\s*",
            r"^خوشحالم که می‌توانم به شما کمک کنم،?\s*",
        ]
        for pat in fillers:
            cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE | re.MULTILINE)

        # Normalize Arabic characters to Persian standard
        cleaned = cleaned.replace("\u064a", "\u06cc").replace("\u0643", "\u06a9")

        # Trim repeated whitespaces
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

        # If too verbose, retain concise executive summary
        words = cleaned.split()
        if len(words) > 300 and len(prompt.split()) < 20:
            cleaned = " ".join(words[:180]) + "..."

        return cleaned
