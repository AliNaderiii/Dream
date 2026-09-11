"""Multi-strategy context compression for Dream: Lossy, Code-Preserving, and Hybrid."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from dream.compression.base import CompactionResult
from dream.compression.engine import estimate_tokens, split_for_compaction
from dream.compression.summarizer import extract_persian_timeline


class CompressionStrategyType(str, Enum):
    """Available context compaction strategies."""

    LOSSY = "lossy"
    CODE_PRESERVING = "code"
    HYBRID = "hybrid"


class BaseCompressionStrategy(ABC):
    """Abstract interface for dialogue compression strategies."""

    @abstractmethod
    def summarize(self, dropped: list[dict[str, Any]], reason: str = "manual") -> str:
        """Produce a compressed summary text from dropped message turns."""


class LossyStrategy(BaseCompressionStrategy):
    """High-ratio narrative summary condensing conversational turns into concise prose."""

    def summarize(self, dropped: list[dict[str, Any]], reason: str = "manual") -> str:
        timeline = extract_persian_timeline(dropped)
        user_queries = [
            str(m.get("content") or "").strip()
            for m in dropped
            if m.get("role") == "user" and m.get("content")
        ]
        assistant_points = [
            str(m.get("content") or "").strip()[:100]
            for m in dropped
            if m.get("role") == "assistant" and m.get("content") and not m.get("tool_calls")
        ]

        sections = [
            f"[Context Compacted (Lossy Strategy) / خلاصه‌سازی متنی فشرده ({len(dropped)} پیام)]"
        ]
        if timeline:
            sections.append(f"• زمان‌بندی: {', '.join(timeline[:6])}")
        if user_queries:
            req_flow = " ➔ ".join(q[:80] for q in user_queries[:5])
            sections.append(f"• سیر درخواست‌های کاربر: {req_flow}")
        if assistant_points:
            sections.append(f"• نکات کلیدی پاسخ‌ها: {' | '.join(assistant_points[:4])}")

        return "\n".join(sections)


class CodePreservingStrategy(BaseCompressionStrategy):
    """Preserves all programming code blocks, SQL snippets, terminal output, and file diffs."""

    def __init__(self) -> None:
        self._code_pattern = re.compile(r"```(?:\w+)?\n([\s\S]*?)\n```", re.MULTILINE)
        self._path_pattern = re.compile(
            r"(?:/[\w\.\-]+)+|(?:\b[A-Za-z]:\\[\w\.\-\\]+)|(?:\b[\w\.\-]+\.(?:py|js|ts|json|md|html|sh|rs)\b)"
        )

    def summarize(self, dropped: list[dict[str, Any]], reason: str = "manual") -> str:
        extracted_code_blocks: list[str] = []
        referenced_paths: set[str] = set()

        for msg in dropped:
            content = str(msg.get("content") or "")
            # Find code blocks
            for match in self._code_pattern.finditer(content):
                snippet = match.group(0)
                if len(snippet) <= 2000:
                    extracted_code_blocks.append(snippet)
                else:
                    extracted_code_blocks.append(f"{snippet[:1000]}\n... [truncated code] ...\n```")

            # Find file paths
            paths = self._path_pattern.findall(content)
            for p in paths:
                if len(p) > 3 and not p.startswith("//"):
                    referenced_paths.add(p)

        lossy_header = LossyStrategy().summarize(dropped, reason)
        sections = [
            lossy_header.replace("Lossy Strategy", "Code-Preserving Strategy"),
        ]

        if referenced_paths:
            paths_str = ", ".join(sorted(referenced_paths)[:8])
            sections.append(f"📁 مسیرهای فایلی مورد استناد: {paths_str}")

        if extracted_code_blocks:
            sections.append(
                f"💻 کدهای استخراج‌شده جهت بقای کانتکست ({len(extracted_code_blocks)} قطعه کد):"
            )
            for block in extracted_code_blocks[:4]:
                sections.append(block)

        return "\n".join(sections)


class HybridStrategy(BaseCompressionStrategy):
    """Comprehensive semantic compaction: state dictionary, active tasks, timeline, and code."""

    def __init__(self) -> None:
        self._code_strat = CodePreservingStrategy()

    def summarize(self, dropped: list[dict[str, Any]], reason: str = "manual") -> str:
        timeline = extract_persian_timeline(dropped)
        tools_executed = [
            str(m.get("name") or "tool")
            for m in dropped
            if m.get("role") == "tool" or m.get("kind") == "tool_result"
        ]

        # Extract potential pending goals or instructions
        pending_goals: list[str] = []
        for msg in dropped:
            if msg.get("role") == "user":
                txt = str(msg.get("content") or "")
                if any(w in txt for w in ("باید", "لطفاً", "سپس", "بعد از", "todo", "next")):
                    pending_goals.append(txt[:90])

        code_summary = self._code_strat.summarize(dropped, reason)

        msg_count = len(dropped)
        sections = [
            f"[Context Compacted (Hybrid Strategy) / فشرده‌سازی ({msg_count} پیام)]",
        ]
        if timeline:
            sections.append(f"📅 خط زمانی وقایع و تاریخ‌ها: {', '.join(timeline[:8])}")
        if tools_executed:
            sections.append(f"⚙️ ابزارهای فراخوانی‌شده: {', '.join(tools_executed[:8])}")
        if pending_goals:
            sections.append(f"📌 اهداف و تسک‌های در جریان: {' | '.join(pending_goals[:4])}")

        # Append code highlights if any
        if "💻 کدهای استخراج‌شده" in code_summary:
            code_part = code_summary.split("📁 مسیرهای فایلی")[0]
            if "💻 کدهای استخراج‌شده" in code_part:
                sections.append(code_part[code_part.index("💻 کدهای استخراج‌شده") :])
            else:
                sections.append(code_summary[code_summary.index("💻 کدهای استخراج‌شده") :])

        return "\n".join(sections)


STRATEGIES: dict[CompressionStrategyType, BaseCompressionStrategy] = {
    CompressionStrategyType.LOSSY: LossyStrategy(),
    CompressionStrategyType.CODE_PRESERVING: CodePreservingStrategy(),
    CompressionStrategyType.HYBRID: HybridStrategy(),
}


def compress_messages(
    messages: list[dict[str, Any]],
    strategy: CompressionStrategyType | str = CompressionStrategyType.HYBRID,
    keep_recent: int = 4,
    reason: str = "manual_compress",
) -> tuple[list[dict[str, Any]], CompactionResult]:
    """Compress a list of messages using the specified strategy."""
    strat_key = (
        CompressionStrategyType(strategy)
        if isinstance(strategy, str)
        else strategy
    )
    strat_impl = STRATEGIES.get(strat_key, HybridStrategy())

    initial_tokens = estimate_tokens(messages)
    dropped, kept = split_for_compaction(messages, preserve=keep_recent)

    if not dropped:
        return list(messages), CompactionResult(
            compacted=False,
            reason="nothing_to_compact",
            tokens_before=initial_tokens,
            tokens_after=initial_tokens,
            dropped_messages_count=0,
            pruned_tools_count=0,
            summary_text="",
        )

    summary = strat_impl.summarize(dropped, reason=reason)
    summary_msg = {
        "role": "system",
        "content": summary,
        "_compaction_header": True,
    }
    result_messages = [summary_msg] + kept
    final_tokens = estimate_tokens(result_messages)

    return result_messages, CompactionResult(
        compacted=True,
        reason=reason,
        tokens_before=initial_tokens,
        tokens_after=final_tokens,
        dropped_messages_count=len(dropped),
        pruned_tools_count=0,
        summary_text=summary,
        metadata={"strategy": strat_key.value},
    )
