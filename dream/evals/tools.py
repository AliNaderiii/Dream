"""LLM agent tools and singleton managers for Agent Evals and Benchmarks."""

from __future__ import annotations

import logging
from typing import Any

from dream.evals.engine import EvalsEngine

logger = logging.getLogger(__name__)

_GLOBAL_EVALS_ENGINE: EvalsEngine | None = None


def get_global_evals_engine() -> EvalsEngine:
    """Retrieve or initialize singleton EvalsEngine."""
    global _GLOBAL_EVALS_ENGINE
    if _GLOBAL_EVALS_ENGINE is None:
        _GLOBAL_EVALS_ENGINE = EvalsEngine()
    return _GLOBAL_EVALS_ENGINE


def reset_global_evals_engine() -> None:
    """Reset the global EvalsEngine instance for test isolation."""
    global _GLOBAL_EVALS_ENGINE
    if _GLOBAL_EVALS_ENGINE is not None:
        _GLOBAL_EVALS_ENGINE.reset()
    _GLOBAL_EVALS_ENGINE = None


def evals_run_suite(
    suite_id: str = "persian_core",
    fail_fast: bool = False,
) -> dict[str, Any]:
    """Execute a comprehensive benchmark test suite against the agent.

    Args:
        suite_id: Name of the evaluation suite ('persian_core', 'tool_accuracy',
            'safety_robustness', 'reasoning_depth').
        fail_fast: If True, halts execution upon the first failed test case.
    """
    engine = get_global_evals_engine()
    try:
        report = engine.run_suite(suite_id=suite_id, fail_fast=fail_fast)
        return {
            "success": True,
            "report": report.to_dict(),
            "summary_fa": report.summary_fa,
        }
    except Exception as exc:
        logger.error(f"Evals run error: {exc}")
        return {
            "success": False,
            "error": str(exc),
            "summary_fa": f"خطا در اجرای ارزیابی: {exc}",
        }


def evals_list_suites() -> dict[str, Any]:
    """List all registered benchmark test suites with descriptions and target criteria."""
    engine = get_global_evals_engine()
    suites = engine.list_suites()
    return {"success": True, "suites": suites, "total_suites": len(suites)}


def evals_compare_baseline(
    suite_id: str = "persian_core",
) -> dict[str, Any]:
    """Run benchmark and compare performance against Hermes baseline metrics.

    Args:
        suite_id: Evaluation suite to run and compare against baseline.
    """
    engine = get_global_evals_engine()
    try:
        comparison = engine.compare_against_baseline(suite_id=suite_id)
        return {"success": True, **comparison}
    except Exception as exc:
        logger.error(f"Evals comparison error: {exc}")
        return {"success": False, "error": str(exc)}


def evals_export_report() -> dict[str, Any]:
    """Export formatted Markdown report of the most recent evaluation run."""
    engine = get_global_evals_engine()
    report_md = engine.format_report_markdown()
    return {"success": True, "markdown_report": report_md}


def evals_get_status() -> dict[str, Any]:
    """Retrieve operational status, history, and metrics from EvalsEngine."""
    engine = get_global_evals_engine()
    status = engine.get_status()
    return {"success": True, **status}


def evals_reset() -> dict[str, Any]:
    """Reset all evaluation history and cached benchmark telemetry."""
    reset_global_evals_engine()
    return {"success": True, "message_fa": "تاریخچه ارزیابی‌ها با موفقیت بازنشانی شد."}


def get_evals_tools() -> list[dict[str, Any]]:
    """Return tool manifests for LLM registration."""
    return [
        {
            "name": "evals_run_suite",
            "description": (
                "Execute an agent benchmark suite (persian_core, tool_accuracy, "
                "safety_robustness, reasoning_depth).\n"
                "اجرای بنچ‌مارک جامع برای ارزیابی دقت و هوشمندی عامل."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "suite_id": {
                        "type": "string",
                        "enum": [
                            "persian_core",
                            "tool_accuracy",
                            "safety_robustness",
                            "reasoning_depth",
                        ],
                        "default": "persian_core",
                    },
                    "fail_fast": {"type": "boolean", "default": False},
                },
            },
            "handler": evals_run_suite,
        },
        {
            "name": "evals_list_suites",
            "description": "List all available evaluation suites.",
            "parameters": {"type": "object", "properties": {}},
            "handler": evals_list_suites,
        },
        {
            "name": "evals_compare_baseline",
            "description": "Compare agent performance directly against Hermes baselines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "suite_id": {"type": "string", "default": "persian_core"},
                },
            },
            "handler": evals_compare_baseline,
        },
        {
            "name": "evals_export_report",
            "description": "Export the latest evaluation report as Markdown.",
            "parameters": {"type": "object", "properties": {}},
            "handler": evals_export_report,
        },
    ]
