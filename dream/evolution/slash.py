"""CLI and slash command handlers for Self-Evolution & Policy Distillation."""

from __future__ import annotations

from dream.evolution.tools import (
    evolution_distill_heuristics,
    evolution_export_policy,
    evolution_get_leaderboard,
    evolution_get_status,
    evolution_reset,
    evolution_run_tournament,
)


def handle_evolution_slash_command(command_str: str) -> str:
    """Handle /evolution CLI slash commands for agent self-evolution."""
    cmd = command_str.strip()
    if not cmd.startswith("/evolution"):
        return "❌ دستور نامعتبر است."

    parts = cmd[len("/evolution") :].strip().split()
    if not parts:
        return (
            "🧬 **راهنمای دستورات تکامل خودکار عامل (/evolution):**\n"
            "- `/evolution distill`: استخراج و تقطیر قوانین هیوریستیک از تجربیات\n"
            "- `/evolution arena [rounds]`: اجرای تورنمنت تکاملی و جهش استراتژی‌ها\n"
            "- `/evolution leaderboard`: مشاهده جدول رده‌بندی استراتژی‌ها بر اساس Elo\n"
            "- `/evolution policy`: خروجی خط‌مشی تکاملی به صورت Markdown\n"
            "- `/evolution status`: مشاهده وضعیت کلی موتور تکامل\n"
            "- `/evolution reset`: بازنشانی وضعیت تکاملی"
        )

    subcmd = parts[0].lower()

    if subcmd == "distill":
        res = evolution_distill_heuristics()
        rules = res.get("distilled_rules", [])
        lines = [f"🔍 **{res.get('summary_fa', 'قوانین استخراج‌شده:')}**"]
        for r in rules:
            lines.append(f"- {r}")
        return "\n".join(lines)

    if subcmd == "arena":
        rounds = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 3
        res = evolution_run_tournament(rounds=rounds)
        if not res.get("success"):
            return "❌ خطا در اجرای تورنمنت تکاملی."
        rep = res.get("report", {})
        top = rep.get("top_strategy", {})
        dur = rep.get("duration_ms", 0.0)
        return (
            f"🏆 **پایان تورنمنت تکاملی ({dur:.1f} میلی‌ثانیه):**\n"
            f"- استراتژی برتر: **{top.get('name')}** (نسل {top.get('generation')})\n"
            f"- ریتینگ Elo جدید: `{top.get('elo_rating', 0.0):.1f}`\n"
            f"- تعداد مسابقات انجام‌شده: `{rep.get('total_matches')}`\n\n"
            f"{rep.get('summary_fa', '')}"
        )

    if subcmd == "leaderboard":
        res = evolution_get_leaderboard()
        board = res.get("leaderboard", [])
        lines = ["📊 **لیدربورد استراتژی‌های عامل (Elo Rating):**"]
        for idx, g in enumerate(board, 1):
            lines.append(
                f"{idx}. **{g['name']}** — Elo: `{g['elo_rating']:.1f}` "
                f"| برد/باخت: `{g['wins']}/{g['losses']}` | نسل: `{g['generation']}`"
            )
        return "\n".join(lines)

    if subcmd == "policy":
        res = evolution_export_policy()
        return res.get("policy_markdown", "")

    if subcmd == "status":
        res = evolution_get_status()
        return (
            f"📈 **وضعیت سیستم تکامل خودکار:**\n"
            f"- تجربیات ثبت‌شده: {res.get('total_playbacks')}\n"
            f"- استراتژی‌های فعال: {res.get('total_strategy_genes')}\n"
            f"- دفعات اجرای تورنمنت: {res.get('total_tournament_runs')}"
        )

    if subcmd == "reset":
        res = evolution_reset()
        return f"✅ {res.get('message_fa', 'بازنشانی شد.')}"

    return "❌ دستور نامعتبر است. برای راهنما `/evolution` را وارد کنید."
