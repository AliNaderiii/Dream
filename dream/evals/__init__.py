"""Agent Evals & Multi-Dimensional Benchmarking Subsystem."""

from __future__ import annotations

from dream.evals.datasets import get_builtin_eval_suites
from dream.evals.engine import EvalsEngine
from dream.evals.evaluator import AgentEvaluator
from dream.evals.slash import handle_evals_slash_command
from dream.evals.tools import (
    evals_compare_baseline,
    evals_export_report,
    evals_get_status,
    evals_list_suites,
    evals_reset,
    evals_run_suite,
    get_evals_tools,
    get_global_evals_engine,
    reset_global_evals_engine,
)
from dream.evals.types import (
    BenchmarkReport,
    EvalCase,
    EvalCategory,
    EvalResult,
    EvalStatus,
    EvalSuite,
)

__all__ = [
    "AgentEvaluator",
    "BenchmarkReport",
    "EvalCase",
    "EvalCategory",
    "EvalResult",
    "EvalStatus",
    "EvalSuite",
    "EvalsEngine",
    "evals_compare_baseline",
    "evals_export_report",
    "evals_get_status",
    "evals_list_suites",
    "evals_reset",
    "evals_run_suite",
    "get_builtin_eval_suites",
    "get_evals_tools",
    "get_global_evals_engine",
    "handle_evals_slash_command",
    "reset_global_evals_engine",
]
