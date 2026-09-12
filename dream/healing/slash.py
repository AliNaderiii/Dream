"""CLI and slash command handlers for Self-Healing and Telemetry."""

from __future__ import annotations

from typing import Any

from dream.healing.tools import (
    healing_diagnose_failure,
    healing_run_chaos_test,
    telemetry_export_report,
    telemetry_reset_all,
)


def handle_healing_slash_command(command_str: str) -> str:
    """Handle /heal, /chaos, and /telemetry CLI slash commands.

    Usage:
        /heal <error_description>
        /chaos <fault_type> [target_name]
        /telemetry [report|reset]
    """
    cmd = command_str.strip()

    if cmd.startswith("/heal"):
        err = cmd[len("/heal") :].strip()
        if not err:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0634\u0631\u062d \u062e\u0637\u0627 \u0631\u0627 \u0628\u0631\u0627\u06cc \u062a\u0634\u062e\u06cc\u0635 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = healing_diagnose_failure(err)
        rep = res.get("report", {})
        return (
            f"\U0001fa79 \u0646\u062a\u06cc\u062c\u0647 \u062a\u0634\u062e\u06cc\u0635 \u0648 \u062e\u0648\u062f\u062a\u0631\u0645\u06cc\u0645\u06cc:\n"
            f"- \u0634\u0646\u0627\u0633\u0647: `{rep.get('incident_id')}`\n"
            f"- \u0646\u0648\u0639 \u062e\u0637\u0627: `{rep.get('fault_type')}`\n"
            f"- \u0627\u0642\u062f\u0627\u0645 \u062a\u0631\u0645\u06cc\u0645\u06cc: `{rep.get('action_taken')}`\n"
            f"- \u0632\u0645\u0627\u0646 \u0628\u0627\u0632\u06cc\u0627\u0628\u06cc: {rep.get('recovery_latency_ms'):.1f} \u0645\u06cc\u0644\u06cc\u200c\u062b\u0627\u0646\u06cc\u0647"
        )

    if cmd.startswith("/chaos"):
        parts = cmd.split()
        fault = parts[1] if len(parts) > 1 else "rate_limit"
        target = parts[2] if len(parts) > 2 else "agent_service"
        res = healing_run_chaos_test(fault_type=fault, target_name=target)
        rep = res.get("report", {})
        return (
            f"\u26a1 \u0622\u0632\u0645\u0627\u06cc\u0634 \u0622\u0634\u0648\u0628 (Chaos Test):\n"
            f"- \u062e\u0637\u0627\u06cc \u062a\u0632\u0631\u06cc\u0642\u200c\u0634\u062f\u0647: `{rep.get('fault_type')}` \u0631\u0648\u06cc `{target}`\n"
            f"- \u067e\u0627\u0633\u062e \u0633\u06cc\u0633\u062a\u0645: `{rep.get('action_taken')}` (\u0628\u0627\u0632\u06cc\u0627\u0628\u06cc \u0645\u0648\u0641\u0642 \u2705)"
        )

    if cmd.startswith("/telemetry"):
        parts = cmd.split()
        subcmd = parts[1].lower() if len(parts) > 1 else "report"
        if subcmd == "reset":
            telemetry_reset_all()
            return "\u2705 \u062f\u0627\u062f\u0647\u200c\u0647\u0627\u06cc \u062a\u0644\u0645\u062a\u0631\u06cc \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."

        res = telemetry_export_report()
        return res.get("markdown_report", "")

    return "\u274c \u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a."
