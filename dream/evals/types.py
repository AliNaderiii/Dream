"""Data types, metrics, and models for Agent Evals & Benchmark Subsystem."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvalCategory(str, Enum):
    """Core evaluation dimensions for intelligent agents."""

    TOOL_ACCURACY = "tool_accuracy"
    PERSIAN_FLUENCY = "persian_fluency"
    REASONING_DEPTH = "reasoning_depth"
    FACTUALITY = "factuality"
    SAFETY_ROBUSTNESS = "safety_robustness"
    LATENCY_EFFICIENCY = "latency_efficiency"


class EvalStatus(str, Enum):
    """Lifecycle state of an evaluation run."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


@dataclass(slots=True)
class EvalCase:
    """Individual benchmark test scenario."""

    case_id: str
    category: EvalCategory
    prompt: str
    expected_tools: list[str] = field(default_factory=list)
    expected_substrings: list[str] = field(default_factory=list)
    forbidden_substrings: list[str] = field(default_factory=list)
    min_score_threshold: float = 0.75
    metadata: dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize eval case to dictionary."""
        return {
            "case_id": self.case_id,
            "category": self.category.value,
            "prompt": self.prompt,
            "expected_tools": self.expected_tools,
            "expected_substrings": self.expected_substrings,
            "forbidden_substrings": self.forbidden_substrings,
            "min_score_threshold": self.min_score_threshold,
            "metadata": self.metadata,
            "weight": self.weight,
        }


@dataclass(slots=True)
class EvalResult:
    """Evaluation score and trace outcome for an individual test case."""

    case_id: str
    category: EvalCategory
    passed: bool
    score: float
    actual_response: str
    actual_tools_called: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    tokens_consumed: int = 0
    feedback_fa: str = ""
    error_message: str | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize eval result to dictionary."""
        return {
            "case_id": self.case_id,
            "category": self.category.value,
            "passed": self.passed,
            "score": round(self.score, 3),
            "actual_response": self.actual_response,
            "actual_tools_called": self.actual_tools_called,
            "latency_ms": round(self.latency_ms, 2),
            "tokens_consumed": self.tokens_consumed,
            "feedback_fa": self.feedback_fa,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class EvalSuite:
    """Named collection of evaluation cases targeting specific capabilities."""

    suite_id: str
    name: str
    description_fa: str
    cases: list[EvalCase]
    target_pass_rate: float = 0.85
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize suite to dictionary."""
        return {
            "suite_id": self.suite_id,
            "name": self.name,
            "description_fa": self.description_fa,
            "total_cases": len(self.cases),
            "cases": [c.to_dict() for c in self.cases],
            "target_pass_rate": self.target_pass_rate,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class BenchmarkReport:
    """Aggregate benchmark results and comparative performance radar."""

    run_id: str
    suite_id: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    overall_pass_rate: float
    overall_composite_score: float
    category_scores: dict[str, float]
    average_latency_ms: float
    total_tokens_consumed: int
    results: list[EvalResult]
    summary_fa: str
    duration_ms: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize benchmark report to dictionary."""
        return {
            "run_id": self.run_id,
            "suite_id": self.suite_id,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "overall_pass_rate": round(self.overall_pass_rate, 3),
            "overall_composite_score": round(self.overall_composite_score, 3),
            "category_scores": {k: round(v, 3) for k, v in self.category_scores.items()},
            "average_latency_ms": round(self.average_latency_ms, 2),
            "total_tokens_consumed": self.total_tokens_consumed,
            "results": [r.to_dict() for r in self.results],
            "summary_fa": self.summary_fa,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": self.timestamp,
        }
