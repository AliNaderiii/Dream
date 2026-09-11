"""LLM Tool bindings for Self-Improving Alignment, Feedback Collection, and DPO Fine-Tuning."""

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
