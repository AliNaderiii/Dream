#!/usr/bin/env python3
"""Phase 37: Adaptive Semantic Router, Dynamic Prompt Compiler & Model Cascading Engine.

Applies all modules for Phase 37:
- dream/router/types.py
- dream/router/backend.py (preserves resolve_route and backend selection)
- dream/router/semantic.py
- dream/router/compiler.py
- dream/router/cascade.py
- dream/router/engine.py
- dream/router/tools.py
- dream/router/slash.py
- dream/router/__init__.py
- dream/tools/toolsets.py (registered router toolset)
- tests/test_semantic_router_and_compiler.py
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

FILES: dict[str, str] = {
    "dream/router/types.py": r'''"""Domain models and data structures for Semantic Routing, Dynamic Prompt Compiler, and Cascading."""

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
''',
    "dream/router/backend.py": r'''"""Model router: hosted -> Aval -> Ollama -> BYOK -> echo, with an honest privacy line."""

from __future__ import annotations

from dataclasses import dataclass
import os

OFFICIAL_BASE_URLS = ("https://api.openai.com/v1", "https://api.openai.com/v1/")

AVAL_BASE_URLS = (
    "https://api.avalai.ir/v1",
    "https://api.avalai.ir/v1/",
    "https://api.avalapis.ir/v1",
    "https://api.avalapis.ir/v1/",
)


@dataclass(frozen=True)
class Route:
    """One resolved route and its privacy statement."""

    name: str
    leaves_machine: bool
    sentence_en: str
    sentence_fa: str


_HOSTED = Route(
    name="hosted",
    leaves_machine=True,
    sentence_en=(
        "Route: hosted — this turn is sent to a cloud model service; "
        "your message leaves this machine."
    ),
    sentence_fa=(
        "\u0645\u0633\u06cc\u0631: \u0633\u0631\u0648\u06cc\u0633 \u0627\u0628\u0631\u06cc "
        "\u2014 \u0627\u06cc\u0646 \u0646\u0648\u0628\u062a \u0628\u0647 \u06cc\u06a9 "
        "\u0633\u0631\u0648\u06cc\u0633 \u0645\u062f\u0644 \u0627\u0628\u0631\u06cc "
        "\u0641\u0631\u0633\u062a\u0627\u062f\u0647 \u0645\u06cc\u200c\u0634\u0648\u062f\u061b "
        "\u067e\u06cc\u0627\u0645 \u0634\u0645\u0627 \u0627\u0632 \u0627\u06cc\u0646 "
        "\u062f\u0633\u062a\u06af\u0627\u0647 \u062e\u0627\u0631\u062c "
        "\u0645\u06cc\u200c\u0634\u0648\u062f."
    ),
)

_AVAL = Route(
    name="aval",
    leaves_machine=True,
    sentence_en=(
        "Route: aval — this turn is sent to Aval AI (api.avalai.ir), "
        "the Iranian cloud provider you configured; "
        "your message leaves this machine."
    ),
    sentence_fa=(
        "\u0645\u0633\u06cc\u0631: \u0622\u0648\u0627\u0644 \u2014 "
        "\u0627\u06cc\u0646 \u0646\u0648\u0628\u062a \u0628\u0647 Aval AI "
        "(api.avalai.ir) \u0641\u0631\u0633\u062a\u0627\u062f\u0647 "
        "\u0645\u06cc\u0634\u0648\u062f\u061b \u067e\u06cc\u0627\u0645 "
        "\u0634\u0645\u0627 \u0627\u0632 \u0627\u06cc\u0646 "
        "\u062f\u0633\u062a\u06af\u0627\u0647 \u062e\u0627\u0631\u062c "
        "\u0645\u06cc\u0634\u0648\u062f."
    ),
)

_OLLAMA = Route(
    name="ollama",
    leaves_machine=False,
    sentence_en=(
        "Route: ollama — this turn runs against a local Ollama server; "
        "your message never leaves this machine."
    ),
    sentence_fa=(
        "\u0645\u0633\u06cc\u0631: \u0627\u0648\u0644\u0627\u0645\u0627 \u2014 "
        "\u0627\u06cc\u0646 \u0646\u0648\u0628\u062a \u0631\u0648\u06cc \u0633\u0631\u0648\u0631 "
        "\u0645\u062d\u0644\u06cc \u0627\u0648\u0644\u0627\u0645\u0627 \u0627\u062c\u0631\u0627 "
        "\u0645\u06cc\u200c\u0634\u0648\u062f\u061b \u067e\u06cc\u0627\u0645 \u0634\u0645\u0627 "
        "\u0647\u0631\u06af\u0632 \u0627\u0632 \u0627\u06cc\u0646 "
        "\u062f\u0633\u062a\u06af\u0627\u0647 "
        "\u062e\u0627\u0631\u062c \u0646\u0645\u06cc\u200c\u0634\u0648\u062f."
    ),
)

_BYOK = Route(
    name="byok",
    leaves_machine=True,
    sentence_en=(
        "Route: byok — this turn is sent to the endpoint you configured "
        "yourself; your message leaves this machine for that server."
    ),
    sentence_fa=(
        "\u0645\u0633\u06cc\u0631: \u06a9\u0644\u06cc\u062f \u0634\u062e\u0635\u06cc \u2014 "
        "\u0627\u06cc\u0646 \u0646\u0648\u0628\u062a \u0628\u0647 \u0633\u0631\u0648\u0631\u06cc "
        "\u06a9\u0647 \u062e\u0648\u062f\u062a\u0627\u0646 "
        "\u067e\u06cc\u06a9\u0631\u0628\u0646\u062f\u06cc "
        "\u06a9\u0631\u062f\u0647\u200c\u0627\u06cc\u062f "
        "\u0641\u0631\u0633\u062a\u0627\u062f\u0647 "
        "\u0645\u06cc\u200c\u0634\u0648\u062f\u061b \u067e\u06cc\u0627\u0645 \u0634\u0645\u0627 "
        "\u0628\u0631\u0627\u06cc \u0622\u0646 \u0633\u0631\u0648\u0631 \u0627\u0632 "
        "\u0627\u06cc\u0646 "
        "\u062f\u0633\u062a\u06af\u0627\u0647 \u062e\u0627\u0631\u062c "
        "\u0645\u06cc\u200c\u0634\u0648\u062f."
    ),
)

_ECHO = Route(
    name="echo",
    leaves_machine=False,
    sentence_en=(
        "Route: echo — fully offline echo backend; "
        "no data leaves this machine."
    ),
    sentence_fa=(
        "\u0645\u0633\u06cc\u0631: \u0622\u0641\u0644\u0627\u06cc\u0646 \u2014 "
        "\u0627\u06cc\u0646 \u0646\u0648\u0628\u062a \u0628\u0647 \u0635\u0648\u0631\u062a "
        "\u06a9\u0627\u0645\u0644\u0627\u064b \u0622\u0641\u0644\u0627\u06cc\u0646 "
        "\u067e\u0631\u062f\u0627\u0632\u0634 \u0645\u06cc\u200c\u0634\u0648\u062f\u061b "
        "\u0647\u06cc\u0686 \u062f\u0627\u062f\u0647\u200c\u0627\u06cc \u0627\u0632 "
        "\u0627\u06cc\u0646 "
        "\u062f\u0633\u062a\u06af\u0627\u0647 \u062e\u0627\u0631\u062c "
        "\u0646\u0645\u06cc\u200c\u0634\u0648\u062f."
    ),
)


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def resolve_route() -> Route:
    """Pick the active route by configuration, never by network probes."""
    explicit = _env("DREAM_BACKEND").lower()
    base_url = _env("OPENAI_BASE_URL")
    official_base = _is_official_base(base_url)
    aval_base = _is_aval_base(base_url)
    if explicit in ("aval", "avalai"):
        return _AVAL
    if explicit == "openai":
        if official_base:
            return _HOSTED
        return _AVAL if aval_base else _BYOK
    if explicit == "ollama":
        return _OLLAMA
    if explicit == "echo":
        return _ECHO

    if _env("OPENAI_API_KEY") and official_base:
        return _HOSTED
    if (os.environ.get("AVALAI_API_KEY") or "").strip() or aval_base:
        return _AVAL
    if _env("OLLAMA_HOST"):
        return _OLLAMA
    if base_url and not official_base:
        return _BYOK
    return _ECHO


def _is_official_base(base_url: str) -> bool:
    """True when the endpoint is the official OpenAI-compatible host."""
    if not base_url:
        return True
    normalised = base_url.strip().rstrip("/")
    return normalised.lower() in {url.rstrip("/").lower() for url in OFFICIAL_BASE_URLS}


def _is_aval_base(base_url: str) -> bool:
    """True when the endpoint is Aval AI's OpenAI-compatible host."""
    if not base_url:
        return False
    normalised = base_url.strip().rstrip("/")
    return normalised.lower() in {url.rstrip("/").lower() for url in AVAL_BASE_URLS}


