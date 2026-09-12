"""Routing Engine Coordinator: Links semantic routing, prompt compilation & cascading."""

from __future__ import annotations

from typing import Any

from dream.router.cascade import ModelCascader
from dream.router.compiler import PromptCompiler
from dream.router.semantic import SemanticRouter
from dream.router.types import (
    CompiledPrompt,
    IntentComplexity,
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

        direct = sum(
            1 for d in self._decisions_history if d.intent == IntentComplexity.DIRECT_ANSWER
        )
        simple = sum(
            1 for d in self._decisions_history if d.intent == IntentComplexity.SIMPLE_TOOL
        )
        reasoning = sum(
            1 for d in self._decisions_history if d.intent == IntentComplexity.REASONING_CHAIN
        )
        deep = sum(
            1 for d in self._decisions_history if d.intent == IntentComplexity.DEEP_RESEARCH
        )
        code = sum(
            1 for d in self._decisions_history if d.intent == IntentComplexity.CODE_EXECUTION
        )
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
            "## 🛣️ گزارش مسیریابی معنایی و آبشار مدل‌ها (Semantic Router & Cascading)",
            f"- **تعداد کل درخواست‌های مسیریابی‌شده:** {stats.total_routed}",
            f"- **صرفه‌جویی تخمینی توکن:** {stats.total_tokens_saved:,} توکن",
            f"- **میانگین زمان تصمیم‌گیری:** {stats.average_latency_ms:.2f} ms",
            "",
            "### 📊 تفکیک قصدها (Intents):",
            f"- پاسخ مستقیم (Direct): {stats.direct_answers}",
            f"- تک‌ابزاری (Simple Tool): {stats.simple_tools}",
            f"- استدلال پیچیده (Reasoning): {stats.reasoning_chains}",
            f"- تحقیق عمیق (Deep Research): {stats.deep_researches}",
            f"- اجرای کد (Code Execution): {stats.code_executions}",
        ]
        return "\n".join(lines)

    def reset(self) -> None:
        """Reset routing history and counters."""
        self._decisions_history.clear()
        self._total_latency_ms = 0.0
