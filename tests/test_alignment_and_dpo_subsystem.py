"""Unit and integration tests for Self-Improving Alignment & DPO Dataset Subsystem."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from dream.alignment import (
    AlignmentEngine,
    FeedbackType,
    MultiDimensionalScorer,
    RubricDimension,
    SelfCritiqueEngine,
    alignment_evaluate_response,
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
        response=(
            "Quantum entanglement is a physical phenomenon occurring "
            "when pairs or groups of particles interact."
        ),
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
    conciseness_score = next(
        s for s in verbose_scores if s.dimension == RubricDimension.CONCISENESS
    )
    assert conciseness_score.score <= 0.6


def test_self_critique_engine_refinement() -> None:
    """Verify SelfCritiqueEngine identifies flaws and produces a refined response."""
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
    """Verify AlignmentEngine records feedback and extracts implicit correction."""
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
        user_input="اشتباه گفتی، اصلاحش کن",
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
    eval_res = alignment_evaluate_response(
        "What is Python?", "Python is a programming language."
    )
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
    assert "گزارش خودانتقادی" in critique_msg
