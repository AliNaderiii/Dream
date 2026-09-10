"""Structured summarization for compacted conversational turns with Jalali preservation."""

from __future__ import annotations

import re
from typing import Any


def deterministic_summary(dropped: list[dict[str, Any]], reason: str) -> str:
    """Return a byte-stable bilingual summary header for offline transports."""
    roles = ",".join(str(item.get("role", "event")) for item in dropped)
    chars = sum(len(str(item.get("content") or "")) for item in dropped)
    # Tool outputs are facts in the conversational record. Keep a bounded,
    # deterministic copy so a later reference remains answerable after its
    # exchange has left the active window.
    tool_results = [
        str(item.get("content") or "")[:512]
        for item in dropped
        if item.get("role") == "tool"
    ]
    preserved = " | ".join(tool_results)
    suffix = f" preserved_tool_results={preserved!r}." if preserved else ""
    header = "[Context compacted / \u0641\u0634\u0631\u062f\u0647\u200c\u0633\u0627\u0632\u06cc \u0634\u062f] "  # noqa: E501
    details = f"reason={reason}; dropped_messages={len(dropped)}; dropped_chars={chars}; roles={roles}.{suffix}"  # noqa: E501
    return f"{header}{details}"


def extract_persian_timeline(messages: list[dict[str, Any]]) -> list[str]:
    """Extract Jalali dates, times, and reminder notes from dropped conversation items."""
    temporal_patterns = [
        re.compile(r"\b1[34]\d\d/\d{1,2}/\d{1,2}\b"),  # Jalali dates like 1403/06/20
        re.compile(r"\b(?:امروز|فردا|پس‌فردا|دیروز|هفته آینده|ماه آینده)\b"),
        re.compile(r"\bساعت\s+\d{1,2}(?::\d{1,2})?\b"),
    ]
    highlights: list[str] = []
    for msg in messages:
        text = str(msg.get("content") or "")
        for pattern in temporal_patterns:
            matches = pattern.findall(text)
            if matches:
                highlights.extend(matches)
    return sorted(set(highlights))


def generate_structured_summary(dropped: list[dict[str, Any]], reason: str) -> str:
    """Generate a multi-section structured context summary with Persian temporal context."""
    base_header = deterministic_summary(dropped, reason)
    timeline = extract_persian_timeline(dropped)

    # Extract user requests and tool names
    user_requests = [
        str(m.get("content") or "")[:120].strip()
        for m in dropped
        if m.get("role") == "user" and m.get("content")
    ]

    sections = [base_header]

    if timeline:
        sections.append(
            f"📅 زمان‌بندی و تاریخ‌های گفتگو (Timeline): {', '.join(timeline[:8])}"
        )

    if user_requests:
        compact_reqs = " -> ".join(user_requests[:4])
        sections.append(f"🎯 درخواست‌های پیشین کاربر (Prior Goals): {compact_reqs}")

    return "\n".join(sections)
