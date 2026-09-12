"""CLI and slash command handlers for Agent Evals & Benchmarks."""

from __future__ import annotations

from dream.evals.tools import (
    evals_compare_baseline,
    evals_export_report,
    evals_get_status,
    evals_list_suites,
    evals_reset,
    evals_run_suite,
)


def handle_evals_slash_command(command_str: str) -> str:
    """Handle /evals CLI slash commands for benchmarking and evaluation."""
    cmd = command_str.strip()
    if not cmd.startswith("/evals"):
        return "❌ دستور نامعتبر است."

    parts = cmd[len("/evals") :].strip().split()
    if not parts:
        return (
            "🎯 **راهنمای دستورات ارزیابی و بنچ‌مارک (/evals):**\n"
            "- `/evals list`: مشاهده لیست مجموعه‌های بنچ‌مارک استاندارد\n"
            "- `/evals run [suite]`: اجرای ارزیابی روی مجموعه انتخابی\n"
            "- `/evals compare [suite]`: مقایسه تجربی عملکرد با مدل Hermes\n"
            "- `/evals report`: نمایش گزارش رسمی آخرین ارزیابی\n"
            "- `/evals status`: مشاهده آمار کلی ارزیابی‌ها\n"
            "- `/evals reset`: پاکسازی تاریخچه ارزیابی‌ها"
        )

    subcmd = parts[0].lower()

    if subcmd == "list":
        res = evals_list_suites()
        suites = res.get("suites", [])
        lines = ["📋 **مجموعه‌های بنچ‌مارک استاندارد Dream:**"]
        for s in suites:
            lines.append(
                f"- `{s['suite_id']}`: {s['name']} "
                f"({s['total_cases']} تست) — {s['description_fa']}"
            )
        return "\n".join(lines)

    if subcmd == "run":
        suite_id = parts[1] if len(parts) > 1 else "persian_core"
        res = evals_run_suite(suite_id=suite_id)
        if not res.get("success"):
            return f"❌ {res.get('summary_fa', 'خطا در اجرای ارزیابی.')}"
        rep = res.get("report", {})
        rate = rep.get("overall_pass_rate", 0.0) * 100
        score = rep.get("overall_composite_score", 0.0) * 100
        dur = rep.get("duration_ms", 0.0)
        return (
            f"✅ **نتیجه ارزیابی مجموعه `{suite_id}` ({dur:.1f} میلی‌ثانیه):**\n"
            f"- نرخ قبولی: `{rate:.1f}%` ({rep.get('passed_cases')}/{rep.get('total_cases')})\n"
            f"- میانگین امتیاز: `{score:.1f}/100`\n"
            f"- زمان میانگین پاسخ: `{rep.get('average_latency_ms'):.1f}ms`\n\n"
            f"{rep.get('summary_fa', '')}"
        )

    if subcmd == "compare":
        suite_id = parts[1] if len(parts) > 1 else "persian_core"
        res = evals_compare_baseline(suite_id=suite_id)
        if not res.get("success"):
            return "❌ خطا در مقایسه با بنچ‌مارک پایه."
        winner = res.get("winner", "Dream")
        diff = res.get("relative_improvement_pct", 0.0)
        icon = "🏆" if winner == "Dream" else "⚠️"
        d_score = res.get("dream_score", 0.0) * 100
        d_pass = res.get("dream_pass_rate", 0.0) * 100
        h_score = res.get("hermes_baseline_score", 0.0) * 100
        h_pass = res.get("hermes_pass_rate", 0.0) * 100
        return (
            f"{icon} **نتایج مقایسه با مدل پایه Hermes (مجموعه `{suite_id}`):**\n"
            f"- امتیاز Dream: `{d_score:.1f}%` (قبولی: `{d_pass:.1f}%`)\n"
            f"- امتیاز Hermes: `{h_score:.1f}%` (قبولی: `{h_pass:.1f}%`)\n"
            f"- بهبود عملکرد: `+{diff:.1f}%`\n"
            f"- برنده بنچ‌مارک: **{winner}**"
        )

    if subcmd == "report":
        res = evals_export_report()
        return res.get("markdown_report", "")

    if subcmd == "status":
        res = evals_get_status()
        total = res.get("total_eval_runs", 0)
        avail = res.get("available_suites", 0)
        return (
            f"📊 **وضعیت سیستم ارزیابی:**\n"
            f"- مجموع ارزیابی‌های اجراشده: {total}\n"
            f"- مجموعه‌های تست فعال: {avail}"
        )

    if subcmd == "reset":
        res = evals_reset()
        return f"✅ {res.get('message_fa', 'بازنشانی شد.')}"

    return "❌ دستور نامعتبر است. برای راهنما `/evals` را وارد کنید."
