"""Slash command handler for session insights, cost analytics, and performance metrics."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.insights.analyzer import InsightsAnalyzer


def handle_insights_command(
    args: str,
    messages: list[dict[str, Any]] | None = None,
    system_prompt: str = "",
    output: Callable[[str], None] = print,
) -> bool:
    """Process `/insights` slash command.

    Usage:
        /insights
        /insights --detailed
        /insights --days 7
    """
    history = messages or []
    analyzer = InsightsAnalyzer()
    report = analyzer.analyze_messages(history, system_prompt=system_prompt)

    output("📊 **تحلیل و بینش‌های نشست گفتگو / Session Insights & Economics:**\n")
    output(f"  • تعداد پیام‌ها: {report.message_count} | تعداد نوبت‌های کاربر: {report.turn_count}")
    output(f"  • کل توکن‌های مصرفی: {report.tokens.total_tokens:,} توکن")
    output(
        f"     ↳ ورودی کاربر: {report.tokens.prompt_tokens:,} | "
        f"پاسخ دستیار: {report.tokens.completion_tokens:,} | "
        f"ابزارها: {report.tokens.tool_tokens:,} ({report.tokens.tool_percentage:.1f}%)"
    )
    output(
        f"  • برآورد هزینه تخمینی: **${report.cost.usd_cost:.4f} دلار** "
        f"(معادل **{report.cost.toman_cost:,.0f} تومان**)\n"
    )

    if report.tools:
        output("🛠️ **آمار فراخوانی ابزارها:**")
        for t in report.tools:
            err_str = f" ({t.error_count} خطا)" if t.error_count else ""
            output(
                f"  - `{t.name}`: {t.call_count} بار فراخوانی{err_str} "
                f"— موفقیت: {t.success_rate:.0f}%"
            )
        output("")

    if report.top_topics:
        output(f"🏷️ **موضوعات پربسامد گفتگو:** {', '.join(report.top_topics)}\n")

    output("💡 **پیشنهادات بهینه‌سازی کانتکست:**")
    for rec in report.recommendations:
        output(f"  {rec}")

    return True
