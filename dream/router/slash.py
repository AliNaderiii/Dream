"""CLI and slash command handlers for Semantic Router and Dynamic Prompt Compiler."""

from __future__ import annotations

from dream.router.tools import (
    router_cascade_plan,
    router_evaluate_query,
    router_export_report,
    router_reset_all,
)


def handle_router_slash_command(command_str: str) -> str:
    """Handle /route, /cascade, and /router CLI slash commands.

    Usage:
        /route <query>
        /cascade <query>
        /router [stats|reset]
    """
    cmd = command_str.strip()

    if cmd.startswith("/router"):
        parts = cmd.split()
        subcmd = parts[1].lower() if len(parts) > 1 else "stats"
        if subcmd == "reset":
            router_reset_all()
            return "✅ آمار مسیریابی بازنشانی شد."

        res = router_export_report()
        return res.get("markdown_report", "")

    if cmd.startswith("/cascade"):
        q = cmd[len("/cascade") :].strip()
        if not q:
            return "❌ لطفاً پرسش را برای تولید پلان آبشار وارد کنید."
        res = router_cascade_plan(q)
        plan = res.get("cascade_plan", {})
        tools = ", ".join(plan.get("speculative_tools", [])) or "none"
        chain = " -> ".join(plan.get("escalation_chain", []))
        return (
            "🌊 پلان آبشار مدل‌ها (Cascading Pipeline):\n"
            f"- مدل اولیه: `{plan.get('primary_tier')}`\n"
            f"- زنجیره ارتقا: {chain}\n"
            f"- ابزارهای پیش‌بینی‌شده: `{tools}`"
        )

    if cmd.startswith("/route"):
        q = cmd[len("/route") :].strip()
        if not q:
            return "❌ لطفاً پرسش یا پرامپت را برای مسیریابی وارد کنید."
        res = router_evaluate_query(q)
        dec = res.get("decision", {})
        conf = dec.get("confidence", 0.0) * 100
        return (
            "🛣️ نتیجه مسیریابی معنایی:\n"
            f"- قصد (Intent): `{dec.get('intent')}`\n"
            f"- مدل هدف (Tier): `{dec.get('target_tier')}`\n"
            f"- صرفه‌جویی توکن: {dec.get('estimated_tokens_saved')} توکن\n"
            f"- اطمینان (Confidence): {conf:.1f}%\n"
            f"- تحلیل: {dec.get('rationale_fa')}"
        )

    return "❌ دستور نامعتبر است."
