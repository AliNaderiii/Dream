"""Dream Autonomous Trajectory Recording, Dataset Distillation, and Evals Subsystem."""

from __future__ import annotations

from dream.distill.evaluator import DEFAULT_BENCHMARK_SUITE, AutonomousEvaluator
from dream.distill.exporter import DatasetDistiller, sanitize_trace_text
from dream.distill.recorder import TrajectoryRecorder
from dream.distill.slash import handle_distill_command, handle_eval_command
from dream.distill.tools import (
    distill_export_dataset,
    distill_record_trajectory,
    eval_run_benchmark,
    get_distill_tools,
    get_global_evaluator,
    get_global_recorder,
    reset_global_distill_state,
)
from dream.distill.types import (
    DistillFormat,
    EvalCaseResult,
    EvalReport,
    EvalTestCase,
    TrajectoryStep,
    TrajectoryTrace,
)

__all__ = [
    "DEFAULT_BENCHMARK_SUITE",
    "AutonomousEvaluator",
    "DatasetDistiller",
    "DistillFormat",
    "EvalCaseResult",
    "EvalReport",
    "EvalTestCase",
    "TrajectoryRecorder",
    "TrajectoryStep",
    "TrajectoryTrace",
    "distill_export_dataset",
    "distill_record_trajectory",
    "eval_run_benchmark",
    "get_distill_tools",
    "get_global_evaluator",
    "get_global_recorder",
    "handle_distill_command",
    "handle_eval_command",
    "reset_global_distill_state",
    "sanitize_trace_text",
]
