"""Domain types and data models for Self-Improving Alignment, DPO Pairs, and Critique."""

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
