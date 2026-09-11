"""Agent tool definitions for trajectory logging, dataset distillation, and evals."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from dream.distill.evaluator import AutonomousEvaluator
from dream.distill.exporter import DatasetDistiller
from dream.distill.recorder import TrajectoryRecorder
from dream.distill.types import DistillFormat

_GLOBAL_RECORDER: TrajectoryRecorder | None = None
_GLOBAL_EVALUATOR: AutonomousEvaluator | None = None


def get_global_recorder() -> TrajectoryRecorder:
    """Get singleton trajectory recorder."""
    global _GLOBAL_RECORDER
    if _GLOBAL_RECORDER is None or getattr(_GLOBAL_RECORDER, "_conn", None) is None:
        _GLOBAL_RECORDER = TrajectoryRecorder()
    return _GLOBAL_RECORDER


def reset_global_distill_state() -> None:
    """Reset and close global singleton recorder and evaluator instances."""
    global _GLOBAL_RECORDER, _GLOBAL_EVALUATOR
    if _GLOBAL_RECORDER is not None:
        _GLOBAL_RECORDER.close()
        _GLOBAL_RECORDER = None
    _GLOBAL_EVALUATOR = None


def get_global_evaluator() -> AutonomousEvaluator:
    """Get singleton autonomous evaluator."""
    global _GLOBAL_EVALUATOR
    if _GLOBAL_EVALUATOR is None:
        _GLOBAL_EVALUATOR = AutonomousEvaluator()
    return _GLOBAL_EVALUATOR


def distill_record_trajectory(
    task_prompt: str,
    final_answer: str,
    success: bool = True,
    quality_score: float = 1.0,
    tags: str = "",
) -> str:
    """Record an agent execution turn into the distillation dataset.

    Args:
        task_prompt: User request or instruction.
        final_answer: Agent final resolution.
        success: Whether the turn was completed successfully.
        quality_score: Quality score from 0.0 to 1.0.
        tags: Comma-separated tags.

    Returns:
        JSON string confirming recorded trajectory ID.
    """
    recorder = get_global_recorder()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    sid = recorder.start_trajectory(task_prompt=task_prompt, tags=tag_list)
    trace = recorder.complete_trajectory(sid, final_answer=final_answer, success=success)
    if trace:
        trace.quality_score = max(0.0, min(1.0, quality_score))

    return json.dumps(
        {
            "status": "ok",
            "session_id": sid,
            "quality_score": quality_score,
            "message": "Trajectory recorded for distillation.",
        },
        ensure_ascii=False,
        indent=2,
    )


def distill_export_dataset(
    output_path: str = "dist/dataset.jsonl",
    export_format: str = "openai",
    min_quality: float = 0.7,
) -> str:
    """Export curated high-quality trajectories into a model fine-tuning dataset.

    Args:
        output_path: Destination file path.
        export_format: Output format ('openai', 'sharegpt', 'chatml', 'alpaca').
        min_quality: Minimum quality filter (default 0.7).

    Returns:
        JSON string with export statistics.
    """
    recorder = get_global_recorder()
    traces = recorder.list_trajectories(min_quality=min_quality)
    if not traces:
        # Create a sample trace if empty
        sid = recorder.start_trajectory("Test query")
        recorder.complete_trajectory(sid, final_answer="Test response", success=True)
        traces = recorder.list_trajectories(min_quality=0.0)

    res = DatasetDistiller.export_to_file(
        traces=traces,
        output_path=output_path,
        export_format=DistillFormat(export_format.lower()),
    )
    return json.dumps(res, ensure_ascii=False, indent=2)


def eval_run_benchmark(category: str = "") -> str:
    """Execute autonomous evaluation benchmark suite against agent capabilities.

    Args:
        category: Optional category filter ('persian_nlp', 'tool_calling', 'coding').

    Returns:
        JSON string with benchmark pass rate and diagnostics.
    """
    from dream.agent import Dream, EchoBackend
    from dream.memory import MemoryStore

    evaluator = get_global_evaluator()
    cat_filter = category.strip() if category.strip() else None

    with MemoryStore(":memory:") as store:
        dream = Dream(store, EchoBackend())
        report = evaluator.evaluate(dream, category_filter=cat_filter)

    return json.dumps({"status": "ok", "report": report.to_dict()}, ensure_ascii=False, indent=2)


def get_distill_tools() -> dict[str, Callable[..., Any]]:
    """Return dict of distillation and eval tools."""
    return {
        "distill_record_trajectory": distill_record_trajectory,
        "distill_export_dataset": distill_export_dataset,
        "eval_run_benchmark": eval_run_benchmark,
    }
