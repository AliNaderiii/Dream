"""Zero-latency semantic intent routing and model tier selection engine."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

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
                    rationale_fa="مطابقت با الگوی سفارشی مسیریابی",
                )

        # Built-in heuristic intent classification
        matched_rules: list[str] = []
        intent = IntentComplexity.DIRECT_ANSWER
        target_tier = ModelTier.FAST_EDGE
        confidence = 0.80

        # 1. Code Execution Check
        code_keywords = [
            "کد",
            "پایتون",
            "برنامه",
            "اسکریپت",
            "الگوریتم",
            "تابع",
            "دیباگ",
            "python",
            "code",
            "script",
            "algorithm",
            "function",
            "debug",
            "def ",
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
                "تحقیق جامع",
                "بررسی عمیق",
                "منابع مختلف",
                "مقایسه کامل",
                "تحلیل بازار",
                "deep research",
                "comprehensive review",
                "investigate",
                "synthesize",
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
                "استدلال",
                "چرا",
                "اثبات",
                "مناظره",
                "درخت تفکر",
                "منطق",
                "گام به گام",
                "ریشه‌یابی",
                "reasoning",
                "prove",
                "debate",
                "tree of thought",
                "logic",
                "step by step",
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
                "ساعت",
                "تاریخ",
                "تقویم",
                "آب و هوا",
                "جستجو کن",
                "سرچ کن",
                "محاسبه",
                "time",
                "date",
                "calendar",
                "weather",
                "search",
                "calculate",
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
            IntentComplexity.DIRECT_ANSWER: "پاسخ مستقیم بدون نیاز به ابزار (Fast Edge)",
            IntentComplexity.SIMPLE_TOOL: "اجرای تک‌ابزاری سریع (Fast Edge / Standard)",
            IntentComplexity.REASONING_CHAIN: (
                "نیازمند زنجیره استدلال و مدل شناختی پیشرفته (Reasoning Heavy)"
            ),
            IntentComplexity.DEEP_RESEARCH: "تحقیق چندمرحله‌ای و ترکیب منابع (Deep Research)",
            IntentComplexity.CODE_EXECUTION: "تحلیل و اجرای کد در سندباکس (Code Execution)",
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
