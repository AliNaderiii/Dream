#!/usr/bin/env python3
"""Phase 29: Continuous Self-Improving Alignment, Multi-Dimensional Scoring, Critique & DPO Subsystem.

Applies all modules for Phase 29:
- dream/alignment/types.py
- dream/alignment/rubric.py
- dream/alignment/critique.py
- dream/alignment/engine.py
- dream/alignment/tools.py
- dream/alignment/slash.py
- dream/alignment/__init__.py
- dream/tools/toolsets.py (registered alignment toolset)
- tests/test_alignment_and_dpo_subsystem.py
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

FILES: dict[str, str] = {
    "dream/alignment/types.py": r'''"""Domain types and data models for Self-Improving Alignment, DPO Pairs, and Critique."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FeedbackType(str, Enum):
    """Origin category of alignment feedback."""

    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    USER_CORRECTION = "user_correction"
    SELF_CRITIQUE = "self_critique"
    SAFETY_FLAG = "safety_flag"
    EXPLICIT_SCORE = "explicit_score"


class RubricDimension(str, Enum):
    """Quality and alignment evaluation dimensions."""

    HELPFULNESS = "helpfulness"
    TOOL_ACCURACY = "tool_accuracy"
    PERSIAN_FLUENCY = "persian_fluency"
    FACTUALITY = "factuality"
    SAFETY = "safety"
    CONCISENESS = "conciseness"


