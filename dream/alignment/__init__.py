"""Continuous Self-Improving Alignment, Preference Generation & Critique Engine."""

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
            description=(
                "Self-improving alignment, rubric scoring, self-critique, "
                "and DPO dataset export tools."
            ),
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
