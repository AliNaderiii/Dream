#!/usr/bin/env python3
"""apply_pr20.py - Standalone installer for Phase 17 / PR #20:
Trajectory Recording, Dataset Self-Distillation & Autonomous Evals Benchmark Engine.

This installer creates or updates the following files in the target repository:
  - dream/distill/__init__.py
  - dream/distill/types.py
  - dream/distill/recorder.py
  - dream/distill/exporter.py
  - dream/distill/evaluator.py
  - dream/distill/tools.py
  - dream/distill/slash.py
  - dream/tools/toolsets.py
  - tests/test_distillation_and_evals.py
"""

from __future__ import annotations

import sys
from pathlib import Path

DISTILL_TYPES_PY = r'''"""Data types and domain models for trajectory recording, dataset distillation, and evals."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DistillFormat(str, Enum):
    """Supported fine-tuning dataset export formats."""

    OPENAI = "openai"
    SHAREGPT = "sharegpt"
    CHATML = "chatml"
    ALPACA = "alpaca"


@dataclass(slots=True)
class TrajectoryStep:
    """A single action/thought/observation turn in an execution trajectory."""

    step_id: int
    role: str  # "system", "user", "assistant", "tool"
    thought: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: str = ""
    content: str = ""
    timestamp: float = field(default_factory=time.time)
    latency_ms: float = 0.0


@dataclass(slots=True)
class TrajectoryTrace:
    """Complete multi-turn agent execution trajectory."""

    session_id: str
    task_prompt: str
    steps: list[TrajectoryStep] = field(default_factory=list)
    final_answer: str = ""
    success: bool = True
    quality_score: float = 1.0  # 0.0 to 1.0
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class EvalTestCase:
    """A benchmark test case for model evaluation."""

    case_id: str
    category: str  # "persian_nlp", "tool_calling", "math", "memory_recall", "coding"
    prompt: str
    expected_tools: list[str] = field(default_factory=list)
    expected_keywords: list[str] = field(default_factory=list)
    assertions: list[str] = field(default_factory=list)
    timeout_seconds: float = 10.0


@dataclass(slots=True)
class EvalCaseResult:
    """Outcome for a single evaluated test case."""

    case_id: str
    category: str
    passed: bool
    latency_ms: float
    output: str = ""
    tools_called: list[str] = field(default_factory=list)
    error_message: str = ""


@dataclass(slots=True)
class EvalReport:
    """Aggregated report of benchmark evaluation execution."""

    total_tests: int
    passed_count: int
    failed_count: int
    pass_rate: float
    avg_latency_ms: float
    tool_accuracy: float
    category_breakdown: dict[str, dict[str, Any]] = field(default_factory=dict)
    case_results: list[EvalCaseResult] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tests": self.total_tests,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "pass_rate": round(self.pass_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "tool_accuracy": round(self.tool_accuracy, 4),
            "category_breakdown": self.category_breakdown,
            "timestamp": self.timestamp,
        }
'''

