"""Slash command handlers for Autonomous Deep Research & Multi-Source Synthesis."""

from __future__ import annotations

from dream.research.tools import (
    research_export_report,
    research_get_status,
    research_list_sessions,
    research_run_autonomous,
)


def handle_research_slash_command(command_str: str) -> str:
    """Handle /research CLI slash commands.

    Usage:
        /research start <topic>
        /research status <session_id>
        /research export <session_id> [file_path]
        /research list
    """
    parts = command_str.strip().split(maxsplit=2)
    if len(parts) < 2:
        return (
            "🔎 دستورات پژوهش عمیق و تدوین گزارش (Deep Research):\n"
            "  /research start <topic>           اجرای پژوهش خودکار و تولید گزارش\n"
            "  /research status <session_id>     بررسی وضعیت و یافته‌های نشست\n"
            "  /research export <id> [path]      ذخیره گزارش در فایل Markdown\n"
            "  /research list                    فهرست نشست‌های پژوهشی"
        )

    subcommand = parts[1].lower()
    arg = parts[2] if len(parts) > 2 else ""

    if subcommand == "list":
        res = research_list_sessions()
        sessions = res.get("sessions", [])
        if not sessions:
            return "📋 هیچ نشست پژوهشی ثبت نشده است."
        lines = ["📚 فهرست نشست‌های پژوهش عمیق:"]
        for s in sessions:
            sid = s["session_id"]
            stop = s["topic"]
            sst = s["status"]
            scnt = s["sources_count"]
            lines.append(f"  • [{sid}] {stop} ({sst}) - {scnt} منبع")
        return "\n".join(lines)

    if subcommand == "start":
        if not arg:
            return "❌ لطفاً موضوع پژوهش را وارد کنید."
        res = research_run_autonomous(arg)
        rep = res.get("report", {})
        sid = res.get("session_id", "")
        summary = rep.get("executive_summary_fa", "")
        sources_cnt = rep.get("total_sources_analyzed", 0)
        conf = rep.get("confidence_level", 0.0)
        return (
            f"✅ پژوهش عمیق برای '{arg}' تکمیل شد! (ID: {sid})\n"
            f"📋 چکیده: {summary}\n"
            f"📖 تعداد منابع: {sources_cnt} | ضریب اطمینان: {conf:.2f}"
        )

    if subcommand == "status":
        if not arg:
            return "❌ لطفاً شناسه نشست (session_id) را وارد کنید."
        res = research_get_status(arg)
        if not res.get("success"):
            return f"❌ {res.get('error')}"
        plan = res.get("plan", {})
        return (
            f"🔎 وضعیت نشست [{plan.get('session_id')}]:\n"
            f"- موضوع: {plan.get('topic')}\n"
            f"- وضعیت: {plan.get('status')}\n"
            f"- منابع جمع‌آوری‌شده: {plan.get('sources_collected_count')}\n"
            f"- یافته‌ها: {plan.get('findings_count')}"
        )

    if subcommand == "export":
        args = arg.split(maxsplit=1)
        if not args:
            return "❌ شناسه نشست را وارد کنید."
        sid = args[0]
        out_path = args[1] if len(args) > 1 else f"data/research_{sid}.md"
        res = research_export_report(sid, out_path)
        if res.get("success"):
            return f"✅ گزارش با موفقیت در '{out_path}' ذخیره شد."
        return f"❌ خطا در ذخیره: {res.get('error')}"

    return f"❌ زیردستور ناشناخته '{subcommand}'. برای راهنما '/research' را بزنید."
