"""Autonomous benchmark evaluation engine for LLM accuracy and tool reliability."""

from __future__ import annotations

import time
from typing import Any

from dream.agent import Dream
from dream.distill.types import EvalCaseResult, EvalReport, EvalTestCase

# Standard Curated Benchmark Test Battery
DEFAULT_BENCHMARK_SUITE: list[EvalTestCase] = [
    EvalTestCase(
        case_id="fa_greeting",
        category="persian_nlp",
        prompt=(
            "\u0633\u0644\u0627\u0645! \u0644\u0637\u0641\u0627\u064b "
            "\u062e\u0648\u062f\u062a \u0631\u0627 \u0628\u0647 \u0632\u0628\u0627\u0646 "
            "\u0641\u0627\u0631\u0633\u06cc \u0645\u0639\u0631\u0641\u06cc "
            "\u06a9\u0646."
        ),
        expected_keywords=[
            "\u062f\u0633\u062a\u06cc\u0627\u0631",
            "\u0647\u0648\u0634\u0645\u0646\u062f",
        ],
    ),
    EvalTestCase(
        case_id="math_calc",
        category="tool_calling",
        prompt=(
            "\u062d\u0627\u0635\u0644 \u0636\u0631\u0628 45 \u062f\u0631 12 "
            "\u0686\u06cc\u0633\u062a\u061f"
        ),
        expected_tools=["calculate"],
        expected_keywords=["540"],
    ),
    EvalTestCase(
        case_id="date_time",
        category="tool_calling",
        prompt=(
            "\u0627\u0644\u0627\u0646 \u0686\u0647 \u062a\u0627\u0631\u06cc\u062e\u06cc "
            "\u0648 \u0633\u0627\u0639\u062a\u06cc \u0627\u0633\u062a\u061f"
        ),
        expected_tools=["get_datetime"],
    ),
    EvalTestCase(
        case_id="jalali_calendar",
        category="persian_nlp",
        prompt=(
            "\u0686\u06af\u0648\u0646\u0647 \u062a\u0642\u0648\u06cc\u0645 "
            "\u0647\u062c\u0631\u06cc "
            "\u0634\u0645\u0633\u06cc \u0631\u0627 \u0628\u0631\u0627\u06cc "
            "\u06cc\u0627\u062f\u0622\u0648\u0631\u0647\u0627 \u062a\u0646\u0638\u06cc\u0645 "
            "\u06a9\u0646\u0645\u061f"
        ),
        expected_keywords=[
            "\u0634\u0645\u0633\u06cc",
            "\u06cc\u0627\u062f\u0622\u0648\u0631",
        ],
    ),
    EvalTestCase(
        case_id="code_python",
        category="coding",
        prompt=(
            "\u06cc\u06a9 \u062a\u0627\u0628\u0639 \u067e\u0627\u06cc\u062a\u0648\u0646 "
            "\u0628\u0631\u0627\u06cc \u0645\u0639\u06a9\u0648\u0633 \u06a9\u0631\u062f\u0646 "
            "\u0631\u0634\u062a\u0647 \u0628\u0646\u0648\u06cc\u0633."
        ),
        expected_keywords=["def", "return"],
    ),
]


class AutonomousEvaluator:
    """Runs automated benchmark test suites across agent backends."""

    def __init__(self, test_suite: list[EvalTestCase] | None = None) -> None:
        self.suite = test_suite or list(DEFAULT_BENCHMARK_SUITE)

    def evaluate(
        self,
        dream: Dream,
        category_filter: str | None = None,
    ) -> EvalReport:
        """Run benchmark battery against a Dream agent instance."""
        cases = self.suite
        if category_filter:
            cases = [c for c in cases if c.category.lower() == category_filter.lower()]

        total = len(cases)
        passed_count = 0
        latencies: list[float] = []
        tool_matches = 0
        total_expected_tools = 0
        case_results: list[EvalCaseResult] = []
        cat_stats: dict[str, dict[str, Any]] = {}

        for case in cases:
            if case.category not in cat_stats:
                cat_stats[case.category] = {"total": 0, "passed": 0, "latencies": []}
            cat_stats[case.category]["total"] += 1

            start_t = time.perf_counter()
            error_msg = ""
            tools_used: list[str] = []
            output_text = ""
            case_passed = True

            try:
                turn = dream.run(case.prompt)
                output_text = turn.reply
                if hasattr(turn, "tool_calls") and turn.tool_calls:
                    tools_used = [tc.get("name", "") for tc in turn.tool_calls]
            except Exception as exc:
                error_msg = str(exc)
                case_passed = False

            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            latencies.append(elapsed_ms)
            cat_stats[case.category]["latencies"].append(elapsed_ms)

            # Check expected tools
            if case.expected_tools:
                total_expected_tools += len(case.expected_tools)
                for exp_tool in case.expected_tools:
                    if exp_tool in tools_used:
                        tool_matches += 1
                    else:
                        case_passed = False

            # Check expected keywords
            for kw in case.expected_keywords:
                if kw.lower() not in output_text.lower():
                    case_passed = False

            if case_passed and not error_msg:
                passed_count += 1
                cat_stats[case.category]["passed"] += 1

            case_results.append(
                EvalCaseResult(
                    case_id=case.case_id,
                    category=case.category,
                    passed=case_passed,
                    latency_ms=elapsed_ms,
                    output=output_text,
                    tools_called=tools_used,
                    error_message=error_msg,
                )
            )

        pass_rate = passed_count / total if total > 0 else 0.0
        avg_lat = sum(latencies) / total if total > 0 else 0.0
        tool_acc = (
            tool_matches / total_expected_tools if total_expected_tools > 0 else 1.0
        )

        # Breakdown summary
        summary_breakdown = {}
        for cat, data in cat_stats.items():
            c_tot = data["total"]
            c_pass = data["passed"]
            c_lats = data["latencies"]
            summary_breakdown[cat] = {
                "total": c_tot,
                "passed": c_pass,
                "pass_rate": round(c_pass / c_tot, 4) if c_tot > 0 else 0.0,
                "avg_latency_ms": round(sum(c_lats) / c_tot, 2) if c_tot > 0 else 0.0,
            }

        return EvalReport(
            total_tests=total,
            passed_count=passed_count,
            failed_count=total - passed_count,
            pass_rate=pass_rate,
            avg_latency_ms=avg_lat,
            tool_accuracy=tool_acc,
            category_breakdown=summary_breakdown,
            case_results=case_results,
        )
