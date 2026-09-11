"""Slash command handlers for Autonomous Deep Research & Multi-Source Synthesis."""

from __future__ import annotations

from typing import Any

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
            "\U0001f50e \u062f\u0633\u062a\u0648\u0631\u0627\u062a \u067e\u0698\u0648\u0647\u0634 \u0639\u0645\u06cc\u0642 \u0648 \u062a\u062f\u0648\u06cc\u0646 \u06af\u0632\u0627\u0631\u0634 (Deep Research):\n"
            "  /research start <topic>           \u0627\u062c\u0631\u0627\u06cc \u067e\u0698\u0648\u0647\u0634 \u062e\u0648\u062f\u06a9\u0627\u0631 \u0648 \u062a\u0648\u0644\u06cc\u062f \u06af\u0632\u0627\u0631\u0634\n"
            "  /research status <session_id>     \u0628\u0631\u0631\u0633\u06cc \u0648\u0636\u0639\u06cc\u062a \u0648 \u06cc\u0627\u0641\u062a\u0647\u200c\u0647\u0627\u06cc \u0646\u0634\u0633\u062a\n"
            "  /research export <id> [path]      \u0630\u062e\u06cc\u0631\u0647 \u06af\u0632\u0627\u0631\u0634 \u062f\u0631 \u0641\u0627\u06cc\u0644 Markdown\n"
            "  /research list                    \u0641\u0647\u0631\u0633\u062a \u0646\u0634\u0633\u062a\u200c\u0647\u0627\u06cc \u067e\u0698\u0648\u0647\u0634\u06cc"
        )

    subcommand = parts[1].lower()
    arg = parts[2] if len(parts) > 2 else ""

    if subcommand == "list":
        res = research_list_sessions()
        sessions = res.get("sessions", [])
        if not sessions:
            return "\U0001f4cb \u0647\u06cc\u0686 \u0646\u0634\u0633\u062a \u067e\u0698\u0648\u0647\u0634\u06cc \u062b\u0628\u062a \u0646\u0634\u062f\u0647 \u0627\u0633\u062a."
        lines = ["\U0001f4da \u0641\u0647\u0631\u0633\u062a \u0646\u0634\u0633\u062a\u200c\u0647\u0627\u06cc \u067e\u0698\u0648\u0647\u0634 \u0639\u0645\u06cc\u0642:"]
        for s in sessions:
            lines.append(f"  \u2022 [{s['session_id']}] {s['topic']} ({s['status']}) - {s['sources_count']} \u0645\u0646\u0628\u0639")
        return "\n".join(lines)

    if subcommand == "start":
        if not arg:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0645\u0648\u0636\u0648\u0639 \u067e\u0698\u0648\u0647\u0634 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = research_run_autonomous(arg)
        rep = res.get("report", {})
        sid = res.get("session_id", "")
        return (
            f"\u2705 \u067e\u0698\u0648\u0647\u0634 \u0639\u0645\u06cc\u0642 \u0628\u0631\u0627\u06cc '{arg}' \u062a\u06a9\u0645\u06cc\u0644 \u0634\u062f! (ID: {sid})\n"
            f"\U0001f4cb \u0686\u06a9\u06cc\u062f\u0647: {rep.get('executive_summary_fa', '')}\n"
            f"\U0001f4d6 \u062a\u0639\u062f\u0627\u062f \u0645\u0646\u0627\u0628\u0639: {rep.get('total_sources_analyzed', 0)} | "
            f"\u0636\u0631\u06cc\u0628 \u0627\u0637\u0645\u06cc\u0646\u0627\u0646: {rep.get('confidence_level', 0):.2f}"
        )

    if subcommand == "status":
        if not arg:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0634\u0646\u0627\u0633\u0647 \u0646\u0634\u0633\u062a (session_id) \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = research_get_status(arg)
        if not res.get("success"):
            return f"\u274c {res.get('error')}"
        plan = res.get("plan", {})
        return (
            f"\U0001f50e \u0648\u0636\u0639\u06cc\u062a \u0646\u0634\u0633\u062a [{plan.get('session_id')}]:\n"
            f"- \u0645\u0648\u0636\u0648\u0639: {plan.get('topic')}\n"
            f"- \u0648\u0636\u0639\u06cc\u062a: {plan.get('status')}\n"
            f"- \u0645\u0646\u0627\u0628\u0639 \u062c\u0645\u0639\u200c\u0622\u0648\u0631\u06cc\u200c\u0634\u062f\u0647: {plan.get('sources_collected_count')}\n"
            f"- \u06cc\u0627\u0641\u062a\u0647\u200c\u0647\u0627: {plan.get('findings_count')}"
        )

    if subcommand == "export":
        args = arg.split(maxsplit=1)
        if not args:
            return "\u274c \u0634\u0646\u0627\u0633\u0647 \u0646\u0634\u0633\u062a \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        sid = args[0]
        out_path = args[1] if len(args) > 1 else f"data/research_{sid}.md"
        res = research_export_report(sid, out_path)
        if res.get("success"):
            return f"\u2705 \u06af\u0632\u0627\u0631\u0634 \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u062f\u0631 '{out_path}' \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f."
        return f"\u274c \u062e\u0637\u0627 \u062f\u0631 \u0630\u062e\u06cc\u0631\u0647: {res.get('error')}"

    return f"\u274c \u0632\u06cc\u0631\u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0634\u0646\u0627\u062e\u062a\u0647 '{subcommand}'. \u0628\u0631\u0627\u06cc \u0631\u0627\u0647\u0646\u0645\u0627 '/research' \u0631\u0627 \u0628\u0632\u0646\u06cc\u062f."
