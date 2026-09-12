"""CLI and slash command handlers for Metacognitive Reasoning and Tree-of-Thought."""

from __future__ import annotations

from typing import Any

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
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0645\u0633\u0626\u0644\u0647 \u06cc\u0627 \u0647\u062f\u0641 \u0631\u0627 \u0628\u0631\u0627\u06cc \u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u062f\u0631\u062e\u062a\u06cc \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."

        # Generate standard hypothesis set
        hypotheses = [
            f"\u0631\u0627\u0647\u06a9\u0627\u0631 \u0645\u0633\u062a\u0642\u06cc\u0645 \u0648 \u062a\u062d\u0644\u06cc\u0644\u06cc \u0628\u0631\u0627\u06cc \u062d\u0644 {goal}",
            f"\u0631\u0627\u0647\u06a9\u0627\u0631 \u062a\u062c\u0632\u06cc\u0647 \u0645\u0633\u0626\u0644\u0647 \u0628\u0647 \u0632\u06cc\u0631\u0645\u0633\u0627\u0626\u0644 \u06a9\u0648\u0686\u06a9\u200c\u062a\u0631",
            f"\u0631\u0648\u06cc\u06a9\u0631\u062f \u0627\u062d\u062a\u06cc\u0627\u0637\u06cc \u0648 \u0628\u0631\u0631\u0633\u06cc \u0631\u06cc\u0633\u06a9\u200c\u0647\u0627\u06cc \u0627\u062d\u062a\u0645\u0627\u0644\u06cc",
        ]

        res = reasoning_solve_goal(goal=goal, hypotheses=hypotheses)
        if res.get("success"):
            return res.get("report", "")
        return f"\u274c \u062e\u0637\u0627 \u062f\u0631 \u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u062f\u0631\u062e\u062a\u06cc: {res.get('error')}"

    if not cmd.startswith("/reasoning"):
        return "\u274c \u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a."

    parts = cmd.split(maxsplit=2)
    if len(parts) == 1:
        return (
            "\U0001f9e0 \u062f\u0633\u062a\u0648\u0631\u0627\u062a \u0645\u0648\u062a\u0648\u0631 \u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u0641\u0631\u0627\u0634\u0646\u0627\u062e\u062a\u06cc (Reasoning / ToT):\n"
            "  /think <goal>                             \u062d\u0644 \u0645\u0633\u0626\u0644\u0647 \u0628\u0627 \u062f\u0631\u062e\u062a \u0627\u0633\u062a\u062f\u0644\u0627\u0644 (Tree-of-Thought)\n"
            "  /tot <goal>                               \u0627\u062c\u0631\u0627\u06cc \u06a9\u0627\u0648\u0634 \u0686\u0646\u062f\u200c\u0645\u0633\u06cc\u0631\u0647\n"
            "  /reasoning status                         \u0648\u0636\u0639\u06cc\u062a \u062f\u0631\u062e\u062a\u200c\u0647\u0627\u06cc \u0627\u0633\u062a\u062f\u0644\u0627\u0644\n"
            "  /reasoning reset                          \u067e\u0627\u06a9\u0633\u0627\u0632\u06cc \u0648 \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc"
        )

    subcmd = parts[1].lower()

    if subcmd == "status":
        st = reasoning_get_status()
        return (
            f"\U0001f4df \u0648\u0636\u0639\u06cc\u062a \u0645\u0648\u062a\u0648\u0631 \u0627\u0633\u062a\u062f\u0644\u0627\u0644:\n"
            f"- \u062a\u0639\u062f\u0627\u062f \u062f\u0631\u062e\u062a\u200c\u0647\u0627\u06cc \u0641\u0639\u0627\u0644: {st.get('total_trajectories')}\n"
            f"- \u0634\u0646\u0627\u0633\u0647 \u0645\u0633\u06cc\u0631 \u062c\u0627\u0631\u06cc: {st.get('active_trajectory_id') or '\u0647\u06cc\u0686'}"
        )

    if subcmd == "reset":
        reasoning_reset_all()
        return "\u2705 \u062f\u0631\u062e\u062a\u200c\u0647\u0627\u06cc \u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."

    return "\u274c \u0632\u06cc\u0631\u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a."