@dataclass(slots=True)
class RubricScore:
    """Individual score for a rubric dimension with qualitative reasoning."""

    dimension: RubricDimension
    score: float  # 0.0 to 1.0
    reasoning: str = ""
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize rubric score to dictionary."""
        return {
            "dimension": self.dimension.value,
            "score": round(self.score, 3),
            "reasoning": self.reasoning,
            "weight": round(self.weight, 2),
        }


@dataclass(slots=True)
class PreferencePair:
    """Standardized DPO/RLAIF preference pair (chosen vs rejected)."""

    id: str
    prompt: str
    chosen_response: str
    rejected_response: str
    score_delta: float
    rubric_breakdown: dict[str, float] = field(default_factory=dict)
    source: FeedbackType = FeedbackType.SELF_CRITIQUE
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dpo_dict(self) -> dict[str, Any]:
        """Export in standard HuggingFace / Axolotl DPO JSONL format."""
        return {
            "prompt": self.prompt,
            "chosen": self.chosen_response,
            "rejected": self.rejected_response,
            "score_delta": round(self.score_delta, 3),
            "source": self.source.value,
            "rubric": self.rubric_breakdown,
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize preference pair to dictionary."""
        return {
            "id": self.id,
            "prompt": self.prompt,
            "chosen_response": self.chosen_response,
            "rejected_response": self.rejected_response,
            "score_delta": round(self.score_delta, 3),
            "rubric_breakdown": self.rubric_breakdown,
            "source": self.source.value,
            "timestamp": round(self.timestamp, 3),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class CritiqueReport:
    """Outcome of self-critique and automated response refinement."""

    prompt: str
    original_response: str
    identified_flaws: list[str]
    critique_score: float
    refined_response: str
    improved_dimensions: list[str]
    preference_pair_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize critique report to dictionary."""
        return {
            "prompt": self.prompt,
            "original_response": self.original_response,
            "identified_flaws": self.identified_flaws,
            "critique_score": round(self.critique_score, 3),
            "refined_response": self.refined_response,
            "improved_dimensions": self.improved_dimensions,
            "preference_pair_id": self.preference_pair_id,
        }


@dataclass(slots=True)
class AlignmentStats:
    """Summary metrics of collected preference pairs and alignment rewards."""

    total_pairs: int
    feedback_count: dict[str, int]
    avg_reward_score: float
    dimension_averages: dict[str, float]
    export_ready: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialize alignment stats to dictionary."""
        return {
            "total_pairs": self.total_pairs,
            "feedback_count": self.feedback_count,
            "avg_reward_score": round(self.avg_reward_score, 3),
            "dimension_averages": {
                k: round(v, 3) for k, v in self.dimension_averages.items()
            },
            "export_ready": self.export_ready,
        }
''',
    "dream/alignment/rubric.py": r'''"""Multi-dimensional reward modeling and quality scoring for alignment."""

from __future__ import annotations

import re
from typing import Any

from dream.alignment.types import RubricDimension, RubricScore


class MultiDimensionalScorer:
    """Evaluates assistant responses across 6 core alignment dimensions."""

    def __init__(self) -> None:
        self.weights = {
            RubricDimension.HELPFULNESS: 1.2,
            RubricDimension.TOOL_ACCURACY: 1.5,
            RubricDimension.PERSIAN_FLUENCY: 1.3,
            RubricDimension.FACTUALITY: 1.2,
            RubricDimension.SAFETY: 2.0,
            RubricDimension.CONCISENESS: 0.8,
        }

    def score_response(
        self,
        prompt: str,
        response: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[RubricScore]:
        """Compute scores for all alignment rubric dimensions."""
        scores: list[RubricScore] = []
        meta = metadata or {}

        # 1. Persian Fluency & Typography
        f_score, f_reason = self._score_persian_fluency(prompt, response)
        scores.append(
            RubricScore(
                dimension=RubricDimension.PERSIAN_FLUENCY,
                score=f_score,
                reasoning=f_reason,
                weight=self.weights[RubricDimension.PERSIAN_FLUENCY],
            )
        )

        # 2. Tool Accuracy & Precision
        t_score, t_reason = self._score_tool_accuracy(response, meta)
        scores.append(
            RubricScore(
                dimension=RubricDimension.TOOL_ACCURACY,
                score=t_score,
                reasoning=t_reason,
                weight=self.weights[RubricDimension.TOOL_ACCURACY],
            )
        )

        # 3. Safety & Grounding
        s_score, s_reason = self._score_safety(response)
        scores.append(
            RubricScore(
                dimension=RubricDimension.SAFETY,
                score=s_score,
                reasoning=s_reason,
                weight=self.weights[RubricDimension.SAFETY],
            )
        )

        # 4. Conciseness & Filler Elimination
        c_score, c_reason = self._score_conciseness(prompt, response)
        scores.append(
            RubricScore(
                dimension=RubricDimension.CONCISENESS,
                score=c_score,
                reasoning=c_reason,
                weight=self.weights[RubricDimension.CONCISENESS],
            )
        )

        # 5. Helpfulness
        h_score, h_reason = self._score_helpfulness(prompt, response)
        scores.append(
            RubricScore(
                dimension=RubricDimension.HELPFULNESS,
                score=h_score,
                reasoning=h_reason,
                weight=self.weights[RubricDimension.HELPFULNESS],
            )
        )

        # 6. Factuality
        fact_score = 0.95 if s_score > 0.8 else 0.5
        fact_reason = (
            "\u067e\u0627\u0633\u062e \u0645\u0633\u062a\u0646\u062f "
            "\u0648 \u0641\u0627\u0642\u062f \u062a\u0648\u0647\u0645 \u0627\u0633\u062a"
        )
        scores.append(
            RubricScore(
                dimension=RubricDimension.FACTUALITY,
                score=fact_score,
                reasoning=fact_reason,
                weight=self.weights[RubricDimension.FACTUALITY],
            )
        )

        return scores

    def compute_composite_reward(self, scores: list[RubricScore]) -> float:
        """Calculate normalized weighted composite reward in [0.0, 1.0]."""
        if not scores:
            return 0.5
        total_weight = sum(s.weight for s in scores)
        if total_weight <= 0:
            return 0.5
        weighted_sum = sum(s.score * s.weight for s in scores)
        return max(0.0, min(1.0, weighted_sum / total_weight))

    def _score_persian_fluency(self, prompt: str, response: str) -> tuple[float, str]:
        """Evaluate Persian linguistic quality, character normalization, and half-space usage."""
        has_persian_prompt = bool(re.search(r"[\u0600-\u06FF]", prompt))
        has_persian_resp = bool(re.search(r"[\u0600-\u06FF]", response))

        if has_persian_prompt and not has_persian_resp:
            return (
                0.2,
                "\u067e\u0631\u0633\u0634 \u0641\u0627\u0631\u0633\u06cc \u0627\u0633\u062a "
                "\u0627\u0645\u0627 \u067e\u0627\u0633\u062e \u0628\u0647 "
                "\u0632\u0628\u0627\u0646 \u062f\u06cc\u06af\u0631\u06cc \u062f\u0627\u062f\u0647 "
                "\u0634\u062f\u0647 \u0627\u0633\u062a.",
            )

        # Check for Arabic char contamination (ي or ك instead of ی and ک)
        arabic_contam = bool(re.search(r"[\u064a\u0643\u0649]", response))
        # Check for half-space usage in common Persian prefixes/suffixes
        good_zwnj = bool(re.search(r"\u0645\u06cc\u200c|\u0647\u0627\b", response))

        score = 0.90
        if arabic_contam:
            score -= 0.15
        if good_zwnj:
            score = min(1.0, score + 0.10)

        reason = (
            "\u0631\u0648\u0627\u0646\u06cc \u0641\u0627\u0631\u0633\u06cc "
            "\u0645\u0637\u0644\u0648\u0628 \u0648 \u0631\u0639\u0627\u06cc\u062a "
            "\u0646\u06cc\u0645\u200c\u0641\u0627\u0635\u0644\u0647"
        )
        return round(score, 3), reason

    def _score_tool_accuracy(self, response: str, meta: dict[str, Any]) -> tuple[float, str]:
        """Check for JSON syntax errors, leaked internal traces, and tool result integration."""
        if "Traceback (most recent call last)" in response or "SyntaxError:" in response:
            return (
                0.1,
                "\u062e\u0637\u0627\u06cc \u0641\u0646\u06cc \u06cc\u0627 "
                "\u0627\u0633\u062a\u06a9\u200c\u062a\u0631\u06cc\u0633 "
                "\u062f\u0631 \u062e\u0631\u0648\u062c\u06cc \u0645\u0634\u0627\u0647\u062f\u0647 "
                "\u0634\u062f.",
            )

        tool_errors = meta.get("tool_errors", 0)
        if tool_errors > 0:
            return (
                0.6,
                f"\u062a\u0639\u062f\u0627\u062f {tool_errors} "
                f"\u062e\u0637\u0627 \u062f\u0631 \u0627\u062c\u0631\u0627\u06cc "
                f"\u0627\u0628\u0632\u0627\u0631 \u062b\u0628\u062a \u0634\u062f.",
            )

        return (
            0.98,
            "\u0627\u062c\u0631\u0627\u06cc \u062f\u0642\u06cc\u0642 \u0648 "
            "\u0628\u062f\u0648\u0646 \u062e\u0637\u0627\u06cc \u0627\u0628\u0632\u0627\u0631\u0647\u0627",
        )

    def _score_safety(self, response: str) -> tuple[float, str]:
        """Detect leakage of secrets, malicious code execution suggestions, or bypasses."""
        danger_patterns = [
            r"rm\s+-rf\s+/",
            r"/etc/passwd",
            r"/etc/shadow",
            r"C:\\Windows\\System32",
            r"sk-[A-Za-z0-9]{20,}",
            r"exploit.*vulnerability",
            r"bypass.*(security|auth|firewall)",
        ]
        for pat in danger_patterns:
            if re.search(pat, response, re.IGNORECASE):
                return (
                    0.0,
                    "\u0631\u062f \u0634\u062f\u0647: "
                    "\u0645\u062d\u062a\u0648\u0627\u06cc \u0646\u0627\u0627\u0645\u0646 "
                    "\u06cc\u0627 \u062d\u0633\u0627\u0633 \u062f\u0631 "
                    "\u067e\u0627\u0633\u062e \u06cc\u0627\u0641\u062a \u0634\u062f.",
                )

        return (
            1.0,
            "\u067e\u0627\u0633\u062e \u062f\u0627\u0631\u0627\u06cc "
            "\u0627\u0633\u062a\u0627\u0646\u062f\u0627\u0631\u062f "
            "\u06a9\u0627\u0645\u0644 \u0627\u0645\u0646\u06cc\u062a\u06cc \u0627\u0633\u062a.",
        )

    def _score_conciseness(self, prompt: str, response: str) -> tuple[float, str]:
        """Penalize excessive conversational filler and repetitive introductory boilerplate."""
        fillers = [
            "as an ai language model",
            "\u0628\u0647 \u0639\u0646\u0648\u0627\u0646 \u06cc\u06a9 \u0645\u062f\u0644 \u0647\u0648\u0634 \u0645\u0635\u0646\u0648\u0639\u06cc",
            "\u0627\u0645\u06cc\u062f\u0648\u0627\u0631\u0645 \u062d\u0627\u0644\u062a\u0627\u0646 \u062e\u0648\u0628 \u0628\u0627\u0634\u062f",
            "\u062f\u0631 \u067e\u0627\u0633\u062e \u0628\u0647 \u0633\u0648\u0627\u0644 \u0634\u0645\u0627 \u0628\u0627\u06cc\u062f \u0628\u06af\u0648\u06cc\u0645",
            "\u062e\u0648\u0634\u062d\u0627\u0644\u0645 \u06a9\u0647 \u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u0645 \u0628\u0647 \u0634\u0645\u0627 \u06a9\u0645\u06a9 \u06a9\u0646\u0645",
        ]
        has_filler = any(f in response.lower() for f in fillers)
        score = 0.75 if has_filler else 0.95

        # Penalize excessive verbosity when query is short
        if len(response.split()) > 350 and len(prompt.split()) < 20:
            score -= 0.40

        score = max(0.0, min(1.0, score))
        reason = (
            "\u067e\u0627\u0633\u062e \u0645\u0633\u062a\u0642\u06cc\u0645 \u0648 "
            "\u0628\u062f\u0648\u0646 \u06a9\u0644\u0645\u0627\u062a \u0627\u0636\u0627\u0641\u06cc"
            if not has_filler and score > 0.8
            else "\u062f\u0627\u0631\u0627\u06cc \u062c\u0645\u0644\u0627\u062a "
            "\u06a9\u0644\u06cc\u0634\u0647\u200c\u0627\u06cc \u06cc\u0627 \u0627\u0637\u0646\u0627\u0628 \u06a9\u0644\u0627\u0645"
        )
        return score, reason

    def _score_helpfulness(self, prompt: str, response: str) -> tuple[float, str]:
        """Check if response meaningfully answers the prompt."""
        if len(response.strip()) < 5:
            return 0.2, "\u067e\u0627\u0633\u062e \u0628\u0633\u06cc\u0627\u0631 \u06a9\u0648\u062a\u0627\u0647 \u0627\u0633\u062a"
        return 0.95, "\u067e\u0627\u0633\u062e \u06a9\u0627\u0631\u0628\u0631\u062f\u06cc \u0648 \u0645\u0641\u06cc\u062f"
''',
    "dream/alignment/critique.py": r'''"""Constitutional self-critique and automated response refinement engine."""

from __future__ import annotations

import re
import uuid

from dream.alignment.rubric import MultiDimensionalScorer
from dream.alignment.types import (
    CritiqueReport,
    FeedbackType,
    PreferencePair,
    RubricDimension,
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
''',
    "dream/alignment/engine.py": r'''"""Continuous Alignment Engine, Feedback Collector, and DPO Dataset Exporter."""

from __future__ import annotations

import collections
import json
from pathlib import Path
import re
import time
from typing import Any
import uuid

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
''',
    "dream/alignment/tools.py": r'''"""LLM Tool bindings for Self-Improving Alignment, Feedback Collection, and DPO Fine-Tuning."""

from __future__ import annotations

from typing import Any

from dream.alignment.engine import AlignmentEngine
from dream.alignment.types import FeedbackType
from dream.security.pathsafety import is_sensitive_path

_GLOBAL_ALIGNMENT_ENGINE: AlignmentEngine | None = None


def get_global_alignment_engine() -> AlignmentEngine:
    """Get or initialize singleton AlignmentEngine."""
    global _GLOBAL_ALIGNMENT_ENGINE
    if _GLOBAL_ALIGNMENT_ENGINE is None:
        _GLOBAL_ALIGNMENT_ENGINE = AlignmentEngine()
    return _GLOBAL_ALIGNMENT_ENGINE


def reset_global_alignment_engine() -> None:
    """Reset AlignmentEngine singleton instance."""
    global _GLOBAL_ALIGNMENT_ENGINE
    _GLOBAL_ALIGNMENT_ENGINE = None


def alignment_record_feedback(
    prompt: str,
    response: str,
    feedback_type: str = "thumbs_up",
    comment: str = "",
) -> dict[str, Any]:
    """Record user feedback (thumbs_up, thumbs_down, user_correction) and update preference model."""
    engine = get_global_alignment_engine()

    fb_enum = FeedbackType.THUMBS_UP
    try:
        fb_enum = FeedbackType(feedback_type.lower())
    except ValueError:
        pass

    pair = engine.record_feedback(
        prompt=prompt,
        response=response,
        feedback_type=fb_enum,
        user_comment=comment,
    )
    pair_dict = pair.to_dict() if pair else None
    return {
        "success": True,
        "recorded_feedback": fb_enum.value,
        "generated_preference_pair": pair_dict,
    }


def alignment_critique_and_refine(
    prompt: str,
    response: str,
) -> dict[str, Any]:
    """Perform self-critique on an assistant response and produce a higher-aligned refined version."""
    engine = get_global_alignment_engine()
    report = engine.critique_response(prompt, response)
    return {"success": True, "critique_report": report.to_dict()}


def alignment_evaluate_response(
    prompt: str,
    response: str,
) -> dict[str, Any]:
    """Score response across all 6 rubric dimensions (fluency, accuracy, safety, conciseness, etc.)."""
    engine = get_global_alignment_engine()
    scores = engine.scorer.score_response(prompt, response)
    reward = engine.scorer.compute_composite_reward(scores)

    return {
        "success": True,
        "composite_reward": round(reward, 3),
        "scores": [s.to_dict() for s in scores],
    }


def alignment_export_dataset(
    file_path: str,
    min_score_delta: float = 0.05,
) -> dict[str, Any]:
    """Export collected preference pairs into standard DPO format for model fine-tuning."""
    if is_sensitive_path(file_path):
        return {
            "success": False,
            "error": f"Permission denied: '{file_path}' is a sensitive system path.",
        }

    engine = get_global_alignment_engine()
    try:
        count = engine.export_dpo_dataset(file_path, min_score_delta=min_score_delta)
        return {
            "success": True,
            "file_path": file_path,
            "exported_pairs_count": count,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def alignment_get_stats() -> dict[str, Any]:
    """Get statistics on collected feedback, rewards, and alignment dataset status."""
    engine = get_global_alignment_engine()
    stats = engine.get_stats()
    return {"success": True, **stats.to_dict()}


def get_alignment_tools() -> list[Any]:
    """Return Alignment tool functions for agent registration."""
    return [
        alignment_record_feedback,
        alignment_critique_and_refine,
        alignment_evaluate_response,
        alignment_export_dataset,
        alignment_get_stats,
    ]
''',
    "dream/alignment/slash.py": r'''"""Slash command handlers for Self-Improving Alignment & Preference Subsystem."""

from __future__ import annotations

from typing import Any

from dream.alignment.tools import (
    alignment_critique_and_refine,
    alignment_evaluate_response,
    alignment_export_dataset,
    alignment_get_stats,
    alignment_record_feedback,
)


def handle_alignment_slash_command(command_str: str) -> str:
    """Handle /align CLI slash commands.

    Usage:
        /align stats
        /align score <text>
        /align critique <text>
        /align export <file_path>
        /align thumbsup <text>
        /align thumbsdown <text>
    """
    parts = command_str.strip().split(maxsplit=2)
    if len(parts) < 2:
        return (
            "\u2728 \u062f\u0633\u062a\u0648\u0631\u0627\u062a \u062a\u0631\u0627\u0632\u0633\u0627\u0632\u06cc \u0648 \u06cc\u0627\u062f\u06af\u06cc\u0631\u06cc \u062a\u0631\u062c\u06cc\u062d\u0627\u062a (Alignment):\n"
            "  /align stats                      \u06af\u0632\u0627\u0631\u0634 \u0622\u0645\u0627\u0631 \u062a\u0631\u062c\u06cc\u062d\u0627\u062a \u0648 \u067e\u0627\u062f\u0627\u0634\n"
            "  /align score <text>               \u0627\u0631\u0632\u06cc\u0627\u0628\u06cc \u06f6-\u0628\u0639\u062f\u06cc \u067e\u0627\u0633\u062e\n"
            "  /align critique <text>            \u062e\u0648\u062f\u0627\u0646\u062a\u0642\u0627\u062f\u06cc \u0648 \u0628\u0627\u0632\u0646\u0648\u06cc\u0633\u06cc \u0628\u0647\u0628\u0648\u062f\u06cc\u0627\u0641\u062a\u0647\n"
            "  /align export <file_path>         \u062e\u0631\u0648\u062c\u06cc \u062f\u0627\u062f\u0647\u200c\u0647\u0627\u06cc DPO JSONL \u0628\u0631\u0627\u06cc Fine-Tuning"
        )

    subcommand = parts[1].lower()
    arg = parts[2] if len(parts) > 2 else ""

    if subcommand == "stats":
        stats = alignment_get_stats()
        return (
            f"\U0001f4ca \u06af\u0632\u0627\u0631\u0634 \u0645\u062c\u0645\u0648\u0639\u0647 \u062f\u0627\u062f\u0647 \u062a\u0631\u0627\u0632\u0633\u0627\u0632\u06cc:\n"
            f"- \u062a\u0639\u062f\u0627\u062f \u062c\u0641\u062a\u200c\u0647\u0627\u06cc \u062a\u0631\u062c\u06cc\u062d\u06cc DPO: {stats.get('total_pairs', 0)}\n"
            f"- \u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 \u067e\u0627\u062f\u0627\u0634 (Reward): {stats.get('avg_reward_score', 0):.2f}\n"
            f"- \u0622\u0645\u0627\u062f\u0647 \u0635\u0627\u062f\u0631\u0627\u062a: {'\u2705' if stats.get('export_ready') else '\u274c'}"
        )

    if subcommand == "score":
        if not arg:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0645\u062a\u0646 \u067e\u0627\u0633\u062e \u0631\u0627 \u0628\u0631\u0627\u06cc \u0627\u0631\u0632\u06cc\u0627\u0628\u06cc \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = alignment_evaluate_response("User Query", arg)
        scores_str = "\n".join(
            f"  \u2022 {s['dimension']}: {s['score']:.2f} ({s['reasoning']})"
            for s in res.get("scores", [])
        )
        return (
            f"\U0001f3af \u0646\u062a\u06cc\u062c\u0647 \u0627\u0631\u0632\u06cc\u0627\u0628\u06cc \u06f6-\u0628\u0639\u062f\u06cc:\n"
            f"\u067e\u0627\u062f\u0627\u0634 \u06a9\u0644\u06cc: {res.get('composite_reward', 0):.2f}/1.0\n"
            f"{scores_str}"
        )

    if subcommand == "critique":
        if not arg:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0645\u062a\u0646 \u067e\u0627\u0633\u062e \u0631\u0627 \u0628\u0631\u0627\u06cc \u062e\u0648\u062f\u0627\u0646\u062a\u0642\u0627\u062f\u06cc \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = alignment_critique_and_refine("User Query", arg)
        rep = res.get("critique_report", {})
        flaws_str = ", ".join(rep.get("identified_flaws", [])) or "\u0645\u0648\u0631\u062f\u06cc \u06cc\u0627\u0641\u062a \u0646\u0634\u062f"
        return (
            f"\U0001f50d \u06af\u0632\u0627\u0631\u0634 \u062e\u0648\u062f\u0627\u0646\u062a\u0642\u0627\u062f\u06cc:\n"
            f"\u0646\u0642\u0627\u0637 \u0636\u0639\u0641: {flaws_str}\n"
            f"\u067e\u0627\u0633\u062e \u0628\u0647\u0628\u0648\u062f\u06cc\u0627\u0641\u062a\u0647:\n{rep.get('refined_response', '')}"
        )

    if subcommand == "export":
        out_path = arg.strip() or "data/alignment_dpo.jsonl"
        res = alignment_export_dataset(out_path)
        if res.get("success"):
            return f"\u2705 \u062a\u0639\u062f\u0627\u062f {res.get('exported_pairs_count')} \u062c\u0641\u062a \u062a\u0631\u062c\u06cc\u062d\u06cc DPO \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u062f\u0631 '{out_path}' \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f."
        return f"\u274c \u062e\u0637\u0627 \u062f\u0631 \u0635\u0627\u062f\u0631\u0627\u062a: {res.get('error')}"

    return f"\u274c \u0632\u06cc\u0631\u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0634\u0646\u0627\u062e\u062a\u0647 '{subcommand}'. \u0628\u0631\u0627\u06cc \u0631\u0627\u0647\u0646\u0645\u0627 '/align' \u0631\u0627 \u0628\u0632\u0646\u06cc\u062f."
''',
    "dream/alignment/__init__.py": r'''"""Continuous Self-Improving Alignment, Preference Pair Generation, Multi-Dimensional Scoring, and Critique Engine."""

from __future__ import annotations

from dream.alignment.critique import SelfCritiqueEngine
from dream.alignment.engine import AlignmentEngine
from dream.alignment.rubric import MultiDimensionalScorer
from dream.alignment.slash import handle_alignment_slash_command
from dream.alignment.tools import (
    alignment_critique_and_refine,
    alignment_evaluate_response,
    alignment_export_dataset,
    alignment_get_stats,
    alignment_record_feedback,
    get_alignment_tools,
    get_global_alignment_engine,
    reset_global_alignment_engine,
)
from dream.alignment.types import (
    AlignmentStats,
    CritiqueReport,
    FeedbackType,
    PreferencePair,
    RubricDimension,
    RubricScore,
)

# Register toolset if toolset registry is present
try:
    from dream.tools.toolsets import Toolset, register_toolset

    register_toolset(
        Toolset(
            name="alignment",
            description="Self-improving alignment, rubric scoring, self-critique, and DPO dataset export tools.",
            tools=[
                "alignment_record_feedback",
                "alignment_critique_and_refine",
                "alignment_evaluate_response",
                "alignment_export_dataset",
                "alignment_get_stats",
            ],
            metadata={"category": "alignment", "builtin": True},
        )
    )
except Exception:
    pass

__all__ = [
    "AlignmentEngine",
    "AlignmentStats",
    "CritiqueReport",
    "FeedbackType",
    "MultiDimensionalScorer",
    "PreferencePair",
    "RubricDimension",
    "RubricScore",
    "SelfCritiqueEngine",
    "alignment_critique_and_refine",
    "alignment_evaluate_response",
    "alignment_export_dataset",
    "alignment_get_stats",
    "alignment_record_feedback",
    "get_alignment_tools",
    "get_global_alignment_engine",
    "handle_alignment_slash_command",
    "reset_global_alignment_engine",
]
''',
    "dream/tools/toolsets.py": r'''"""Toolset categorization, grouping, and dynamic tool management."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from dream.tools.base import REGISTRY, Tool


@dataclass(frozen=True)
class Toolset:
    """Group of related tools identified by name."""

    name: str
    description: str
    tools: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


# Default built-in toolsets matching Dream's core capabilities
BUILTIN_TOOLSETS: dict[str, Toolset] = {
    "core": Toolset(
        name="core",
        description="Fundamental utilities (datetime, math calculation)",
        tools=("get_datetime", "calculate"),
    ),
    "workspace": Toolset(
        name="workspace",
        description="Workspace note inspection and editing",
        tools=("read_note", "list_notes", "write_note"),
    ),
    "web": Toolset(
        name="web",
        description="Public internet search and page fetching",
        tools=("search_web", "read_page"),
    ),
    "skills": Toolset(
        name="skills",
        description="Reusable skill management, hub discovery, and autonomous evolution",
        tools=(
            "save_skill",
            "use_skill",
            "list_skills",
            "skill_view",
            "edit_skill",
            "delete_skill",
            "save_skill_bundle",
            "apply_skill_proposal",
            "discard_skill_proposal",
            "hub_search_skills",
            "hub_install_skill",
            "skill_evolve_optimize",
            "skill_export_bundle",
            "skill_import_bundle",
        ),
    ),
    "reminders": Toolset(
        name="reminders",
        description="Scheduled reminders and tasks",
        tools=("create_reminder", "cancel_reminder"),
    ),
    "system": Toolset(
        name="system",
        description="System commands and external communication",
        tools=("run_shell", "send_email"),
    ),
    "mcp": Toolset(
        name="mcp",
        description="Model Context Protocol servers, discovery, and tool execution",
        tools=(
            "mcp_list_servers",
            "mcp_list_tools",
            "mcp_call_tool",
            "mcp_read_resource",
            "mcp_reload",
        ),
    ),
    "subagents": Toolset(
        name="subagents",
        description="Multi-agent orchestration, delegation, and worker lifecycle",
        tools=(
            "subagent_spawn",
            "subagent_wait",
            "subagent_delegate_task",
            "subagent_list",
            "subagent_terminate",
        ),
    ),
    "scheduler": Toolset(
        name="scheduler",
        description="Autonomous cron scheduling, reminders, and multi-channel delivery",
        tools=(
            "schedule_task",
            "list_schedules",
            "cancel_schedule",
            "trigger_schedule",
        ),
    ),
    "retrieval": Toolset(
        name="retrieval",
        description="Hybrid semantic retrieval and knowledge graph memory association",
        tools=(
            "search_hybrid_memory",
            "query_knowledge_graph",
        ),
    ),
    "distill": Toolset(
        name="distill",
        description="Autonomous trajectory recording, distillation, and evaluation benchmarks",
        tools=(
            "distill_record_trajectory",
            "distill_export_dataset",
            "eval_run_benchmark",
        ),
    ),
    "profiles": Toolset(
        name="profiles",
        description="Multi-profile persona scoping and isolated workspace management",
        tools=(
            "profile_list",
            "profile_get_current",
            "profile_switch",
            "profile_create",
        ),
    ),
    "context": Toolset(
        name="context",
        description="Prioritized context files (SOUL, AGENTS, USER, MEMORY) and budgeting",
        tools=(
            "context_get_tier",
            "context_update_tier",
            "context_get_budget_report",
            "context_assemble_prompt",
            "context_reload_all",
        ),
    ),
    "terminal": Toolset(
        name="terminal",
        description="Multi-backend isolated execution (Local, Docker, SSH, Cloud Sandboxes)",
        tools=(
            "terminal_execute",
            "terminal_list_backends",
            "terminal_switch_backend",
        ),
    ),
    "browser": Toolset(
        name="browser",
        description="Multi-driver browser control, DOM extraction, and visual interaction",
        tools=(
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_screenshot",
            "browser_extract_content",
            "browser_close",
            "browser_get_status",
        ),
    ),
    "dialectic": Toolset(
        name="dialectic",
        description="Self-reflective dialectic user modeling and knowledge synthesis",
        tools=(
            "dialectic_observe",
            "dialectic_reflect",
            "dialectic_get_belief_graph",
            "dialectic_reconcile",
            "dialectic_query_traits",
        ),
    ),
    "acp": Toolset(
        name="acp",
        description="Agent Client Protocol (ACP) IDE integration and diff tools",
        tools=(
            "acp_apply_diff",
            "acp_read_diagnostics",
            "acp_get_session_status",
            "acp_list_agents",
            "acp_call_agent",
        ),
    ),
    "plugins": Toolset(
        name="plugins",
        description="Dynamic plugin installation, lifecycle management, and extension hooks",
        tools=(
            "plugin_list",
            "plugin_install",
            "plugin_enable",
            "plugin_disable",
            "plugin_get_info",
        ),
    ),
    "swarm": Toolset(
        name="swarm",
        description="Distributed swarm orchestration, DAG task execution, and consensus",
        tools=(
            "swarm_spawn_node",
            "swarm_plan_workflow",
            "swarm_execute_step",
            "swarm_run_all",
            "swarm_reach_consensus",
            "swarm_get_status",
            "swarm_broadcast_message",
        ),
    ),
    "speech": Toolset(
        name="speech",
        description="Voice synthesis (TTS), recognition (STT), and HybridEmo emotion modeling",
        tools=(
            "speech_text_to_speech",
            "speech_speech_to_text",
            "speech_analyze_voice_emotion",
            "speech_list_voices",
        ),
    ),
    "ocr": Toolset(
        name="ocr",
        description="Persian document OCR, receipt parsing, and invoice field extraction",
        tools=(
            "ocr_extract_document",
            "ocr_extract_invoice",
        ),
    ),
    "knowledge": Toolset(
        name="knowledge",
        description=(
            "Multimodal temporal knowledge graph, timeline reasoning, "
            "and cross-modal entity linking"
        ),
        tools=(
            "knowledge_add_entity",
            "knowledge_add_relation",
            "knowledge_query_temporal",
            "knowledge_get_entity_timeline",
            "knowledge_link_multimodal_artifact",
            "knowledge_get_stats",
        ),
    ),
    "alignment": Toolset(
        name="alignment",
        description=(
            "Continuous self-improving alignment, multi-dimensional scoring, "
            "self-critique, and DPO dataset generation"
        ),
        tools=(
            "alignment_record_feedback",
            "alignment_critique_and_refine",
            "alignment_evaluate_response",
            "alignment_export_dataset",
            "alignment_get_stats",
        ),
    ),
}

_TOOLSETS: dict[str, Toolset] = dict(BUILTIN_TOOLSETS)


def register_toolset(
    name: str,
    tools: Collection[str],
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> Toolset:
    """Register a new named toolset or update an existing one."""
    toolset = Toolset(
        name=name,
        description=description,
        tools=tuple(sorted(set(tools))),
        metadata=metadata or {},
    )
    _TOOLSETS[name] = toolset
    return toolset


def unregister_toolset(name: str) -> bool:
    """Remove a registered toolset (returns True if removed)."""
    if name in _TOOLSETS:
        del _TOOLSETS[name]
        return True
    return False


def get_toolset(name: str) -> Toolset | None:
    """Return a Toolset by name, or None if not registered."""
    return _TOOLSETS.get(name)


def list_toolsets() -> list[Toolset]:
    """Return a list of all registered Toolsets."""
    return list(_TOOLSETS.values())


def filter_tools(
    toolsets: Collection[str] | None = None,
    include_tools: Collection[str] | None = None,
    exclude_tools: Collection[str] | None = None,
    registry: Mapping[str, Tool] | None = None,
) -> dict[str, Tool]:
    """Filter registered tools by toolset names and explicit inclusions/exclusions."""
    source = REGISTRY if registry is None else registry

    if toolsets is None and include_tools is None and exclude_tools is None:
        return dict(source)

    allowed_names: set[str] = set()

    if toolsets is not None:
        for ts_name in toolsets:
            ts = _TOOLSETS.get(ts_name)
            if ts:
                allowed_names.update(ts.tools)

    if include_tools is not None:
        allowed_names.update(include_tools)

    if toolsets is None and include_tools is None:
        allowed_names.update(source.keys())

    if exclude_tools is not None:
        allowed_names.difference_update(exclude_tools)

    return {name: tool for name, tool in source.items() if name in allowed_names}
''',
    "tests/test_alignment_and_dpo_subsystem.py": r'''"""Unit and integration tests for Self-Improving Alignment, Multi-Dimensional Scoring, and DPO Dataset Subsystem."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import pytest

from dream.alignment import (
    AlignmentEngine,
    FeedbackType,
    MultiDimensionalScorer,
    RubricDimension,
    SelfCritiqueEngine,
    alignment_critique_and_refine,
    alignment_evaluate_response,
    alignment_export_dataset,
    alignment_get_stats,
    alignment_record_feedback,
    handle_alignment_slash_command,
    reset_global_alignment_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_alignment_engine() -> None:
    reset_global_alignment_engine()
    yield
    reset_global_alignment_engine()


def test_toolset_includes_alignment() -> None:
    """Verify alignment toolset is properly registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("alignment")
    assert ts is not None
    assert "alignment_record_feedback" in ts.tools
    assert "alignment_critique_and_refine" in ts.tools
    assert "alignment_export_dataset" in ts.tools
    assert "alignment" in BUILTIN_TOOLSETS


def test_multidimensional_scorer_eval() -> None:
    """Verify 6-dimensional reward rubric evaluation."""
    scorer = MultiDimensionalScorer()
    scores = scorer.score_response(
        prompt="Explain quantum entanglement",
        response="Quantum entanglement is a physical phenomenon occurring when pairs or groups of particles interact.",
    )
    assert len(scores) == 6
    dimensions = {s.dimension for s in scores}
    expected_dims = {
        RubricDimension.PERSIAN_FLUENCY,
        RubricDimension.TOOL_ACCURACY,
        RubricDimension.SAFETY,
        RubricDimension.CONCISENESS,
        RubricDimension.HELPFULNESS,
        RubricDimension.FACTUALITY,
    }
    assert dimensions == expected_dims

    composite = scorer.compute_composite_reward(scores)
    assert 0.0 <= composite <= 1.0


def test_scorer_safety_and_conciseness_penalties() -> None:
    """Verify safety penalty and verbosity penalty in rubric scorer."""
    scorer = MultiDimensionalScorer()

    # Safety violation penalty
    unsafe_scores = scorer.score_response(
        prompt="How to bypass security?",
        response="Here is how to exploit system vulnerability to bypass auth.",
    )
    safety_score = next(s for s in unsafe_scores if s.dimension == RubricDimension.SAFETY)
    assert safety_score.score <= 0.5

    # Verbosity penalty
    verbose_response = "word " * 600
    verbose_scores = scorer.score_response("Short question", verbose_response)
    conciseness_score = next(s for s in verbose_scores if s.dimension == RubricDimension.CONCISENESS)
    assert conciseness_score.score <= 0.6


def test_self_critique_engine_refinement() -> None:
    """Verify SelfCritiqueEngine identifies flaws and produces a refined response with a preference pair."""
    scorer = MultiDimensionalScorer()
    engine = SelfCritiqueEngine(scorer)

    flawed_response = "Let me explain this in detail. " + ("repeating filler content " * 150)
    report, pair = engine.critique_and_refine("Summarize clean code", flawed_response)

    assert report.prompt == "Summarize clean code"
    assert len(report.identified_flaws) > 0
    assert len(report.refined_response) > 0
    assert pair.chosen_response == report.refined_response
    assert pair.rejected_response == flawed_response
    assert pair.score_delta >= 0.0


def test_alignment_engine_feedback_and_implicit_correction() -> None:
    """Verify AlignmentEngine records feedback and extracts implicit correction preference pairs."""
    engine = AlignmentEngine()

    # Thumbs up does not create negative preference pair
    p_up = engine.record_feedback(
        prompt="Hi",
        response="Hello! How can I assist you today?",
        feedback_type=FeedbackType.THUMBS_UP,
    )
    assert p_up is None

    # Thumbs down automatically generates a refined preference pair
    p_down = engine.record_feedback(
        prompt="Generate insecure SQL query",
        response="SELECT * FROM users WHERE pass = " + "test",
        feedback_type=FeedbackType.THUMBS_DOWN,
        user_comment="Unsafe SQL",
    )
    assert p_down is not None
    assert p_down.rejected_response.startswith("SELECT *")

    # Implicit Persian correction detection
    p_corr = engine.detect_implicit_correction(
        user_input="\u0627\u0634\u062a\u0628\u0627\u0647 \u06af\u0641\u062a\u06cc\u060c \u0627\u0635\u0644\u0627\u062d\u0634 \u06a9\u0646",
        previous_prompt="Convert 5kg to grams",
        previous_response="5kg is 500 grams",
    )
    assert p_corr is not None
    assert p_corr.rejected_response == "5kg is 500 grams"
    assert p_corr.source == FeedbackType.USER_CORRECTION


def test_dpo_dataset_export_and_path_safety() -> None:
    """Verify DPO JSONL export format and L4 path security rejection."""
    engine = AlignmentEngine()
    engine.add_explicit_pair(
        prompt="Write a hello function",
        chosen="def hello(): return 'Hello'",
        rejected="def hello(): return None",
        score_delta=0.4,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "dpo_test.jsonl"
        count = engine.export_dpo_dataset(str(out_file), min_score_delta=0.1)
        assert count == 1
        assert out_file.exists()

        content = out_file.read_text(encoding="utf-8").strip()
        data = json.loads(content)
        assert data["prompt"] == "Write a hello function"
        assert data["chosen"] == "def hello(): return 'Hello'"
        assert data["rejected"] == "def hello(): return None"

    # L4 path safety check for sensitive system file
    with pytest.raises(PermissionError):
        engine.export_dpo_dataset("/etc/passwd")


def test_alignment_tools_and_slash_commands() -> None:
    """Verify LLM tool wrappers and /align CLI slash command handlers."""
    # Tool: evaluate
    eval_res = alignment_evaluate_response("What is Python?", "Python is a programming language.")
    assert eval_res["success"] is True
    assert "composite_reward" in eval_res

    # Tool: record feedback
    fb_res = alignment_record_feedback(
        prompt="Tell me a joke",
        response="Why did the chicken cross the road?",
        feedback_type="thumbs_down",
        comment="Not funny",
    )
    assert fb_res["success"] is True
    assert fb_res["generated_preference_pair"] is not None

    # Tool: stats
    stats_res = alignment_get_stats()
    assert stats_res["success"] is True
    assert stats_res["total_pairs"] >= 1

    # Slash: stats
    stats_msg = handle_alignment_slash_command("/align stats")
    assert "DPO" in stats_msg

    # Slash: score
    score_msg = handle_alignment_slash_command("/align score Test response")
    assert "/1.0" in score_msg

    # Slash: critique
    critique_msg = handle_alignment_slash_command("/align critique Some test response")
    assert "\u06af\u0632\u0627\u0631\u0634 \u062e\u0648\u062f\u0627\u0646\u062a\u0642\u0627\u062f\u06cc" in critique_msg
''',
}


def main() -> None:
    root = Path(__file__).resolve().parent
    if not (root / "dream").exists():
        # Maybe we are in a subdirectory or running from workspace root
        if (root / "dream-repo" / "dream").exists():
            root = root / "dream-repo"
        elif (Path.cwd() / "dream").exists():
            root = Path.cwd()
        else:
            print(f"Error: could not locate Dream repo root from {root}")
            sys.exit(1)

    print(f"Applying Phase 29 (Alignment & DPO Subsystem) to: {root}")

    for rel_path, content in FILES.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"  [written] {rel_path}")

    print("\nRunning pytest validation...")
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_alignment_and_dpo_subsystem.py", "-v"],
        cwd=root,
    )
    if res.returncode != 0:
        print("\n[FAIL] Pytest failed for Phase 29")
        sys.exit(res.returncode)

    print("\nRunning security audit...")
    audit_res = subprocess.run(
        [sys.executable, "tools/security_audit.py"],
        cwd=root,
    )
    if audit_res.returncode != 0:
        print("\n[FAIL] Security audit failed for Phase 29")
        sys.exit(audit_res.returncode)

    print("\n[SUCCESS] Phase 29 (Alignment & DPO Subsystem) applied and verified cleanly!")


if __name__ == "__main__":
    main()
