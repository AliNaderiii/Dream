"""Slash command handlers for Self-Improving Alignment & Preference Subsystem."""

from __future__ import annotations

from dream.alignment.tools import (
    alignment_critique_and_refine,
    alignment_evaluate_response,
    alignment_export_dataset,
    alignment_get_stats,
)


def handle_alignment_slash_command(command_str: str) -> str:
    """Handle /align CLI slash commands.

    Usage:
        /align stats
        /align score <text>
        /align critique <text>
        /align export <file_path>
        /align thumbsup <text>
        /align thumbsdown <text>
    """
    parts = command_str.strip().split(maxsplit=2)
    if len(parts) < 2:
        return (
            "✨ دستورات ترازبندی و یادگیری ترجیحات (Alignment):\n"
            "  /align stats                      گزارش آمار ترجیحات و پاداش\n"
            "  /align score <text>               ارزیابی ۶-بعدی پاسخ\n"
            "  /align critique <text>            خودانتقادی و بازنویسی بهبودی یافته\n"
            "  /align export <file_path>         خروجی داده‌های DPO JSONL برای Fine-Tuning"
        )

    subcommand = parts[1].lower()
    arg = parts[2] if len(parts) > 2 else ""

    if subcommand == "stats":
        stats = alignment_get_stats()
        ready_icon = "✅" if stats.get("export_ready") else "❌"
        return (
            "📊 گزارش مجموعه داده ترازبندی:\n"
            f"- تعداد جفت‌های ترجیحی DPO: {stats.get('total_pairs', 0)}\n"
            f"- میانگین پاداش (Reward): {stats.get('avg_reward_score', 0):.2f}\n"
            f"- آماده صادرات: {ready_icon}"
        )

    if subcommand == "score":
        if not arg:
            return "❌ لطفاً متن پاسخ را برای ارزیابی وارد کنید."
        res = alignment_evaluate_response("User Query", arg)
        scores_str = "\n".join(
            f"  • {s['dimension']}: {s['score']:.2f} ({s['reasoning']})"
            for s in res.get("scores", [])
        )
        return (
            f"🎯 نتیجه ارزیابی ۶-بعدی:\n"
            f"پاداش کلی: {res.get('composite_reward', 0):.2f}/1.0\n"
            f"{scores_str}"
        )

    if subcommand == "critique":
        if not arg:
            return "❌ لطفاً متن پاسخ را برای خودانتقادی وارد کنید."
        res = alignment_critique_and_refine("User Query", arg)
        rep = res.get("critique_report", {})
        flaws = rep.get("identified_flaws", [])
        flaws_str = ", ".join(flaws) if flaws else "موردی یافت نشد"
        return (
            "🔍 گزارش خودانتقادی:\n"
            f"نقاط ضعف: {flaws_str}\n"
            f"پاسخ بهبودی‌یافته:\n{rep.get('refined_response', '')}"
        )

    if subcommand == "export":
        out_path = arg.strip() or "data/alignment_dpo.jsonl"
        res = alignment_export_dataset(out_path)
        if res.get("success"):
            cnt = res.get("exported_pairs_count")
            return f"✅ تعداد {cnt} جفت ترجیحی DPO با موفقیت در '{out_path}' ذخیره شد."
        return f"❌ خطا در صادرات: {res.get('error')}"

    return f"❌ زیردستور ناشناخته '{subcommand}'. برای راهنما '/align' را بزنید."
