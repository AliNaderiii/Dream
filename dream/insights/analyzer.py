"""Analytical engine computing conversation token usage, financial costs, and tool heatmaps."""

from __future__ import annotations

import collections
import re
from typing import Any

from dream.compression.base import CHARS_PER_TOKEN
from dream.insights.types import (
    CostEstimate,
    SessionInsightReport,
    TokenBreakdown,
    ToolUsageStats,
)

# Reference cost rates per 1M tokens (standard blend rate)
INPUT_COST_PER_MILLION_USD = 0.50
OUTPUT_COST_PER_MILLION_USD = 1.50
DEFAULT_TOMAN_USD_RATE = 60_000.0


class InsightsAnalyzer:
    """Analyzes message histories and metrics to generate telemetry and optimization insights."""

    def __init__(self, exchange_rate_toman: float = DEFAULT_TOMAN_USD_RATE) -> None:
        self.exchange_rate_toman = exchange_rate_toman

    def analyze_messages(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str = "",
    ) -> SessionInsightReport:
        """Analyze a list of conversational messages and produce a complete InsightReport."""
        prompt_chars = 0
        completion_chars = 0
        tool_chars = 0
        system_chars = len(system_prompt)

        tool_counter: collections.Counter[str] = collections.Counter()
        tool_chars_counter: collections.Counter[str] = collections.Counter()
        tool_error_counter: collections.Counter[str] = collections.Counter()

        user_turns = 0
        user_texts: list[str] = []

        for msg in messages:
            role = msg.get("role", "")
            content = str(msg.get("content") or "")

            if role == "user":
                user_turns += 1
                prompt_chars += len(content)
                user_texts.append(content)
            elif role == "assistant":
                completion_chars += len(content)
                tool_calls = msg.get("tool_calls")
                if tool_calls and isinstance(tool_calls, list):
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            fn_name = (
                                tc.get("function", {}).get("name")
                                or tc.get("name")
                                or "tool"
                            )
                            tool_counter[fn_name] += 1
            elif role == "tool" or msg.get("kind") == "tool_result":
                tool_chars += len(content)
                tname = str(msg.get("name") or "tool")
                tool_chars_counter[tname] += len(content)
                if "error" in content.lower() or "خطا" in content:
                    tool_error_counter[tname] += 1
            elif role == "system":
                system_chars += len(content)

        prompt_tokens = max(0, (prompt_chars + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)
        completion_tokens = max(0, (completion_chars + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)
        tool_tokens = max(0, (tool_chars + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)
        system_tokens = max(0, (system_chars + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)
        total_tokens = prompt_tokens + completion_tokens + tool_tokens + system_tokens

        # Financial cost calculations
        in_cost = ((prompt_tokens + system_tokens + tool_tokens) / 1_000_000.0)
        out_cost = (completion_tokens / 1_000_000.0)
        usd_cost = (in_cost * INPUT_COST_PER_MILLION_USD) + (out_cost * OUTPUT_COST_PER_MILLION_USD)
        toman_cost = usd_cost * self.exchange_rate_toman

        cost_obj = CostEstimate(
            usd_cost=usd_cost,
            toman_cost=toman_cost,
            exchange_rate_toman=self.exchange_rate_toman,
        )

        tokens_obj = TokenBreakdown(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tool_tokens=tool_tokens,
            system_tokens=system_tokens,
            total_tokens=total_tokens,
        )

        # Tool stats aggregation
        tools_stats: list[ToolUsageStats] = []
        all_tool_names = set(tool_counter.keys()) | set(tool_chars_counter.keys())
        for name in sorted(all_tool_names):
            calls = max(tool_counter[name], 1 if name in tool_chars_counter else 0)
            errs = tool_error_counter[name]
            chars = tool_chars_counter[name]
            tools_stats.append(
                ToolUsageStats(
                    name=name,
                    call_count=calls,
                    error_count=errs,
                    total_chars_generated=chars,
                )
            )

        # Topic and recommendation heuristics
        top_topics = self._extract_key_topics(user_texts)
        recommendations = self._generate_recommendations(tokens_obj, tools_stats)

        return SessionInsightReport(
            message_count=len(messages),
            turn_count=user_turns,
            tokens=tokens_obj,
            cost=cost_obj,
            tools=tools_stats,
            top_topics=top_topics,
            recommendations=recommendations,
        )

    def _extract_key_topics(self, user_texts: list[str]) -> list[str]:
        """Extract frequent topics from user messages."""
        words: list[str] = []
        for text in user_texts:
            tokens = re.findall(r"[\w\u0600-\u06FF]{3,}", text)
            words.extend(tokens)

        # Filter common stopwords
        stopwords = {
            "لطفاً", "برای", "است", "کنید", "دارد", "این", "آن", "که", "با", "از", "در",
            "please", "the", "and", "for", "with", "this", "that", "from"
        }
        filtered = [w for w in words if w.lower() not in stopwords]
        counts = collections.Counter(filtered).most_common(5)
        return [w for w, _ in counts]

    def _generate_recommendations(
        self, tokens: TokenBreakdown, tools: list[ToolUsageStats]
    ) -> list[str]:
        """Provide intelligent context and cost optimization suggestions."""
        recs = []
        if tokens.tool_percentage > 40.0:
            recs.append(
                "💡 خروجی ابزارها بیش از ۴۰٪ کانتکست است؛ دستور `/compress code` پیشنهاد می‌شود."
            )
        if tokens.system_tokens > 2000:
            recs.append(
                "💡 حجم دستورات سیستم (System Prompt) بالاست؛ برای کاهش مصرف توکن بازبینی فرمایید."
            )
        for t in tools:
            if t.error_count > 0:
                recs.append(
                    f"⚠️ ابزار `{t.name}` دارای {t.error_count} خطا بود؛ "
                    "بررسی پایداری سرور پیشنهاد می‌شود."
                )
        if not recs:
            recs.append("✅ وضعیت مصرف توکن و کانتکست در حالت بهینه و متعادل قرار دارد.")
        return recs