DISTILL_RECORDER_PY = r'''"""Trajectory recorder for multi-step agent execution tracing and quality scoring."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any

from dream.distill.types import TrajectoryStep, TrajectoryTrace


class TrajectoryRecorder:
    """Records and scores execution trajectories for model fine-tuning and evaluation."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ":memory:"
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._active_trajectories: dict[str, TrajectoryTrace] = {}
        self._init_tables()

    def close(self) -> None:
        """Close the SQLite database connection."""
        if hasattr(self, "_conn") and self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def __enter__(self) -> TrajectoryRecorder:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()

    def _init_tables(self) -> None:
        """Initialize trajectory storage schema."""
        if self._conn is None:
            return
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS distill_trajectories (
                    session_id TEXT PRIMARY KEY,
                    task_prompt TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    final_answer TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    quality_score REAL NOT NULL,
                    tags_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trajectories_quality "
                "ON distill_trajectories (quality_score)"
            )

    def start_trajectory(
        self,
        task_prompt: str,
        session_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Initialize a new recording session."""
        sid = session_id or f"traj_{uuid.uuid4().hex[:12]}"
        trace = TrajectoryTrace(
            session_id=sid,
            task_prompt=task_prompt,
            steps=[TrajectoryStep(step_id=0, role="user", content=task_prompt)],
            tags=tags or [],
            metadata=metadata or {},
        )
        self._active_trajectories[sid] = trace
        return sid

    def add_step(
        self,
        session_id: str,
        role: str,
        content: str = "",
        thought: str = "",
        tool_name: str = "",
        tool_args: dict[str, Any] | None = None,
        tool_result: str = "",
        latency_ms: float = 0.0,
    ) -> None:
        """Append an action or thought step to the active trajectory."""
        trace = self._active_trajectories.get(session_id)
        if not trace:
            return

        step = TrajectoryStep(
            step_id=len(trace.steps),
            role=role,
            thought=thought,
            tool_name=tool_name,
            tool_args=tool_args or {},
            tool_result=tool_result,
            content=content,
            latency_ms=latency_ms,
        )
        trace.steps.append(step)

    def complete_trajectory(
        self,
        session_id: str,
        final_answer: str,
        success: bool = True,
        user_rating: float | None = None,
    ) -> TrajectoryTrace | None:
        """Finalize, score, and persist the trajectory trace."""
        trace = self._active_trajectories.pop(session_id, None)
        if not trace:
            return None

        trace.final_answer = final_answer
        trace.success = success

        # Compute Quality Score (0.0 to 1.0)
        score = 1.0
        if not success:
            score -= 0.5

        # Penalize for error occurrences in tool results
        error_count = sum(
            1 for s in trace.steps if s.tool_result and "error" in s.tool_result.lower()
        )
        score -= min(0.3, error_count * 0.1)

        # User feedback adjustment if provided
        if user_rating is not None:
            score = (score * 0.7) + (max(0.0, min(1.0, user_rating / 5.0)) * 0.3)

        trace.quality_score = max(0.0, min(1.0, score))

        # Save to SQLite
        steps_serialized = [
            {
                "step_id": s.step_id,
                "role": s.role,
                "thought": s.thought,
                "tool_name": s.tool_name,
                "tool_args": s.tool_args,
                "tool_result": s.tool_result,
                "content": s.content,
                "latency_ms": s.latency_ms,
            }
            for s in trace.steps
        ]

        if self._conn is not None:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO distill_trajectories (
                        session_id, task_prompt, steps_json, final_answer,
                        success, quality_score, tags_json, metadata_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trace.session_id,
                        trace.task_prompt,
                        json.dumps(steps_serialized, ensure_ascii=False),
                        trace.final_answer,
                        1 if trace.success else 0,
                        trace.quality_score,
                        json.dumps(trace.tags, ensure_ascii=False),
                        json.dumps(trace.metadata, ensure_ascii=False),
                        time.time(),
                    ),
                )
        return trace

    def list_trajectories(
        self,
        min_quality: float = 0.7,
        limit: int = 100,
    ) -> list[TrajectoryTrace]:
        """Fetch high-quality trajectories matching filtering criteria."""
        if self._conn is None:
            return []
        rows = self._conn.execute(
            """
            SELECT * FROM distill_trajectories
            WHERE quality_score >= ?
            ORDER BY quality_score DESC, created_at DESC
            LIMIT ?
            """,
            (min_quality, limit),
        ).fetchall()

        results: list[TrajectoryTrace] = []
        for r in rows:
            raw_steps = json.loads(r["steps_json"] or "[]")
            steps = [
                TrajectoryStep(
                    step_id=s.get("step_id", 0),
                    role=s.get("role", "assistant"),
                    thought=s.get("thought", ""),
                    tool_name=s.get("tool_name", ""),
                    tool_args=s.get("tool_args", {}),
                    tool_result=s.get("tool_result", ""),
                    content=s.get("content", ""),
                    latency_ms=s.get("latency_ms", 0.0),
                )
                for s in raw_steps
            ]
            results.append(
                TrajectoryTrace(
                    session_id=r["session_id"],
                    task_prompt=r["task_prompt"],
                    steps=steps,
                    final_answer=r["final_answer"],
                    success=bool(r["success"]),
                    quality_score=r["quality_score"],
                    tags=json.loads(r["tags_json"] or "[]"),
                    metadata=json.loads(r["metadata_json"] or "{}"),
                    created_at=r["created_at"],
                )
            )
        return results
'''