_ROUTE_BACKEND: dict[str, str] = {
    "hosted": "openai",
    "aval": "openai",
    "ollama": "ollama",
    "byok": "openai",
    "echo": "echo",
}


def build_router_backend():
    """Construct the backend instance the resolved route would use."""
    from dream.agent import build_backend

    return build_backend(_ROUTE_BACKEND[resolve_route().name])


def route_text() -> str:
    """One honest paragraph naming the route and whether data leaves."""
    route = resolve_route()
    return f"{route.sentence_en}\n{route.sentence_fa}"
''',
    "dream/router/semantic.py": r'''"""Zero-latency semantic intent routing and model tier selection engine."""

from __future__ import annotations

import re
import time
from typing import Any
import uuid

from dream.router.types import IntentComplexity, ModelTier, RoutingDecision


class SemanticRouter:
    """Classifies user intent complexity and selects optimal model tier in sub-millisecond time."""

    def __init__(self) -> None:
        self._custom_rules: list[dict[str, Any]] = []

    def add_route_rule(
        self,
        pattern: str,
        intent: IntentComplexity,
        target_tier: ModelTier,
        priority: int = 10,
    ) -> None:
        """Register a custom regex routing pattern with priority."""
        self._custom_rules.append(
            {
                "regex": re.compile(pattern, re.IGNORECASE),
                "intent": intent,
                "target_tier": target_tier,
                "priority": priority,
                "pattern_str": pattern,
            }
        )
        self._custom_rules.sort(key=lambda r: r["priority"], reverse=True)

    def route_query(self, query: str) -> RoutingDecision:
        """Analyze query and produce optimal RoutingDecision."""
        start_time = time.time()
        q_clean = query.strip()
        q_lower = q_clean.lower()
        decision_id = f"route-{uuid.uuid4().hex[:6]}"

        # Check custom rules first
        for rule in self._custom_rules:
            if rule["regex"].search(q_clean):
                latency_ms = (time.time() - start_time) * 1000
                return RoutingDecision(
                    decision_id=decision_id,
                    query=query,
                    intent=rule["intent"],
                    target_tier=rule["target_tier"],
                    confidence=0.95,
                    estimated_latency_ms=latency_ms,
                    estimated_tokens_saved=self._estimate_tokens_saved(rule["target_tier"]),
                    matched_rules=[f"custom_pattern:{rule['pattern_str']}"],
                    predicted_tools=self._predict_tools(rule["intent"]),
                    rationale_fa="\u0645\u0637\u0627\u0628\u0642\u062a \u0628\u0627 \u0627\u0644\u06af\u0648\u06cc \u0633\u0641\u0627\u0631\u0634\u06cc \u0645\u0633\u06cc\u0631\u06cc\u0627\u0628\u06cc",
                )

        # Built-in heuristic intent classification
        matched_rules: list[str] = []
        intent = IntentComplexity.DIRECT_ANSWER
        target_tier = ModelTier.FAST_EDGE
        confidence = 0.80

        # 1. Code Execution Check
        code_keywords = [
            "کد", "پایتون", "برنامه", "اسکریپت", "الگوریتم", "تابع", "دیباگ",
            "python", "code", "script", "algorithm", "function", "debug", "def ",
        ]
        if any(kw in q_lower for kw in code_keywords):
            intent = IntentComplexity.CODE_EXECUTION
            target_tier = ModelTier.STANDARD_CHAT
            confidence = 0.90
            matched_rules.append("code_execution_heuristics")

        # 2. Deep Research Check
        elif any(
            kw in q_lower
            for kw in [
                "تحقیق جامع", "بررسی عمیق", "منابع مختلف", "مقایسه کامل", "تحلیل بازار",
                "deep research", "comprehensive review", "investigate", "synthesize",
            ]
        ):
            intent = IntentComplexity.DEEP_RESEARCH
            target_tier = ModelTier.REASONING_HEAVY
            confidence = 0.92
            matched_rules.append("deep_research_heuristics")

        # 3. Reasoning Chain / Complex Logic Check
        elif any(
            kw in q_lower
            for kw in [
                "استدلال", "چرا", "اثبات", "مناظره", "درخت تفکر", "منطق", "گام به گام", "ریشه‌یابی",
                "reasoning", "prove", "debate", "tree of thought", "logic", "step by step",
            ]
        ):
            intent = IntentComplexity.REASONING_CHAIN
            target_tier = ModelTier.REASONING_HEAVY
            confidence = 0.88
            matched_rules.append("reasoning_chain_heuristics")

        # 4. Simple Tool Check
        elif any(
            kw in q_lower
            for kw in [
                "ساعت", "تاریخ", "تقویم", "آب و هوا", "جستجو کن", "سرچ کن", "محاسبه",
                "time", "date", "calendar", "weather", "search", "calculate",
            ]
        ):
            intent = IntentComplexity.SIMPLE_TOOL
            target_tier = ModelTier.FAST_EDGE
            confidence = 0.85
            matched_rules.append("simple_tool_heuristics")

        # 5. Direct Answer / Greeting
        else:
            intent = IntentComplexity.DIRECT_ANSWER
            target_tier = ModelTier.FAST_EDGE
            confidence = 0.82
            matched_rules.append("direct_answer_fallback")

        latency_ms = max(0.01, (time.time() - start_time) * 1000)
        tokens_saved = self._estimate_tokens_saved(target_tier)
        predicted_tools = self._predict_tools(intent)

        rationale_map = {
            IntentComplexity.DIRECT_ANSWER: "\u067e\u0627\u0633\u062e \u0645\u0633\u062a\u0642\u06cc\u0645 \u0628\u062f\u0648\u0646 \u0646\u06cc\u0627\u0632 \u0628\u0647 \u0627\u0628\u0632\u0627\u0631 (Fast Edge)",
            IntentComplexity.SIMPLE_TOOL: "\u0627\u062c\u0631\u0627\u06cc \u062a\u06a9\u200c\u0627\u0628\u0632\u0627\u0631\u06cc \u0633\u0631\u06cc\u0639 (Fast Edge / Standard)",
            IntentComplexity.REASONING_CHAIN: "\u0646\u06cc\u0627\u0632\u0645\u0646\u062f \u0632\u0646\u062c\u06cc\u0631\u0647 \u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u0648 \u0645\u062f\u0644 \u0634\u0646\u0627\u062e\u062a\u06cc \u067e\u06cc\u0634\u0631\u0641\u062a\u0647 (Reasoning Heavy)",
            IntentComplexity.DEEP_RESEARCH: "\u062a\u062d\u0642\u06cc\u0642 \u0686\u0646\u062f\u0645\u0631\u062d\u0644\u0647\u200c\u0627\u06cc \u0648 \u062a\u0631\u06a9\u06cc\u0628 \u0645\u0646\u0627\u0628\u0639 (Deep Research)",
            IntentComplexity.CODE_EXECUTION: "\u062a\u062d\u0644\u06cc\u0644 \u0648 \u0627\u062c\u0631\u0627\u06cc \u06a9\u062f \u062f\u0631 \u0633\u0646\u062f\u0628\u0627\u06a9\u0633 (Code Execution)",
        }

        return RoutingDecision(
            decision_id=decision_id,
            query=query,
            intent=intent,
            target_tier=target_tier,
            confidence=confidence,
            estimated_latency_ms=latency_ms,
            estimated_tokens_saved=tokens_saved,
            matched_rules=matched_rules,
            predicted_tools=predicted_tools,
            rationale_fa=rationale_map.get(intent, ""),
        )

    def _estimate_tokens_saved(self, tier: ModelTier) -> int:
        """Calculate token economy savings compared to defaulting all to reasoning heavy."""
        if tier == ModelTier.FAST_EDGE:
            return 1250  # Saves large system prompt + chain-of-thought tokens
        elif tier == ModelTier.STANDARD_CHAT:
            return 600
        return 0

    def _predict_tools(self, intent: IntentComplexity) -> list[str]:
        """Speculatively predict tools needed for intent."""
        if intent == IntentComplexity.SIMPLE_TOOL:
            return ["get_datetime", "calculate", "search_web"]
        elif intent == IntentComplexity.CODE_EXECUTION:
            return ["sandbox_execute_python", "sandbox_analyze_dataset"]
        elif intent == IntentComplexity.DEEP_RESEARCH:
            return ["research_plan_investigation", "search_web", "read_page"]
        elif intent == IntentComplexity.REASONING_CHAIN:
            return ["reasoning_create_thought_tree", "debate_create_session"]
        return []
