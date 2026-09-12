"""CLI and slash command handlers for Memory Consolidation and Epistemic Distillation."""

from __future__ import annotations

from dream.consolidation.tools import (
    consolidation_distill_session,
    consolidation_export_report,
    consolidation_reset_all,
    consolidation_run_cycle,
)


def handle_consolidation_slash_command(command_str: str) -> str:
    """Handle /consolidate, /distill_memory, and /memory_health CLI slash commands.

    Usage:
        /consolidate [dry_run]
        /distill_memory <transcript>
        /memory_health [reset]
    """
    cmd = command_str.strip()

    if cmd.startswith("/consolidate"):
        parts = cmd.split()
        is_dry = len(parts) > 1 and parts[1].lower() in ("dry", "dry_run", "preview")
        res = consolidation_run_cycle(dry_run=is_dry)
        rep = res.get("report", {})
        prefix = "(پیش‌نمایش)" if is_dry else ""
        return (
            f"🧠 نتیجه چرخه تثبیت حافظه {prefix}:\n"
            f"- گره‌ها: {rep.get('initial_memory_count')} -> {rep.get('final_memory_count')}\n"
            f"- هرس شده: {rep.get('pruned_nodes_count')} گره\n"
            f"- تعارض‌های حل‌شده: {rep.get('conflicts_resolved_count')}\n"
            f"- کاهش آنتروپی: {rep.get('entropy_reduction_pct', 0.0):.1f}%\n"
            f"- زمان اجرا: {rep.get('duration_ms', 0.0):.1f} میلی‌ثانیه"
        )

    if cmd.startswith("/distill_memory"):
        raw = cmd[len("/distill_memory") :].strip()
        if not raw:
            return "❌ لطفاً متن مکالمه را برای تقطیر وارد کنید."
        res = consolidation_distill_session(raw)
        cnt = res.get("distilled_facts_count", 0)
        return f"✨ تقطیر با موفقیت انجام شد: {cnt} فکت و باور جدید استخراج گردید."

    if cmd.startswith("/memory_health"):
        parts = cmd.split()
        subcmd = parts[1].lower() if len(parts) > 1 else "report"
        if subcmd == "reset":
            consolidation_reset_all()
            return "✅ حافظه و تاریخچه تثبیت بازنشانی شد."

        res = consolidation_export_report()
        return res.get("markdown_report", "")

    return "❌ دستور نامعتبر است."