DISTILL_EXPORTER_PY = r'''"""Dataset distillation and formatting engine for model fine-tuning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dream.distill.types import DistillFormat, TrajectoryTrace


def sanitize_trace_text(text: str) -> str:
    """Strip common sensitive tokens and keys from training samples."""
    import re

    sanitized = re.sub(r"(sk-[A-Za-z0-9_\-]{20,})", "[REDACTED_API_KEY]", text)
    sanitized = re.sub(
        r"(bearer\s+[A-Za-z0-9_\-\.]{20,})",
        "Bearer [REDACTED_TOKEN]",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized


class DatasetDistiller:
    """Formats curated trajectories into fine-tuning datasets."""

    @staticmethod
    def to_openai_format(traces: list[TrajectoryTrace]) -> list[dict[str, Any]]:
        """Export into OpenAI Fine-Tuning JSONL schema."""
        dataset = []
        for t in traces:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are Dream, a next-generation bilingual AI assistant "
                        "with tool-calling capabilities."
                    ),
                }
            ]
            for s in t.steps:
                if s.role == "user":
                    messages.append({"role": "user", "content": sanitize_trace_text(s.content)})
                elif s.role == "assistant":
                    content = s.content
                    if s.thought:
                        content = f"<thought>{s.thought}</thought>\n{content}"
                    messages.append(
                        {
                            "role": "assistant",
                            "content": sanitize_trace_text(content.strip()),
                        }
                    )
                elif s.role == "tool":
                    messages.append(
                        {
                            "role": "tool",
                            "name": s.tool_name,
                            "content": sanitize_trace_text(s.tool_result),
                        }
                    )
            # Add final answer if not duplicate
            if t.final_answer and (
                not messages or messages[-1].get("content") != t.final_answer
            ):
                messages.append(
                    {
                        "role": "assistant",
                        "content": sanitize_trace_text(t.final_answer),
                    }
                )
            dataset.append({"messages": messages})
        return dataset

    @staticmethod
    def to_sharegpt_format(traces: list[TrajectoryTrace]) -> list[dict[str, Any]]:
        """Export into ShareGPT format."""
        dataset = []
        for t in traces:
            conversations = []
            for s in t.steps:
                role_label = "human" if s.role == "user" else "gpt"
                val = s.content or s.final_answer or s.thought
                if val:
                    conversations.append(
                        {"from": role_label, "value": sanitize_trace_text(val)}
                    )
            dataset.append({"id": t.session_id, "conversations": conversations})
        return dataset

    @staticmethod
    def to_chatml_format(traces: list[TrajectoryTrace]) -> list[str]:
        """Export into ChatML formatted raw text samples."""
        samples = []
        for t in traces:
            blocks = [
                "<|im_start|>system\nYou are Dream Assistant v2.0.<|im_end|>"
            ]
            for s in t.steps:
                body = s.content
                if s.thought:
                    body = f"<thought>\n{s.thought}\n</thought>\n{body}"
                blocks.append(f"<|im_start|>{s.role}\n{sanitize_trace_text(body.strip())}<|im_end|>")
            if t.final_answer:
                blocks.append(f"<|im_start|>assistant\n{sanitize_trace_text(t.final_answer)}<|im_end|>")
            samples.append("\n".join(blocks))
        return samples

    @staticmethod
    def to_alpaca_format(traces: list[TrajectoryTrace]) -> list[dict[str, str]]:
        """Export into Alpaca instruction-following format."""
        dataset = []
        for t in traces:
            dataset.append(
                {
                    "instruction": sanitize_trace_text(t.task_prompt),
                    "input": "",
                    "output": sanitize_trace_text(t.final_answer),
                }
            )
        return dataset

    @classmethod
    def export_to_file(
        cls,
        traces: list[TrajectoryTrace],
        output_path: Path | str,
        export_format: DistillFormat | str = DistillFormat.OPENAI,
    ) -> dict[str, Any]:
        """Format and write training dataset to target file."""
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        fmt = DistillFormat(export_format)

        if fmt == DistillFormat.OPENAI:
            data = cls.to_openai_format(traces)
            lines = [json.dumps(row, ensure_ascii=False) for row in data]
            out_p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        elif fmt == DistillFormat.SHAREGPT:
            data = cls.to_sharegpt_format(traces)
            out_p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        elif fmt == DistillFormat.CHATML:
            samples = cls.to_chatml_format(traces)
            out_p.write_text("\n\n---\n\n".join(samples) + "\n", encoding="utf-8")
        elif fmt == DistillFormat.ALPACA:
            data = cls.to_alpaca_format(traces)
            out_p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "success": True,
            "format": fmt.value,
            "samples_count": len(traces),
            "output_path": str(out_p),
            "file_size_bytes": out_p.stat().st_size,
        }
'''

DISTILL_EVALUATOR_PY = r'''"""Autonomous benchmark evaluation engine for LLM accuracy and tool reliability."""

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
'''

