"""CLI and slash command handlers for Memory Consolidation and Epistemic Distillation."""

from __future__ import annotations

from typing import Any

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
        return (
            f"\U0001f9e0 \u0646\u062a\u06cc\u062c\u0647 \u0686\u0631\u062e\u0647 \u062a\u062b\u0628\u06cc\u062a \u062d\u0627\u0641\u0638\u0647 {'(پیش‌نمایش)' if is_dry else ''}:\n"
            f"- \u06af\u0631\u0647\u200c\u0647\u0627: {rep.get('initial_memory_count')} -> {rep.get('final_memory_count')}\n"
            f"- \u0647\u0631\u0633 \u0634\u062f\u0647: {rep.get('pruned_nodes_count')} \u06af\u0631\u0647\n"
            f"- \u062a\u0639\u0627\u0631\u0636\u200c\u0647\u0627\u06cc \u062d\u0644\u200c\u0634\u062f\u0647: {rep.get('conflicts_resolved_count')}\n"
            f"- \u06a9\u0627\u0647\u0634 \u0622\u0646\u062a\u0631\u0648\u067e\u06cc: {rep.get('entropy_reduction_pct'):.1f}%\n"
            f"- \u0632\u0645\u0627\u0646 \u0627\u062c\u0631\u0627: {rep.get('duration_ms'):.1f} \u0645\u06cc\u0644\u06cc\u200c\u062b\u0627\u0646\u06cc\u0647"
        )

    if cmd.startswith("/distill_memory"):
        raw = cmd[len("/distill_memory") :].strip()
        if not raw:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0645\u062a\u0646 \u0645\u06a9\u0627\u0644\u0645\u0647 \u0631\u0627 \u0628\u0631\u0627\u06cc \u062a\u0642\u0637\u06cc\u0631 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = consolidation_distill_session(raw)
        return f"\u2728 \u062a\u0642\u0637\u06cc\u0631 \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u0627\u0646\u062c\u0627\u0645 \u0634\u062f: {res.get('distilled_facts_count')} \u0641\u06a9\u062a \u0648 \u0628\u0627\u0648\u0631 \u062c\u062f\u06cc\u062f \u0627\u0633\u062a\u062e\u0631\u0627\u062c \u06af\u0631\u062f\u06cc\u062f."

    if cmd.startswith("/memory_health"):
        parts = cmd.split()
        subcmd = parts[1].lower() if len(parts) > 1 else "report"
        if subcmd == "reset":
            consolidation_reset_all()
            return "\u2705 \u062d\u0627\u0641\u0638\u0647 \u0648 \u062a\u0627\u0631\u06cc\u062e\u0686\u0647 \u062a\u062b\u0628\u06cc\u062a \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."

        res = consolidation_export_report()
        return res.get("markdown_report", "")

    return "\u274c \u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a."
