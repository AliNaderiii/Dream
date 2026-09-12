"""Dataset Curator, Decontamination, and Quality Scoring Engine."""

from __future__ import annotations

import re
from typing import Any

from dream.synthetic.types import (
    FilterCriteria,
    SampleQualityTier,
    SyntheticSample,
)


class DatasetCurator:
    """Evaluates, filters, deduplicates, and scores synthetic samples for training."""

    def curate_and_filter(
        self,
        samples: list[SyntheticSample],
        criteria: FilterCriteria | None = None,
    ) -> tuple[list[SyntheticSample], list[SyntheticSample], dict[str, Any]]:
        """Filter samples against quality criteria and deduplicate.

        Returns:
            (accepted_samples, rejected_samples, curation_metrics)
        """
        crit = criteria or FilterCriteria()
        accepted: list[SyntheticSample] = []
        rejected: list[SyntheticSample] = []

        seen_prompts: list[str] = []

        for s in samples:
            score = self.score_sample(s)
            s.quality_score = score
            s.quality_tier = self._classify_tier(score)

            # Quality score threshold
            if score < crit.min_quality_score:
                s.metadata["rejection_reason"] = "low_quality_score"
                rejected.append(s)
                continue

            # Reasoning length check
            if (
                crit.min_reasoning_length_chars > 0
                and len(s.reasoning_trace) < crit.min_reasoning_length_chars
            ):
                s.metadata["rejection_reason"] = "insufficient_reasoning_trace"
                rejected.append(s)
                continue

            # Persian language requirement
            if crit.require_persian_fluency and not re.search(r"[\u0600-\u06FF]", s.prompt):
                s.metadata["rejection_reason"] = "missing_persian_script"
                rejected.append(s)
                continue

            # Deduplication check via Jaccard similarity
            is_duplicate = False
            for prev_p in seen_prompts:
                sim = self._jaccard_similarity(s.prompt, prev_p)
                if sim >= crit.deduplication_threshold:
                    is_duplicate = True
                    break

            if is_duplicate:
                s.metadata["rejection_reason"] = "duplicate_prompt"
                rejected.append(s)
                continue

            seen_prompts.append(s.prompt)
            accepted.append(s)

        avg_score = (
            sum(s.quality_score for s in accepted) / len(accepted) if accepted else 0.0
        )

        metrics = {
            "total_input_samples": len(samples),
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "retention_rate_pct": round((len(accepted) / max(1, len(samples))) * 100, 2),
            "average_quality_score": round(avg_score, 4),
        }

        return accepted, rejected, metrics

    def score_sample(self, sample: SyntheticSample) -> float:
        """Heuristic quality scoring based on length, structure, and formatting."""
        score = 0.80

        # Prompt completeness
        if len(sample.prompt.strip()) > 15:
            score += 0.05

        # Chosen response quality
        if len(sample.chosen_response.strip()) > 40:
            score += 0.05

        # Reasoning presence
        if len(sample.reasoning_trace.strip()) > 30:
            score += 0.05

        # DPO rejected candidate presence
        if sample.rejected_response and len(sample.rejected_response.strip()) > 15:
            score += 0.05

        return min(1.0, max(0.0, score))

    @staticmethod
    def _classify_tier(score: float) -> SampleQualityTier:
        """Map numeric score to quality tier."""
        if score >= 0.90:
            return SampleQualityTier.PRISTINE
        elif score >= 0.75:
            return SampleQualityTier.HIGH
        elif score >= 0.60:
            return SampleQualityTier.ACCEPTABLE
        return SampleQualityTier.REJECTED

    @staticmethod
    def _jaccard_similarity(str1: str, str2: str) -> float:
        """Compute token-level Jaccard similarity."""
        set1 = set(str1.lower().split())
        set2 = set(str2.lower().split())
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0