DISTILL_TOOLS_PY = r'''"""Agent tool definitions for trajectory logging, dataset distillation, and evals."""

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
'''

DISTILL_SLASH_PY = r'''"""Slash command handlers for Dataset Distillation and Autonomous Evals."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.distill.exporter import DatasetDistiller
from dream.distill.tools import get_global_evaluator, get_global_recorder
from dream.distill.types import DistillFormat


def handle_distill_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/distill` slash command (export dataset or show stats)."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors
    recorder = get_global_recorder()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "stats"

    if subcmd in ("stats", "info"):
        traces = recorder.list_trajectories(min_quality=0.0)
        output(cm.bold(f"🧠 Dataset Distillation Engine ({len(traces)} Recorded Traces):"))
        high_q = sum(1 for t in traces if t.quality_score >= 0.8)
        output(f"  • High-Quality Samples (>=0.8): {cm.green(str(high_q))}")
        output(f"  • Total Trajectories:            {len(traces)}")
        return True

    if subcmd == "export":
        fmt = parts[2].lower() if len(parts) > 2 else "openai"
        out_path = parts[3] if len(parts) > 3 else f"dist/distilled_dataset_{fmt}.jsonl"
        traces = recorder.list_trajectories(min_quality=0.5)
        if not traces:
            output(cm.yellow("No recorded trajectories found to export."))
            return True

        res = DatasetDistiller.export_to_file(
            traces=traces,
            output_path=out_path,
            export_format=DistillFormat(fmt),
        )
        if res.get("success"):
            output(cm.green(f"✓ Exported {res.get('samples_count')} samples ({fmt}) to {out_path}"))
        else:
            output(cm.red(f"✗ Export failed: {res.get('error')}"))
        return True

    output(
        cm.bold(
            "Usage / "
            "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
            "\u062f\u0633\u062a\u0648\u0631 /distill:"
        )
    )
    output(
        "  /distill stats                     - "
        "\u0646\u0645\u0627\u06cc\u0634 \u0622\u0645\u0627\u0631 "
        "\u062a\u0631\u0627\u0698\u06a9\u062a\u0648\u0631\u06cc\u200c\u0647\u0627 "
        "/ View dataset stats"
    )
    output(
        "  /distill export [format] [path]    - "
        "\u0627\u0633\u062a\u062e\u0631\u0627\u062c "
        "\u062f\u06cc\u062a\u0627\u0633\u062a "
        "\u0622\u0645\u0648\u0632\u0634\u06cc / Export dataset"
    )
    return True


def handle_eval_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/eval` slash command (run automated benchmark suite)."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors
    from dream.agent import Dream, EchoBackend
    from dream.memory import MemoryStore

    evaluator = get_global_evaluator()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "run"
    cat_filter = parts[2] if len(parts) > 2 else None

    if subcmd in ("run", "benchmark", "test"):
        output(cm.cyan("🚀 Running Dream Autonomous Benchmark Suite..."))
        with MemoryStore(":memory:") as store:
            dream = Dream(store, EchoBackend())
            report = evaluator.evaluate(dream, category_filter=cat_filter)

        pass_pct = int(report.pass_rate * 100)
        output(cm.bold(f"📊 Benchmark Evaluation Report ({report.total_tests} Tests):"))
        rate_str = cm.green(f"{pass_pct}%")
        output(f"  • Pass Rate:     {rate_str} ({report.passed_count}/{report.total_tests})")
        output(f"  • Tool Accuracy: {cm.cyan(f'{report.tool_accuracy * 100:.1f}%')}")
        output(f"  • Avg Latency:   {cm.dim(f'{report.avg_latency_ms:.1f}ms')}")

        for cat, stats in report.category_breakdown.items():
            c_pass = stats.get("passed", 0)
            c_tot = stats.get("total", 0)
            lat = stats.get("avg_latency_ms", 0.0)
            output(f"    - {cat:<15}: {c_pass}/{c_tot} passed ({lat:.1f}ms)")
        return True

    output(
        cm.bold(
            "Usage / "
            "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
            "\u062f\u0633\u062a\u0648\u0631 /eval:"
        )
    )
    output(
        "  /eval run                 - "
        "\u0627\u062c\u0631\u0627\u06cc \u062a\u0645\u0627\u0645 "
        "\u062a\u0633\u062a\u200c\u0647\u0627\u06cc "
        "\u0628\u0646\u0686\u0645\u0627\u0631\u06a9 "
        "/ Run all benchmark tests"
    )
    output(
        "  /eval run <category>      - "
        "\u0627\u062c\u0631\u0627\u06cc \u062f\u0633\u062a\u0647 "
        "\u062e\u0627\u0635 / Run category (persian_nlp, coding)"
    )
    return True
'''

