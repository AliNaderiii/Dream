"""Agent tools for context compaction, insights, and fast-mode management."""

from __future__ import annotations

import json

from dream.compression.fast_mode import get_fast_mode_controller
from dream.insights.analyzer import InsightsAnalyzer
from dream.tools.base import tool


@tool(risk="safe")
def set_fast_mode(mode: str = "auto") -> str:
    """Set the agent execution speed and latency mode ('auto', 'cold', 'turbo').

    :param mode: Desired mode ('auto' adaptive, 'cold' deep reasoning, 'turbo' low latency).
    """
    controller = get_fast_mode_controller()
    try:
        new_mode = controller.set_mode(mode)
        return f"حالت سرعت ایجنت با موفقیت روی '{new_mode.value}' تنظیم شد."
    except Exception as exc:
        return f"خطا در تنظیم حالت سرعت: {exc}"


@tool(risk="safe")
def get_insights_report(session_id: str = "") -> str:
    """Generate token consumption, tool frequency, and financial cost insights.

    :param session_id: Optional session identifier.
    """
    analyzer = InsightsAnalyzer()
    # Produce diagnostic baseline report
    report = analyzer.analyze_messages([])
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
