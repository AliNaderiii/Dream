"""CLI and slash command handlers for Metacognitive Reasoning and Tree-of-Thought."""

from __future__ import annotations

from dream.reasoning.tools import (
    reasoning_get_status,
    reasoning_reset_all,
    reasoning_solve_goal,
)


def handle_reasoning_slash_command(command_str: str) -> str:
    """Handle /think, /tot, and /reasoning CLI slash commands.

    Usage:
        /think <problem_or_goal>
        /tot <problem_or_goal>
        /reasoning status
        /reasoning reset
    """
    cmd = command_str.strip()

    if cmd.startswith("/think") or cmd.startswith("/tot"):
        prefix = "/think" if cmd.startswith("/think") else "/tot"
        goal = cmd[len(prefix) :].strip()
        if not goal:
            return "❌ لطفاً مسئله یا هدف را برای استدلال درختی وارد کنید."

        # Generate standard hypothesis set
        hypotheses = [
            f"راهکار مستقیم و تحلیلی برای حل {goal}",
            "راهکار تجزیه مسئله به زیرمسائل کوچک‌تر",
            "رویکرد احتیاطی و بررسی ریسک‌های احتمالی",
        ]

        res = reasoning_solve_goal(goal=goal, hypotheses=hypotheses)
        if res.get("success"):
            return res.get("report", "")
        return f"❌ خطا در استدلال درختی: {res.get('error')}"

    if not cmd.startswith("/reasoning"):
        return "❌ دستور نامعتبر است."

    parts = cmd.split(maxsplit=2)
    if len(parts) == 1:
        return (
            "🧠 دستورات موتور استدلال فراشناختی (Reasoning / ToT):\n"
            "  /think <goal>                             حل مسئله با درخت استدلال (ToT)\n"
            "  /tot <goal>                               اجرای کاوش چند‌مسیره\n"
            "  /reasoning status                         وضعیت درخت‌های استدلال\n"
            "  /reasoning reset                          پاکسازی و بازنشانی"
        )

    subcmd = parts[1].lower()

    if subcmd == "status":
        st = reasoning_get_status()
        act_id = st.get("active_trajectory_id")
        act_str = act_id if act_id else "هیچ"
        return (
            "🗟 وضعیت موتور استدلال:\n"
            f"- تعداد درخت‌های فعال: {st.get('total_trajectories')}\n"
            f"- شناسه مسیر جاری: {act_str}"
        )

    if subcmd == "reset":
        reasoning_reset_all()
        return "✅ درخت‌های استدلال بازنشانی شد."

    return "❌ زیردستور نامعتبر است."