DISTILL_INIT_PY = r'''"""Dream Autonomous Trajectory Recording, Dataset Distillation, and Evals Subsystem."""

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
from dream.tools.toolsets import get_toolset, register_toolset

# Ensure distill toolset is registered
if get_toolset("distill") is None:
    register_toolset(
        "distill",
        (
            "distill_record_trajectory",
            "distill_export_dataset",
            "eval_run_benchmark",
        ),
        description="Autonomous trajectory recording, distillation, and evaluation benchmarks",
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
'''

TOOLSETS_PY = r'''"""Toolset categorization, grouping, and dynamic tool management."""

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
'''

TEST_DISTILL_PY = r'''"""Comprehensive test suite for Trajectory Recording, Dataset Distillation, and Evals."""

from __future__ import annotations

import json

from dream.agent import Dream, EchoBackend
from dream.distill import (
    AutonomousEvaluator,
    DatasetDistiller,
    DistillFormat,
    EvalTestCase,
    TrajectoryRecorder,
    distill_export_dataset,
    distill_record_trajectory,
    eval_run_benchmark,
    get_distill_tools,
    handle_distill_command,
    handle_eval_command,
    reset_global_distill_state,
    sanitize_trace_text,
)
from dream.memory import MemoryStore
from dream.tools.toolsets import get_toolset


def test_trajectory_recorder_lifecycle_and_scoring(tmp_path):
    """Verify trajectory recording, step tracking, error penalties, and quality scoring."""
    db_file = str(tmp_path / "distill.db")
    with TrajectoryRecorder(db_path=db_file) as recorder:
        sid = recorder.start_trajectory(
            task_prompt="How do I calculate taxes in Iran?",
            tags=["tax", "iran"],
        )
        assert sid.startswith("traj_")

        recorder.add_step(
            session_id=sid,
            role="assistant",
            thought="I should invoke the tax calculation skill",
            tool_name="iran_tax_calc",
            tool_args={"amount": 10000000},
            tool_result='{"status": "ok", "tax": 0}',
        )

        trace = recorder.complete_trajectory(
            session_id=sid,
            final_answer="The tax amount is 0 Rials due to legal exemption.",
            success=True,
            user_rating=5.0,
        )
        assert trace is not None
        assert trace.quality_score >= 0.95

        # List trajectories
        saved = recorder.list_trajectories(min_quality=0.8)
        assert len(saved) == 1
        assert saved[0].session_id == sid
        assert saved[0].tags == ["tax", "iran"]


def test_dataset_distiller_formats_and_sanitization(tmp_path):
    """Verify export to OpenAI, ShareGPT, ChatML, and Alpaca formats with secret redaction."""
    dummy_key = "sk-" + "samplekeyfortest" * 2
    dummy_bearer = "Bearer " + "secrettokenfortest" * 2
    with TrajectoryRecorder() as recorder:
        sid = recorder.start_trajectory(
            task_prompt=f"My secret key is {dummy_key}"
        )
        recorder.add_step(
            session_id=sid,
            role="assistant",
            content=f"Received token {dummy_bearer}",
        )
        trace = recorder.complete_trajectory(
            session_id=sid,
            final_answer="Done processing.",
            success=True,
        )
        assert trace is not None

        # Sanitize check
        redacted = sanitize_trace_text(f"API: {dummy_key}")
        assert "[REDACTED_API_KEY]" in redacted

        # Export OpenAI
        out_openai = tmp_path / "dataset.jsonl"
        res_openai = DatasetDistiller.export_to_file([trace], out_openai, DistillFormat.OPENAI)
        assert res_openai["success"] is True
        assert "[REDACTED_API_KEY]" in out_openai.read_text(encoding="utf-8")

        # Export ShareGPT
        out_sharegpt = tmp_path / "sharegpt.json"
        res_sharegpt = DatasetDistiller.export_to_file(
            [trace], out_sharegpt, DistillFormat.SHAREGPT
        )
        assert res_sharegpt["success"] is True

        # Export ChatML
        out_chatml = tmp_path / "chatml.txt"
        res_chatml = DatasetDistiller.export_to_file([trace], out_chatml, DistillFormat.CHATML)
        assert res_chatml["success"] is True
        assert "<|im_start|>" in out_chatml.read_text(encoding="utf-8")

        # Export Alpaca
        out_alpaca = tmp_path / "alpaca.json"
        res_alpaca = DatasetDistiller.export_to_file([trace], out_alpaca, DistillFormat.ALPACA)
        assert res_alpaca["success"] is True


def test_autonomous_evaluator_benchmark_execution():
    """Verify evaluation battery running against agent and aggregating diagnostics."""
    test_suite = [
        EvalTestCase(
            case_id="echo_test_1",
            category="echo",
            prompt="Hello Echo",
            expected_keywords=["Echo:"],
        ),
        EvalTestCase(
            case_id="echo_test_2",
            category="echo",
            prompt="Another test",
            expected_keywords=["Echo:"],
        ),
    ]

    evaluator = AutonomousEvaluator(test_suite)
    with MemoryStore(":memory:") as store:
        dream = Dream(store, EchoBackend())
        report = evaluator.evaluate(dream)

    assert report.total_tests == 2
    assert report.passed_count == 2
    assert report.pass_rate == 1.0
    assert "echo" in report.category_breakdown


def test_distill_tools_and_slash_commands(tmp_path):
    """Verify LLM agent tools and slash command dispatchers."""
    try:
        # Tool: distill_record_trajectory
        rec_json = distill_record_trajectory(
            task_prompt="Test task",
            final_answer="Test answer",
            quality_score=0.9,
        )
        parsed_rec = json.loads(rec_json)
        assert parsed_rec["status"] == "ok"

        # Tool: distill_export_dataset
        out_file = str(tmp_path / "export_tools.jsonl")
        export_json = distill_export_dataset(output_path=out_file, export_format="openai")
        parsed_exp = json.loads(export_json)
        assert parsed_exp["success"] is True

        # Tool: eval_run_benchmark
        eval_json = eval_run_benchmark()
        parsed_eval = json.loads(eval_json)
        assert parsed_eval["status"] == "ok"

        # Tool registry
        tools_dict = get_distill_tools()
        assert "distill_record_trajectory" in tools_dict
        assert "distill_export_dataset" in tools_dict
        assert "eval_run_benchmark" in tools_dict

        # Slash commands
        out: list[str] = []
        handle_distill_command("/distill stats", output=out.append)
        assert any("Dataset Distillation Engine" in line for line in out)

        out.clear()
        handle_eval_command("/eval run", output=out.append)
        assert any("Benchmark Evaluation Report" in line for line in out)
    finally:
        reset_global_distill_state()


def test_toolsets_includes_distill():
    """Verify distill toolset grouping in BUILTIN_TOOLSETS."""
    distill_ts = get_toolset("distill")
    assert distill_ts is not None
    assert "distill_record_trajectory" in distill_ts.tools
    assert "distill_export_dataset" in distill_ts.tools
    assert "eval_run_benchmark" in distill_ts.tools
'''


