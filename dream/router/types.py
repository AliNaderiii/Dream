"""Domain models and data structures for Semantic Routing, Dynamic Prompt Compiler, and Cascading."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any


class IntentComplexity(str, Enum):
    """Categorization of user prompt cognitive complexity."""

    DIRECT_ANSWER = "direct_answer"  # Fast, no tools needed (e.g. greeting, basic factual)
    SIMPLE_TOOL = "simple_tool"      # Single tool call (e.g. time, simple search)
    REASONING_CHAIN = "reasoning_chain"  # Multi-step reasoning / debate
    DEEP_RESEARCH = "deep_research"    # In-depth synthesis, web crawling
    CODE_EXECUTION = "code_execution"  # Python interpreter, math proofs


class ModelTier(str, Enum):
    """LLM cost and capability tiers for cascading execution."""

    FAST_EDGE = "fast_edge"          # e.g. 8B / flash model (Low latency, high throughput)
    STANDARD_CHAT = "standard_chat"  # e.g. 70B / Sonnet (General conversational & tools)
    REASONING_HEAVY = "reasoning_heavy"  # e.g. o1 / R1 / Opus (Deep cognitive logic)


@dataclass(slots=True)
class RoutingDecision:
    """Outcome of intent routing and model tier selection."""

    decision_id: str
    query: str
    intent: IntentComplexity
    target_tier: ModelTier
    confidence: float
    estimated_latency_ms: float
    estimated_tokens_saved: int
    matched_rules: list[str] = field(default_factory=list)
    predicted_tools: list[str] = field(default_factory=list)
    rationale_fa: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize routing decision to dictionary."""
        return {
            "decision_id": self.decision_id,
            "query": self.query,
            "intent": self.intent.value,
            "target_tier": self.target_tier.value,
            "confidence": round(self.confidence, 3),
            "estimated_latency_ms": round(self.estimated_latency_ms, 2),
            "estimated_tokens_saved": self.estimated_tokens_saved,
            "matched_rules": self.matched_rules,
            "predicted_tools": self.predicted_tools,
            "rationale_fa": self.rationale_fa,
            "timestamp": round(self.timestamp, 2),
        }


@dataclass(slots=True)
class PromptSection:
    """A modular block of a prompt with priority and token cost."""

    section_id: str
    title: str
    content: str
    priority: int = 100  # Higher number = higher priority to keep under budget
    is_mandatory: bool = False
    estimated_tokens: int = 0

    def __post_init__(self) -> None:
        if self.estimated_tokens == 0 and self.content:
            # Approximate 4 characters per token
            object.__setattr__(self, "estimated_tokens", max(1, len(self.content) // 4))


@dataclass(slots=True)
class CompiledPrompt:
    """Result of AST-like prompt compilation and token budgeting."""

    template_name: str
    target_tier: ModelTier
    system_prompt: str
    user_prompt: str
    total_tokens: int
    max_budget_tokens: int
    included_sections: list[str]
    dropped_sections: list[str]
    compilation_time_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize compiled prompt metadata."""
        return {
            "template_name": self.template_name,
            "target_tier": self.target_tier.value,
            "system_prompt_length": len(self.system_prompt),
            "user_prompt_length": len(self.user_prompt),
            "total_tokens": self.total_tokens,
            "max_budget_tokens": self.max_budget_tokens,
            "included_sections": self.included_sections,
            "dropped_sections": self.dropped_sections,
            "compilation_time_ms": round(self.compilation_time_ms, 2),
        }


@dataclass(slots=True)
class RouterStats:
    """Aggregate statistics for routing and cascading savings."""

    total_routed: int
    direct_answers: int
    simple_tools: int
    reasoning_chains: int
    deep_researches: int
    code_executions: int
    total_tokens_saved: int
    average_latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize router statistics."""
        return {
            "total_routed": self.total_routed,
            "direct_answers": self.direct_answers,
            "simple_tools": self.simple_tools,
            "reasoning_chains": self.reasoning_chains,
            "deep_researches": self.deep_researches,
            "code_executions": self.code_executions,
            "total_tokens_saved": self.total_tokens_saved,
            "average_latency_ms": round(self.average_latency_ms, 2),
        }
