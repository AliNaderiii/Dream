"""CLI and slash command handlers for Semantic Router and Dynamic Prompt Compiler."""

from __future__ import annotations

from typing import Any

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
            return "\u2705 \u0622\u0645\u0627\u0631 \u0645\u0633\u06cc\u0631\u06cc\u0627\u0628\u06cc \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."

        res = router_export_report()
        return res.get("markdown_report", "")

    if cmd.startswith("/cascade"):
        q = cmd[len("/cascade") :].strip()
        if not q:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u067e\u0631\u0633\u0634 \u0631\u0627 \u0628\u0631\u0627\u06cc \u062a\u0648\u0644\u06cc\u062f \u067e\u0644\u0627\u0646 \u0622\u0628\u0634\u0627\u0631 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = router_cascade_plan(q)
        plan = res.get("cascade_plan", {})
        return (
            f"\U0001f30a \u067e\u0644\u0627\u0646 \u0622\u0628\u0634\u0627\u0631 \u0645\u062f\u0644\u200c\u0647\u0627 (Cascading Pipeline):\n"
            f"- \u0645\u062f\u0644 \u0627\u0648\u0644\u06cc\u0647: `{plan.get('primary_tier')}`\n"
            f"- \u0632\u0646\u062c\u06cc\u0631\u0647 \u0627\u0631\u062a\u0642\u0627: {' -> '.join(plan.get('escalation_chain', []))}\n"
            f"- \u0627\u0628\u0632\u0627\u0631\u0647\u0627\u06cc \u067e\u06cc\u0634\u200c\u0628\u06cc\u0646\u06cc\u200c\u0634\u062f\u0647: `{', '.join(plan.get('speculative_tools', [])) or 'none'}`"
        )

    if cmd.startswith("/route"):
        q = cmd[len("/route") :].strip()
        if not q:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u067e\u0631\u0633\u0634 \u06cc\u0627 \u067e\u0631\u0627\u0645\u067e\u062a \u0631\u0627 \u0628\u0631\u0627\u06cc \u0645\u0633\u06cc\u0631\u06cc\u0627\u0628\u06cc \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = router_evaluate_query(q)
        dec = res.get("decision", {})
        return (
            f"\U0001f6e4\ufe0f \u0646\u062a\u06cc\u062c\u0647 \u0645\u0633\u06cc\u0631\u06cc\u0627\u0628\u06cc \u0645\u0639\u0646\u0627\u06cc\u06cc:\n"
            f"- \u0642\u0635\u062f (Intent): `{dec.get('intent')}`\n"
            f"- \u0645\u062f\u0644 \u0647\u062f\u0641 (Tier): `{dec.get('target_tier')}`\n"
            f"- \u0635\u0631\u0641\u0647\u200c\u062c\u0648\u06cc\u06cc \u062a\u0648\u06a9\u0646: {dec.get('estimated_tokens_saved')} \u062a\u0648\u06a9\u0646\n"
            f"- \u0627\u0637\u0645\u06cc\u0646\u0627\u0646 (Confidence): {dec.get('confidence') * 100:.1f}%\n"
            f"- \u062a\u062d\u0644\u06cc\u0644: {dec.get('rationale_fa')}"
        )

    return "\u274c \u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a."
