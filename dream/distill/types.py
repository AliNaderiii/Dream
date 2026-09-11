"""Data types and domain models for trajectory recording, dataset distillation, and evals."""

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