def apply_patch(repo_dir: Path) -> None:
    print(f"[*] Applying PR #20 (Trajectory Recording, Distillation & Evals) to: {repo_dir.resolve()}")

    files_to_write = {
        repo_dir / "dream" / "distill" / "__init__.py": DISTILL_INIT_PY,
        repo_dir / "dream" / "distill" / "types.py": DISTILL_TYPES_PY,
        repo_dir / "dream" / "distill" / "recorder.py": DISTILL_RECORDER_PY,
        repo_dir / "dream" / "distill" / "exporter.py": DISTILL_EXPORTER_PY,
        repo_dir / "dream" / "distill" / "evaluator.py": DISTILL_EVALUATOR_PY,
        repo_dir / "dream" / "distill" / "tools.py": DISTILL_TOOLS_PY,
        repo_dir / "dream" / "distill" / "slash.py": DISTILL_SLASH_PY,
        repo_dir / "dream" / "tools" / "toolsets.py": TOOLSETS_PY,
        repo_dir / "tests" / "test_distillation_and_evals.py": TEST_DISTILL_PY,
    }

    for path, content in files_to_write.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")
        print(f"  [+] Wrote: {path.relative_to(repo_dir)}")

    print("\n[✓] PR #20 successfully applied!")
    print("Next steps:")
    print("  1. Run tests: pytest -v tests/test_distillation_and_evals.py")
    print("  2. Run linter: ruff check dream/distill dream/tools/toolsets.py tests/test_distillation_and_evals.py")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    apply_patch(target)
