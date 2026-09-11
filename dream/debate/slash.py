"""CLI and slash command handlers for Multi-Agent Debate & Fact-Checking."""

from __future__ import annotations

from typing import Any

from dream.debate.tools import (
    debate_create_session,
    debate_list_sessions,
    debate_reach_consensus,
    debate_reset_all,
    debate_run_autonomous,
    debate_verify_statement,
)


def handle_debate_slash_command(command_str: str) -> str:
    """Handle /debate and /verify slash commands for CLI and REPL.

    Usage:
        /debate <topic>
        /debate list
        /debate status <debate_id>
        /debate reset
        /verify <statement>
    """
    cmd = command_str.strip()

    if cmd.startswith("/verify"):
        statement = cmd[len("/verify") :].strip()
        if not statement:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u06af\u0632\u0627\u0631\u0647 \u06cc\u0627 \u0627\u062f\u0639\u0627 \u0631\u0627 \u0628\u0631\u0627\u06cc \u0631\u0627\u0633\u062a\u06cc\u200c\u0622\u0632\u0645\u0627\u06cc\u06cc \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = debate_verify_statement(statement)
        status = res.get("verification_status", "unverified")
        conf = res.get("confidence", 0.0)
        fallacies = res.get("fallacies", [])

        out = [
            f"\U0001f50e \u0646\u062a\u06cc\u062c\u0647 \u0627\u0631\u0632\u06cc\u0627\u0628\u06cc \u06af\u0632\u0627\u0631\u0647:",
            f"- \u0648\u0636\u0639\u06cc\u062a: `{status}`",
            f"- \u0636\u0631\u06cc\u0628 \u0627\u0637\u0645\u06cc\u0646\u0627\u0646: {conf:.2f}",
        ]
        if fallacies:
            out.append(f"- \u26a0\ufe0f \u0645\u063a\u0627\u0644\u0637\u0627\u062a \u0634\u0646\u0627\u0633\u0627\u06cc\u06cc\u200c\u0634\u062f\u0647: {', '.join(fallacies)}")
        else:
            out.append("- \u2705 \u0647\u06cc\u0686 \u0645\u063a\u0627\u0644\u0637\u0647 \u0645\u0646\u0637\u0642\u06cc \u0634\u0646\u0627\u0633\u0627\u06cc\u06cc \u0646\u0634\u062f.")
        return "\n".join(out)

    if not cmd.startswith("/debate"):
        return "\u274c \u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a."

    parts = cmd.split(maxsplit=2)
    if len(parts) == 1:
        return (
            "\U0001f3db \u062f\u0633\u062a\u0648\u0631\u0627\u062a \u0645\u0646\u0627\u0638\u0631\u0647 \u0686\u0646\u062f-\u0639\u0627\u0645\u0644 (Debate):\n"
            "  /debate <topic>                           \u0627\u062c\u0631\u0627\u06cc \u0645\u0646\u0627\u0638\u0631\u0647 \u062e\u0648\u062f\u06a9\u0627\u0631 \u067e\u06cc\u0631\u0627\u0645\u0648\u0646 \u0645\u0648\u0636\u0648\u0639\n"
            "  /debate list                              \u0641\u0647\u0631\u0633\u062a \u0645\u0646\u0627\u0638\u0631\u0627\u062a \u062b\u0628\u062a\u200c\u0634\u062f\u0647\n"
            "  /debate status <id>                       \u0627\u0631\u0632\u06cc\u0627\u0628\u06cc \u0627\u062c\u0645\u0627\u0639 \u0646\u0634\u0633\u062a\n"
            "  /debate reset                             \u067e\u0627\u06a9\u0633\u0627\u0632\u06cc \u062d\u0627\u0641\u0638\u0647 \u0645\u0646\u0627\u0638\u0631\u0627\u062a\n"
            "  /verify <claim>                           \u0631\u0627\u0633\u062a\u06cc\u200c\u0622\u0632\u0645\u0627\u06cc\u06cc \u0648 \u06a9\u0634\u0641 \u0645\u063a\u0627\u0644\u0637\u0627\u062a"
        )

    subcmd = parts[1].lower()
    arg_rest = parts[2] if len(parts) > 2 else ""

    if subcmd == "list":
        res = debate_list_sessions()
        debates = res.get("debates", [])
        if not debates:
            return "\U0001f4dc \u0647\u06cc\u0686 \u0645\u0646\u0627\u0638\u0631\u0647\u200c\u0627\u06cc \u062b\u0628\u062a \u0646\u0634\u062f\u0647 \u0627\u0633\u062a."
        lines = ["\U0001f3db \u0641\u0647\u0631\u0633\u062a \u0646\u0634\u0633\u062a\u200c\u0647\u0627\u06cc \u0645\u0646\u0627\u0638\u0631\u0647:"]
        for d in debates:
            lines.append(f"- `{d['debate_id']}`: **{d['topic']}** ({d['status']}, \u0627\u0637\u0645\u06cc\u0646\u0627\u0646: {d['confidence_score']})")
        return "\n".join(lines)

    if subcmd == "reset":
        debate_reset_all()
        return "\u2705 \u062d\u0627\u0641\u0638\u0647 \u0645\u0646\u0627\u0638\u0631\u0627\u062a \u067e\u0627\u06a9\u0633\u0627\u0632\u06cc \u0634\u062f."

    if subcmd == "status":
        did = arg_rest.strip()
        if not did:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0634\u0646\u0627\u0633\u0647 \u0645\u0646\u0627\u0638\u0631\u0647 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = debate_reach_consensus(did)
        if not res.get("success"):
            return f"\u274c {res.get('error')}"
        return res.get("summary", "")

    # Treat whole arg as topic for autonomous debate
    topic = cmd[len("/debate") :].strip()
    res = debate_run_autonomous(
        topic=topic,
        proponent_arg=f"\u062f\u0644\u0627\u06cc\u0644 \u0645\u0648\u0627\u0641\u0642 \u067e\u06cc\u0631\u0627\u0645\u0648\u0646 {topic}",
        opponent_arg=f"\u062f\u0644\u0627\u06cc\u0644 \u0645\u0646\u062a\u0642\u062f \u0648 \u0686\u0627\u0644\u0634\u200c\u0647\u0627\u06cc {topic}",
    )
    if res.get("success"):
        return res.get("consensus_summary", "")
    return f"\u274c \u062e\u0637\u0627 \u062f\u0631 \u0627\u062c\u0631\u0627\u06cc \u0645\u0646\u0627\u0638\u0631\u0647: {res.get('error')}"