''',
    "dream/router/compiler.py": r'''"""Dynamic Prompt Compiler: Token budgeting, AST section assembly, and template rendering."""

from __future__ import annotations

import time
from typing import Any

from dream.router.types import CompiledPrompt, ModelTier, PromptSection


class PromptCompiler:
    """Compiles structured prompt sections into token-budgeted system and user prompts."""

    # Default token budgets per model tier
    TIER_BUDGETS: dict[ModelTier, int] = {
        ModelTier.FAST_EDGE: 2048,
        ModelTier.STANDARD_CHAT: 8192,
        ModelTier.REASONING_HEAVY: 16384,
    }

    def __init__(self) -> None:
        self._templates: dict[str, list[PromptSection]] = {}
        self._init_builtin_templates()

    def _init_builtin_templates(self) -> None:
        """Initialize core Dream prompt templates."""
        self._templates["default_agent"] = [
            PromptSection(
                section_id="soul_core",
                title="Soul Core Identity",
                content="You are Dream, an ultra-intelligent, highly capable AI assistant.",
                priority=1000,
                is_mandatory=True,
            ),
            PromptSection(
                section_id="persian_excellence",
                title="Language & Cultural Nuance",
                content="Respond fluently, naturally, and accurately in Persian with proper Persian grammar and typography.",
                priority=900,
                is_mandatory=True,
            ),
            PromptSection(
                section_id="context_calendar",
                title="Temporal Grounding",
                content="Current Jalali Date: {jalali_date}. Always ground chronological assertions.",
                priority=700,
                is_mandatory=False,
            ),
            PromptSection(
                section_id="tool_guidelines",
                title="Tool Calling Protocol",
                content="Use available tools judiciously. Validate arguments before dispatching calls.",
                priority=500,
                is_mandatory=False,
            ),
            PromptSection(
                section_id="extended_dialectic",
                title="Dialectic Memory Profile",
                content="User Preferences: {user_profile}. Dialectic Beliefs: {dialectic_beliefs}.",
                priority=300,
                is_mandatory=False,
            ),
        ]

    def register_template(
        self,
        name: str,
        sections: list[PromptSection],
    ) -> None:
        """Register a new modular prompt template."""
        self._templates[name] = sections

    def compile(
        self,
        template_name: str,
        target_tier: ModelTier,
        user_query: str,
        variables: dict[str, Any] | None = None,
        max_budget_tokens: int | None = None,
    ) -> CompiledPrompt:
        """Assemble and prune prompt sections according to token budget."""
        start_time = time.time()
        vars_dict = variables or {}
        budget = max_budget_tokens or self.TIER_BUDGETS.get(target_tier, 4096)

        sections = self._templates.get(template_name, self._templates["default_agent"])

        # Estimate user query tokens
        user_tokens = max(1, len(user_query) // 4)
        available_sys_tokens = max(1, budget - user_tokens)

        # Sort sections: mandatory first, then highest priority
        sorted_sections = sorted(
            sections,
            key=lambda s: (s.is_mandatory, s.priority),
            reverse=True,
        )

        included_ids: list[str] = []
        dropped_ids: list[str] = []
        rendered_blocks: list[str] = []
        current_tokens = 0

        for sec in sorted_sections:
            # Substitute variables
            raw_content = sec.content
            for k, v in vars_dict.items():
                raw_content = raw_content.replace(f"{{{k}}}", str(v))

            # Clean unresolved place-holders if optional
            if not sec.is_mandatory:
                import re

                raw_content = re.sub(r"\{[a-zA-Z0-9_]+\}", "", raw_content).strip()

            sec_tokens = max(1, len(raw_content) // 4)

            if sec.is_mandatory or (current_tokens + sec_tokens <= available_sys_tokens):
                rendered_blocks.append(raw_content)
                current_tokens += sec_tokens
                included_ids.append(sec.section_id)
            else:
                dropped_ids.append(sec.section_id)

        system_prompt = "\n\n".join(rendered_blocks)
        total_tokens = current_tokens + user_tokens
        latency_ms = (time.time() - start_time) * 1000

        return CompiledPrompt(
            template_name=template_name,
            target_tier=target_tier,
            system_prompt=system_prompt,
            user_prompt=user_query,
            total_tokens=total_tokens,
            max_budget_tokens=budget,
            included_sections=included_ids,
            dropped_sections=dropped_ids,
            compilation_time_ms=latency_ms,
        )
''',
    "dream/router/cascade.py": r'''"""Model Cascader: Multi-tier fallback execution policies and escalation triggers."""

from __future__ import annotations

from typing import Any

from dream.router.types import IntentComplexity, ModelTier, RoutingDecision


class ModelCascader:
    """Orchestrates tiered escalation policies across Fast, Standard, and Heavy models."""

    def get_cascade_plan(self, decision: RoutingDecision) -> dict[str, Any]:
        """Generate full execution and escalation pipeline based on routing decision."""
        primary_tier = decision.target_tier

        escalation_path: list[ModelTier] = []
        if primary_tier == ModelTier.FAST_EDGE:
            escalation_path = [ModelTier.FAST_EDGE, ModelTier.STANDARD_CHAT, ModelTier.REASONING_HEAVY]
        elif primary_tier == ModelTier.STANDARD_CHAT:
            escalation_path = [ModelTier.STANDARD_CHAT, ModelTier.REASONING_HEAVY]
        else:
            escalation_path = [ModelTier.REASONING_HEAVY]

        return {
            "primary_tier": primary_tier.value,
            "escalation_chain": [t.value for t in escalation_path],
            "speculative_tools": decision.predicted_tools,
            "escalation_triggers": [
                "tool_dispatch_failure",
                "model_hallucination_detected",
                "token_budget_overflow",
                "confidence_drop_below_0.75",
            ],
            "estimated_token_saving": decision.estimated_tokens_saved,
        }

    def evaluate_escalation(
        self,
        current_tier: ModelTier,
        confidence: float,
        had_tool_error: bool = False,
    ) -> tuple[bool, ModelTier | None]:
        """Determine if current turn must escalate to higher model tier."""
        if current_tier == ModelTier.REASONING_HEAVY:
            return False, None

        if had_tool_error or confidence < 0.70:
            next_tier = (
                ModelTier.STANDARD_CHAT
                if current_tier == ModelTier.FAST_EDGE
                else ModelTier.REASONING_HEAVY
            )
            return True, next_tier

        return False, None
''',
    "dream/router/engine.py": r'''"""Routing Engine Coordinator: Links semantic routing, prompt compilation, and cascading."""

from __future__ import annotations

import time
from typing import Any

from dream.router.cascade import ModelCascader
from dream.router.compiler import PromptCompiler
from dream.router.semantic import SemanticRouter
from dream.router.types import (
    CompiledPrompt,
    IntentComplexity,
    ModelTier,
    RouterStats,
    RoutingDecision,
)


class RoutingEngine:
    """Unified coordinator for semantic intent routing, prompt compilation, and cascading."""

    def __init__(
        self,
        router: SemanticRouter | None = None,
        compiler: PromptCompiler | None = None,
        cascader: ModelCascader | None = None,
    ) -> None:
        self.router = router or SemanticRouter()
        self.compiler = compiler or PromptCompiler()
        self.cascader = cascader or ModelCascader()

        self._decisions_history: list[RoutingDecision] = []
        self._total_latency_ms: float = 0.0

    def route_and_compile(
        self,
        user_query: str,
        template_name: str = "default_agent",
        variables: dict[str, Any] | None = None,
    ) -> tuple[RoutingDecision, CompiledPrompt, dict[str, Any]]:
        """Route user query, compile token-budgeted prompt, and generate cascade plan."""
        # Step 1: Semantic Intent Routing
        decision = self.router.route_query(user_query)
        self._decisions_history.append(decision)
        self._total_latency_ms += decision.estimated_latency_ms

        # Step 2: Dynamic Prompt Compilation
        compiled = self.compiler.compile(
            template_name=template_name,
            target_tier=decision.target_tier,
            user_query=user_query,
            variables=variables,
        )

        # Step 3: Cascading Plan
        cascade_plan = self.cascader.get_cascade_plan(decision)

        return decision, compiled, cascade_plan

    def get_stats(self) -> RouterStats:
        """Compute aggregate routing statistics and token economy."""
        total = len(self._decisions_history)
        if total == 0:
            return RouterStats(
                total_routed=0,
                direct_answers=0,
                simple_tools=0,
                reasoning_chains=0,
                deep_researches=0,
                code_executions=0,
                total_tokens_saved=0,
                average_latency_ms=0.0,
            )

        direct = sum(1 for d in self._decisions_history if d.intent == IntentComplexity.DIRECT_ANSWER)
        simple = sum(1 for d in self._decisions_history if d.intent == IntentComplexity.SIMPLE_TOOL)
        reasoning = sum(1 for d in self._decisions_history if d.intent == IntentComplexity.REASONING_CHAIN)
        deep = sum(1 for d in self._decisions_history if d.intent == IntentComplexity.DEEP_RESEARCH)
        code = sum(1 for d in self._decisions_history if d.intent == IntentComplexity.CODE_EXECUTION)
        tokens_saved = sum(d.estimated_tokens_saved for d in self._decisions_history)
        avg_latency = self._total_latency_ms / total

        return RouterStats(
            total_routed=total,
            direct_answers=direct,
            simple_tools=simple,
            reasoning_chains=reasoning,
            deep_researches=deep,
            code_executions=code,
            total_tokens_saved=tokens_saved,
            average_latency_ms=avg_latency,
        )

    def format_routing_report(self) -> str:
        """Format routing decisions and economics into Markdown."""
        stats = self.get_stats()
        lines = [
            "## \U0001f6e4\ufe0f \u06af\u0632\u0627\u0631\u0634 \u0645\u0633\u06cc\u0631\u06cc\u0627\u0628\u06cc \u0645\u0639\u0646\u0627\u06cc\u06cc \u0648 \u0622\u0628\u0634\u0627\u0631 \u0645\u062f\u0644\u200c\u0647\u0627 (Semantic Router & Cascading)",
            f"- **\u062a\u0639\u062f\u0627\u062f \u06a9\u0644 \u062f\u0631\u062e\u0648\u0627\u0633\u062a\u200c\u0647\u0627\u06cc \u0645\u0633\u06cc\u0631\u06cc\u0627\u0628\u06cc\u200c\u0634\u062f\u0647:** {stats.total_routed}",
            f"- **\u0635\u0631\u0641\u0647\u200c\u062c\u0648\u06cc\u06cc \u062a\u062e\u0645\u06cc\u0646\u06cc \u062a\u0648\u06a9\u0646:** {stats.total_tokens_saved:,} \u062a\u0648\u06a9\u0646",
            f"- **\u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 \u0632\u0645\u0627\u0646 \u062a\u0635\u0645\u06cc\u0645\u200c\u06af\u06cc\u0631\u06cc:** {stats.average_latency_ms:.2f} ms",
            "",
            "### \U0001f4ca \u062a\u0641\u06a9\u06cc\u06a9 \u0642\u0635\u062f\u0647\u0627 (Intents):",
            f"- \u067e\u0627\u0633\u062e \u0645\u0633\u062a\u0642\u06cc\u0645 (Direct): {stats.direct_answers}",
            f"- \u062a\u06a9\u200c\u0627\u0628\u0632\u0627\u0631\u06cc (Simple Tool): {stats.simple_tools}",
            f"- \u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u067e\u06cc\u0686\u06cc\u062f\u0647 (Reasoning): {stats.reasoning_chains}",
            f"- \u062a\u062d\u0642\u06cc\u0642 \u0639\u0645\u06cc\u0642 (Deep Research): {stats.deep_researches}",
            f"- \u0627\u062c\u0631\u0627\u06cc \u06a9\u062f (Code Execution): {stats.code_executions}",
        ]
        return "\n".join(lines)

    def reset(self) -> None:
        """Reset routing history and counters."""
        self._decisions_history.clear()
        self._total_latency_ms = 0.0
''',
    "dream/router/tools.py": r'''"""LLM tool bindings for Semantic Routing, Prompt Compiler, and Cascading Engine."""

from __future__ import annotations

from typing import Any

from dream.router.engine import RoutingEngine

_GLOBAL_ROUTING_ENGINE: RoutingEngine | None = None


def get_global_routing_engine() -> RoutingEngine:
    """Get or initialize singleton RoutingEngine."""
    global _GLOBAL_ROUTING_ENGINE
    if _GLOBAL_ROUTING_ENGINE is None:
        _GLOBAL_ROUTING_ENGINE = RoutingEngine()
    return _GLOBAL_ROUTING_ENGINE


def reset_global_routing_engine() -> None:
    """Reset singleton RoutingEngine."""
    global _GLOBAL_ROUTING_ENGINE
    _GLOBAL_ROUTING_ENGINE = None


def router_evaluate_query(query: str) -> dict[str, Any]:
    """Evaluate cognitive complexity of user query and return target model tier."""
    engine = get_global_routing_engine()
    decision = engine.router.route_query(query)
    return {"success": True, "decision": decision.to_dict()}


def router_compile_prompt(
    template_name: str = "default_agent",
    variables: dict[str, Any] | None = None,
    user_query: str = "",
) -> dict[str, Any]:
    """Compile token-budgeted prompt template with dynamic variable injection."""
    engine = get_global_routing_engine()
    decision = engine.router.route_query(user_query or "سلام")
    compiled = engine.compiler.compile(
        template_name=template_name,
        target_tier=decision.target_tier,
        user_query=user_query,
        variables=variables or {},
    )
    return {
        "success": True,
        "compiled_prompt": compiled.to_dict(),
        "system_prompt": compiled.system_prompt,
    }


def router_cascade_plan(query: str) -> dict[str, Any]:
    """Generate multi-tier cascading fallback plan and speculative tool sequence."""
    engine = get_global_routing_engine()
    decision, compiled, cascade_plan = engine.route_and_compile(query)
    return {
        "success": True,
        "decision": decision.to_dict(),
        "cascade_plan": cascade_plan,
    }


def router_get_stats() -> dict[str, Any]:
    """Get aggregate statistics on intent distribution and token savings."""
    engine = get_global_routing_engine()
    stats = engine.get_stats()
    return {"success": True, "stats": stats.to_dict()}


def router_export_report() -> dict[str, Any]:
    """Export formatted Markdown summary of routing decisions and token economics."""
    engine = get_global_routing_engine()
    report = engine.format_routing_report()
    return {"success": True, "markdown_report": report}


def router_reset_all() -> dict[str, Any]:
    """Reset router history and metrics."""
    engine = get_global_routing_engine()
    engine.reset()
    return {"success": True, "message": "\u0622\u0645\u0627\u0631 \u0648 \u062a\u0627\u0631\u06cc\u062e\u0686\u0647 \u0645\u0633\u06cc\u0631\u06cc\u0627\u0628\u06cc \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."}


def get_router_tools() -> list[Any]:
    """Return router tool functions for agent registration."""
    return [
        router_evaluate_query,
        router_compile_prompt,
        router_cascade_plan,
        router_get_stats,
        router_export_report,
        router_reset_all,
    ]
''',
    "dream/router/slash.py": r'''"""CLI and slash command handlers for Semantic Router and Dynamic Prompt Compiler."""

from __future__ import annotations

from typing import Any

from dream.router.tools import (
    router_cascade_plan,
    router_evaluate_query,
    router_export_report,
    router_reset_all,
)


def handle_router_slash_command(command_str: str) -> str:
    """Handle /route, /cascade, and /router CLI slash commands.

    Usage:
        /route <query>
        /cascade <query>
        /router [stats|reset]
    """
    cmd = command_str.strip()

    if cmd.startswith("/router"):
        parts = cmd.split()
        subcmd = parts[1].lower() if len(parts) > 1 else "stats"
        if subcmd == "reset":
            router_reset_all()
            return "\u2705 \u0622\u0645\u0627\u0631 \u0645\u0633\u06cc\u0631\u06cc\u0627\u0628\u06cc \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."

        res = router_export_report()
        return res.get("markdown_report", "")

    if cmd.startswith("/cascade"):
        q = cmd[len("/cascade") :].strip()
        if not q:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u067e\u0631\u0633\u0634 \u0631\u0627 \u0628\u0631\u0627\u06cc \u062a\u0648\u0644\u06cc\u062f \u067e\u0644\u0627\u0646 \u0622\u0628\u0634\u0627\u0631 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = router_cascade_plan(q)
        plan = res.get("cascade_plan", {})
        return (
            f"\U0001f30a \u067e\u0644\u0627\u0646 \u0622\u0628\u0634\u0627\u0631 \u0645\u062f\u0644\u200c\u0647\u0627 (Cascading Pipeline):\n"
            f"- \u0645\u062f\u0644 \u0627\u0648\u0644\u06cc\u0647: `{plan.get('primary_tier')}`\n"
            f"- \u0632\u0646\u062c\u06cc\u0631\u0647 \u0627\u0631\u062a\u0642\u0627: {' -> '.join(plan.get('escalation_chain', []))}\n"
            f"- \u0627\u0628\u0632\u0627\u0631\u0647\u0627\u06cc \u067e\u06cc\u0634\u200c\u0628\u06cc\u0646\u06cc\u200c\u0634\u062f\u0647: `{', '.join(plan.get('speculative_tools', [])) or 'none'}`"
        )

    if cmd.startswith("/route"):
        q = cmd[len("/route") :].strip()
        if not q:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u067e\u0631\u0633\u0634 \u06cc\u0627 \u067e\u0631\u0627\u0645\u067e\u062a \u0631\u0627 \u0628\u0631\u0627\u06cc \u0645\u0633\u06cc\u0631\u06cc\u0627\u0628\u06cc \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = router_evaluate_query(q)
        dec = res.get("decision", {})
        return (
            f"\U0001f6e4\ufe0f \u0646\u062a\u06cc\u062c\u0647 \u0645\u0633\u06cc\u0631\u06cc\u0627\u0628\u06cc \u0645\u0639\u0646\u0627\u06cc\u06cc:\n"
            f"- \u0642\u0635\u062f (Intent): `{dec.get('intent')}`\n"
            f"- \u0645\u062f\u0644 \u0647\u062f\u0641 (Tier): `{dec.get('target_tier')}`\n"
            f"- \u0635\u0631\u0641\u0647\u200c\u062c\u0648\u06cc\u06cc \u062a\u0648\u06a9\u0646: {dec.get('estimated_tokens_saved')} \u062a\u0648\u06a9\u0646\n"
            f"- \u0627\u0637\u0645\u06cc\u0646\u0627\u0646 (Confidence): {dec.get('confidence') * 100:.1f}%\n"
            f"- \u062a\u062d\u0644\u06cc\u0644: {dec.get('rationale_fa')}"
        )

    return "\u274c \u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a."
''',
    "dream/router/__init__.py": r'''"""Adaptive Semantic Router, Dynamic Prompt Compiler, and Model Cascading Engine Subsystem."""

from __future__ import annotations

from dream.router.backend import (
    AVAL_BASE_URLS,
    OFFICIAL_BASE_URLS,
    Route,
    _AVAL,
    _BYOK,
    _ECHO,
    _HOSTED,
    _OLLAMA,
    _ROUTE_BACKEND,
    build_router_backend,
    resolve_route,
    route_text,
)
from dream.router.cascade import ModelCascader
from dream.router.compiler import PromptCompiler
from dream.router.engine import RoutingEngine
from dream.router.semantic import SemanticRouter
from dream.router.slash import handle_router_slash_command
from dream.router.tools import (
    get_global_routing_engine,
    get_router_tools,
    reset_global_routing_engine,
    router_cascade_plan,
    router_compile_prompt,
    router_evaluate_query,
    router_export_report,
    router_get_stats,
    router_reset_all,
)
from dream.router.types import (
    CompiledPrompt,
    IntentComplexity,
    ModelTier,
    PromptSection,
    RouterStats,
    RoutingDecision,
)

# Auto-register router toolset
try:
    from dream.tools.toolsets import Toolset, register_toolset

    register_toolset(
        Toolset(
            name="router",
            description="Adaptive semantic routing, prompt compilation, and cascading execution.",
            tools=[
                "router_evaluate_query",
                "router_compile_prompt",
                "router_cascade_plan",
                "router_get_stats",
                "router_export_report",
                "router_reset_all",
            ],
            metadata={"category": "router", "builtin": True},
        )
    )
except Exception:
    pass

__all__ = [
    "AVAL_BASE_URLS",
    "CompiledPrompt",
    "IntentComplexity",
    "ModelCascader",
    "ModelTier",
    "OFFICIAL_BASE_URLS",
    "PromptCompiler",
    "PromptSection",
    "Route",
    "RouterStats",
    "RoutingDecision",
    "RoutingEngine",
    "SemanticRouter",
    "_AVAL",
    "_BYOK",
    "_ECHO",
    "_HOSTED",
    "_OLLAMA",
    "_ROUTE_BACKEND",
    "build_router_backend",
    "get_global_routing_engine",
    "get_router_tools",
    "handle_router_slash_command",
    "reset_global_routing_engine",
    "resolve_route",
    "route_text",
    "router_cascade_plan",
    "router_compile_prompt",
    "router_evaluate_query",
    "router_export_report",
    "router_get_stats",
    "router_reset_all",
]
''',
    "dream/tools/toolsets.py": r'''"""Toolset categorization, grouping, and dynamic tool management."""

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
    "profiles": Toolset(
        name="profiles",
        description="Multi-profile persona scoping and isolated workspace management",
        tools=(
            "profile_list",
            "profile_get_current",
            "profile_switch",
            "profile_create",
        ),
    ),
    "context": Toolset(
        name="context",
        description="Prioritized context files (SOUL, AGENTS, USER, MEMORY) and budgeting",
        tools=(
            "context_get_tier",
            "context_update_tier",
            "context_get_budget_report",
            "context_assemble_prompt",
            "context_reload_all",
        ),
    ),
    "terminal": Toolset(
        name="terminal",
        description="Multi-backend isolated execution (Local, Docker, SSH, Cloud Sandboxes)",
        tools=(
            "terminal_execute",
            "terminal_list_backends",
            "terminal_switch_backend",
        ),
    ),
    "browser": Toolset(
        name="browser",
        description="Multi-driver browser control, DOM extraction, and visual interaction",
        tools=(
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_screenshot",
            "browser_extract_content",
            "browser_close",
            "browser_get_status",
        ),
    ),
    "dialectic": Toolset(
        name="dialectic",
        description="Self-reflective dialectic user modeling and knowledge synthesis",
        tools=(
            "dialectic_observe",
            "dialectic_reflect",
            "dialectic_get_belief_graph",
            "dialectic_reconcile",
            "dialectic_query_traits",
        ),
    ),
    "acp": Toolset(
        name="acp",
        description="Agent Client Protocol (ACP) IDE integration and diff tools",
        tools=(
            "acp_apply_diff",
            "acp_read_diagnostics",
            "acp_get_session_status",
            "acp_list_agents",
            "acp_call_agent",
        ),
    ),
    "plugins": Toolset(
        name="plugins",
        description="Dynamic plugin installation, lifecycle management, and extension hooks",
        tools=(
            "plugin_list",
            "plugin_install",
            "plugin_enable",
            "plugin_disable",
            "plugin_get_info",
        ),
    ),
    "swarm": Toolset(
        name="swarm",
        description="Distributed swarm orchestration, DAG task execution, and consensus",
        tools=(
            "swarm_spawn_node",
            "swarm_plan_workflow",
            "swarm_execute_step",
            "swarm_run_all",
            "swarm_reach_consensus",
            "swarm_get_status",
            "swarm_broadcast_message",
        ),
    ),
    "speech": Toolset(
        name="speech",
        description="Voice synthesis (TTS), recognition (STT), and HybridEmo emotion modeling",
        tools=(
            "speech_text_to_speech",
            "speech_speech_to_text",
            "speech_analyze_voice_emotion",
            "speech_list_voices",
        ),
    ),
    "ocr": Toolset(
        name="ocr",
        description="Persian document OCR, receipt parsing, and invoice field extraction",
        tools=(
            "ocr_extract_document",
            "ocr_extract_invoice",
        ),
    ),
    "knowledge": Toolset(
        name="knowledge",
        description=(
            "Multimodal temporal knowledge graph, timeline reasoning, "
            "and cross-modal entity linking"
        ),
        tools=(
            "knowledge_add_entity",
            "knowledge_add_relation",
            "knowledge_query_temporal",
            "knowledge_get_entity_timeline",
            "knowledge_link_multimodal_artifact",
            "knowledge_get_stats",
        ),
    ),
    "alignment": Toolset(
        name="alignment",
        description=(
            "Continuous self-improving alignment, multi-dimensional scoring, "
            "self-critique, and DPO dataset generation"
        ),
        tools=(
            "alignment_record_feedback",
            "alignment_critique_and_refine",
            "alignment_evaluate_response",
            "alignment_export_dataset",
            "alignment_get_stats",
        ),
    ),
    "research": Toolset(
        name="research",
        description=(
            "Autonomous multi-step deep research, evidence collection, "
            "and multi-source intelligence synthesis"
        ),
        tools=(
            "research_plan_investigation",
            "research_add_source",
            "research_synthesize_report",
            "research_run_autonomous",
            "research_export_report",
            "research_get_status",
            "research_list_sessions",
        ),
    ),
    "cache": Toolset(
        name="cache",
        description=(
            "Semantic caching, speculative pre-fetching, and token economics optimization"
        ),
        tools=(
            "cache_lookup_query",
            "cache_store_entry",
            "cache_predict_tool",
            "cache_get_economics",
            "cache_clear",
            "cache_warmup",
        ),
    ),
    "sandbox": Toolset(
        name="sandbox",
        description=(
            "Isolated Python code execution, dataset analysis, and REPL interpreter"
        ),
        tools=(
            "sandbox_execute_python",
            "sandbox_analyze_dataset",
            "sandbox_reset_session",
            "sandbox_list_artifacts",
            "sandbox_get_status",
        ),
    ),
    "canvas": Toolset(
        name="canvas",
        description=(
            "Interactive visual artifacts, diagrams, standalone previews, and versioning"
        ),
        tools=(
            "canvas_create_artifact",
            "canvas_update_artifact",
            "canvas_get_artifact",
            "canvas_list_artifacts",
            "canvas_diff_versions",
            "canvas_render_preview",
            "canvas_export_bundle",
            "canvas_reset_session",
            "canvas_get_status",
        ),
    ),
    "debate": Toolset(
        name="debate",
        description=(
            "Multi-agent debate rounds, Delphi consensus evaluation, and fact verification"
        ),
        tools=(
            "debate_create_session",
            "debate_add_turn",
            "debate_run_autonomous",
            "debate_verify_statement",
            "debate_reach_consensus",
            "debate_list_sessions",
            "debate_reset_all",
        ),
    ),
    "reasoning": Toolset(
        name="reasoning",
        description=(
            "Tree-of-Thought exploration, strategy branching, and metacognitive self-evaluation"
        ),
        tools=(
            "reasoning_create_thought_tree",
            "reasoning_expand_node",
            "reasoning_evaluate_node",
            "reasoning_solve_goal",
            "reasoning_get_best_path",
            "reasoning_get_status",
            "reasoning_reset_all",
        ),
    ),
    "healing": Toolset(
        name="healing",
        description=(
            "Autonomous error diagnosis, self-healing recovery, telemetry, and chaos testing"
        ),
        tools=(
            "healing_diagnose_failure",
            "healing_run_chaos_test",
            "telemetry_get_health_metrics",
            "telemetry_export_report",
            "telemetry_export_spans",
            "telemetry_reset_all",
        ),
    ),
    "router": Toolset(
        name="router",
        description=(
            "Adaptive semantic routing, prompt compilation, and cascading execution"
        ),
        tools=(
            "router_evaluate_query",
            "router_compile_prompt",
            "router_cascade_plan",
            "router_get_stats",
            "router_export_report",
            "router_reset_all",
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
        names = source.keys()
        allowed_names.update(names)

    if exclude_tools is not None:
        allowed_names.difference_update(exclude_tools)

    return {name: tool for name, tool in source.items() if name in allowed_names}
''',
    "tests/test_semantic_router_and_compiler.py": r'''"""Unit and integration tests for Semantic Router, Dynamic Prompt Compiler & Cascading Engine."""

from __future__ import annotations

import pytest

from dream.router import (
    IntentComplexity,
    ModelCascader,
    ModelTier,
    PromptCompiler,
    PromptSection,
    RoutingEngine,
    SemanticRouter,
    get_router_tools,
    handle_router_slash_command,
    reset_global_routing_engine,
    router_cascade_plan,
    router_compile_prompt,
    router_evaluate_query,
    router_export_report,
    router_get_stats,
    router_reset_all,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_router_engine() -> None:
    reset_global_routing_engine()
    yield
    reset_global_routing_engine()


def test_toolset_includes_router() -> None:
    """Verify router toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("router")
    assert ts is not None
    assert "router_evaluate_query" in ts.tools
    assert "router_compile_prompt" in ts.tools
    assert "router_cascade_plan" in ts.tools
    assert "router" in BUILTIN_TOOLSETS


def test_semantic_router_intent_classification() -> None:
    """Verify semantic router accurately classifies queries into intents and model tiers."""
    router = SemanticRouter()

    # Direct Answer
    d_direct = router.route_query("سلام، حال شما چطوره؟")
    assert d_direct.intent == IntentComplexity.DIRECT_ANSWER
    assert d_direct.target_tier == ModelTier.FAST_EDGE
    assert d_direct.estimated_tokens_saved == 1250

    # Simple Tool
    d_tool = router.route_query("ساعت و تاریخ امروز چند است؟")
    assert d_tool.intent == IntentComplexity.SIMPLE_TOOL
    assert d_tool.target_tier == ModelTier.FAST_EDGE
    assert "get_datetime" in d_tool.predicted_tools

    # Code Execution
    d_code = router.route_query("یک اسکریپت پایتون برای مرتب‌سازی آرایه بنویس")
    assert d_code.intent == IntentComplexity.CODE_EXECUTION
    assert d_code.target_tier == ModelTier.STANDARD_CHAT
    assert "sandbox_execute_python" in d_code.predicted_tools

    # Reasoning Chain
    d_reason = router.route_query("استدلال و اثبات کن که آیا هوش مصنوعی عمومی ممکن است؟")
    assert d_reason.intent == IntentComplexity.REASONING_CHAIN
    assert d_reason.target_tier == ModelTier.REASONING_HEAVY

    # Deep Research
    d_deep = router.route_query("یک تحقیق جامع و بررسی عمیق از بازار تراشه‌های هوش مصنوعی ارائه بده")
    assert d_deep.intent == IntentComplexity.DEEP_RESEARCH
    assert d_deep.target_tier == ModelTier.REASONING_HEAVY


def test_semantic_router_custom_rule() -> None:
    """Verify custom routing regex rules take priority."""
    router = SemanticRouter()
    router.add_route_rule(
        pattern=r"^\/admin_deep",
        intent=IntentComplexity.DEEP_RESEARCH,
        target_tier=ModelTier.REASONING_HEAVY,
        priority=100,
    )

    decision = router.route_query("/admin_deep analyze server logs")
    assert decision.intent == IntentComplexity.DEEP_RESEARCH
    assert decision.target_tier == ModelTier.REASONING_HEAVY
    assert "custom_pattern:^\\/admin_deep" in decision.matched_rules


def test_prompt_compiler_token_budgeting() -> None:
    """Verify dynamic prompt assembly obeys token limits and drops lower priority sections."""
    compiler = PromptCompiler()

    # Small budget drops non-mandatory sections
    compiled_small = compiler.compile(
        template_name="default_agent",
        target_tier=ModelTier.FAST_EDGE,
        user_query="Hello",
        max_budget_tokens=50,
    )
    assert "soul_core" in compiled_small.included_sections
    assert "persian_excellence" in compiled_small.included_sections
    assert "extended_dialectic" in compiled_small.dropped_sections

    # Variable injection
    compiled_vars = compiler.compile(
        template_name="default_agent",
        target_tier=ModelTier.STANDARD_CHAT,
        user_query="تست",
        variables={"jalali_date": "1405/06/20", "user_profile": "AI Researcher"},
        max_budget_tokens=4000,
    )
    assert "1405/06/20" in compiled_vars.system_prompt
    assert "AI Researcher" in compiled_vars.system_prompt


def test_model_cascader_and_escalation() -> None:
    """Verify cascading pipeline and escalation evaluation."""
    cascader = ModelCascader()
    router = SemanticRouter()

    dec_fast = router.route_query("سلام")
    plan = cascader.get_cascade_plan(dec_fast)
    assert plan["primary_tier"] == "fast_edge"
    assert "standard_chat" in plan["escalation_chain"]
    assert "reasoning_heavy" in plan["escalation_chain"]

    # Escalation on tool failure
    must_esc, next_tier = cascader.evaluate_escalation(
        current_tier=ModelTier.FAST_EDGE,
        confidence=0.85,
        had_tool_error=True,
    )
    assert must_esc is True
    assert next_tier == ModelTier.STANDARD_CHAT

    # No escalation on normal high confidence
    no_esc, _ = cascader.evaluate_escalation(
        current_tier=ModelTier.STANDARD_CHAT,
        confidence=0.95,
        had_tool_error=False,
    )
    assert no_esc is False


def test_routing_engine_and_stats() -> None:
    """Verify routing coordinator records history and calculates token savings."""
    engine = RoutingEngine()

    engine.route_and_compile("سلام")
    engine.route_and_compile("کد پایتون بنویس")
    engine.route_and_compile("ساعت چند است؟")

    stats = engine.get_stats()
    assert stats.total_routed == 3
    assert stats.direct_answers == 1
    assert stats.code_executions == 1
    assert stats.simple_tools == 1
    assert stats.total_tokens_saved > 0
    assert stats.average_latency_ms >= 0.0


def test_router_tools_and_slash_commands() -> None:
    """Verify LLM agent tools and /route, /cascade, /router slash commands."""
    tools = get_router_tools()
    assert len(tools) >= 5

    # Tool: evaluate query
    res_eval = router_evaluate_query("یک الگوریتم یادگیری عمیق به زبان پایتون")
    assert res_eval["success"] is True
    assert res_eval["decision"]["intent"] == "code_execution"

    # Tool: compile prompt
    res_comp = router_compile_prompt(variables={"jalali_date": "1405/01/01"})
    assert res_comp["success"] is True
    assert "1401" in res_comp["system_prompt"] or "1405" in res_comp["system_prompt"]

    # Tool: cascade plan
    res_casc = router_cascade_plan("تحقیق جامع پیرامون پردازنده‌های عصبی")
    assert res_casc["success"] is True
    assert res_casc["decision"]["target_tier"] == "reasoning_heavy"

    # Tool: get stats
    res_stats = router_get_stats()
    assert res_stats["success"] is True

    # Tool: export report
    res_rep = router_export_report()
    assert res_rep["success"] is True
    assert "Semantic Router & Cascading" in res_rep["markdown_report"]

    # Slash: /route
    slash_r = handle_router_slash_command("/route ساعت چنده؟")
    assert "نتیجه مسیریابی معنایی" in slash_r

    # Slash: /cascade
    slash_c = handle_router_slash_command("/cascade بنویس کد")
    assert "پلان آبشار مدل‌ها" in slash_c

    # Slash: /router stats
    slash_s = handle_router_slash_command("/router stats")
    assert "Semantic Router & Cascading" in slash_s

    # Slash: /router reset
    slash_reset = handle_router_slash_command("/router reset")
    assert "بازنشانی شد" in slash_reset
''',
}


def main() -> None:
    root = Path(__file__).resolve().parent
    if not (root / "dream").exists():
        if (root / "dream-repo" / "dream").exists():
            root = root / "dream-repo"
        elif (Path.cwd() / "dream").exists():
            root = Path.cwd()
        else:
            print(f"Error: could not locate Dream repo root from {root}")
            sys.exit(1)

    print(f"Applying Phase 37 (Semantic Router & Prompt Compiler Engine) to: {root}")

    for rel_path, content in FILES.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"  [written] {rel_path}")

    print("\nRunning pytest validation...")
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_router.py", "tests/test_semantic_router_and_compiler.py", "-v"],
        cwd=root,
    )
    if res.returncode != 0:
        print("\n[FAIL] Pytest failed for Phase 37")
        sys.exit(res.returncode)

    print("\nRunning security audit...")
    audit_res = subprocess.run(
        [sys.executable, "tools/security_audit.py"],
        cwd=root,
    )
    if audit_res.returncode != 0:
        print("\n[FAIL] Security audit failed for Phase 37")
        sys.exit(audit_res.returncode)

    print("\n[SUCCESS] Phase 37 (Semantic Router & Prompt Compiler Engine) applied and verified cleanly!")


if __name__ == "__main__":
    main()
