"""Slash command handlers for Self-Improving Alignment & Preference Subsystem."""

from __future__ import annotations

from typing import Any

from dream.alignment.tools import (
    alignment_critique_and_refine,
    alignment_evaluate_response,
    alignment_export_dataset,
    alignment_get_stats,
    alignment_record_feedback,
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
            "\u2728 \u062f\u0633\u062a\u0648\u0631\u0627\u062a \u062a\u0631\u0627\u0632\u0633\u0627\u0632\u06cc \u0648 \u06cc\u0627\u062f\u06af\u06cc\u0631\u06cc \u062a\u0631\u062c\u06cc\u062d\u0627\u062a (Alignment):\n"
            "  /align stats                      \u06af\u0632\u0627\u0631\u0634 \u0622\u0645\u0627\u0631 \u062a\u0631\u062c\u06cc\u062d\u0627\u062a \u0648 \u067e\u0627\u062f\u0627\u0634\n"
            "  /align score <text>               \u0627\u0631\u0632\u06cc\u0627\u0628\u06cc \u06f6-\u0628\u0639\u062f\u06cc \u067e\u0627\u0633\u062e\n"
            "  /align critique <text>            \u062e\u0648\u062f\u0627\u0646\u062a\u0642\u0627\u062f\u06cc \u0648 \u0628\u0627\u0632\u0646\u0648\u06cc\u0633\u06cc \u0628\u0647\u0628\u0648\u062f\u06cc\u0627\u0641\u062a\u0647\n"
            "  /align export <file_path>         \u062e\u0631\u0648\u062c\u06cc \u062f\u0627\u062f\u0647\u200c\u0647\u0627\u06cc DPO JSONL \u0628\u0631\u0627\u06cc Fine-Tuning"
        )

    subcommand = parts[1].lower()
    arg = parts[2] if len(parts) > 2 else ""

    if subcommand == "stats":
        stats = alignment_get_stats()
        return (
            f"\U0001f4ca \u06af\u0632\u0627\u0631\u0634 \u0645\u062c\u0645\u0648\u0639\u0647 \u062f\u0627\u062f\u0647 \u062a\u0631\u0627\u0632\u0633\u0627\u0632\u06cc:\n"
            f"- \u062a\u0639\u062f\u0627\u062f \u062c\u0641\u062a\u200c\u0647\u0627\u06cc \u062a\u0631\u062c\u06cc\u062d\u06cc DPO: {stats.get('total_pairs', 0)}\n"
            f"- \u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 \u067e\u0627\u062f\u0627\u0634 (Reward): {stats.get('avg_reward_score', 0):.2f}\n"
            f"- \u0622\u0645\u0627\u062f\u0647 \u0635\u0627\u062f\u0631\u0627\u062a: {'\u2705' if stats.get('export_ready') else '\u274c'}"
        )

    if subcommand == "score":
        if not arg:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0645\u062a\u0646 \u067e\u0627\u0633\u062e \u0631\u0627 \u0628\u0631\u0627\u06cc \u0627\u0631\u0632\u06cc\u0627\u0628\u06cc \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = alignment_evaluate_response("User Query", arg)
        scores_str = "\n".join(
            f"  \u2022 {s['dimension']}: {s['score']:.2f} ({s['reasoning']})"
            for s in res.get("scores", [])
        )
        return (
            f"\U0001f3af \u0646\u062a\u06cc\u062c\u0647 \u0627\u0631\u0632\u06cc\u0627\u0628\u06cc \u06f6-\u0628\u0639\u062f\u06cc:\n"
            f"\u067e\u0627\u062f\u0627\u0634 \u06a9\u0644\u06cc: {res.get('composite_reward', 0):.2f}/1.0\n"
            f"{scores_str}"
        )

    if subcommand == "critique":
        if not arg:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0645\u062a\u0646 \u067e\u0627\u0633\u062e \u0631\u0627 \u0628\u0631\u0627\u06cc \u062e\u0648\u062f\u0627\u0646\u062a\u0642\u0627\u062f\u06cc \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = alignment_critique_and_refine("User Query", arg)
        rep = res.get("critique_report", {})
        flaws_str = ", ".join(rep.get("identified_flaws", [])) or "\u0645\u0648\u0631\u062f\u06cc \u06cc\u0627\u0641\u062a \u0646\u0634\u062f"
        return (
            f"\U0001f50d \u06af\u0632\u0627\u0631\u0634 \u062e\u0648\u062f\u0627\u0646\u062a\u0642\u0627\u062f\u06cc:\n"
            f"\u0646\u0642\u0627\u0637 \u0636\u0639\u0641: {flaws_str}\n"
            f"\u067e\u0627\u0633\u062e \u0628\u0647\u0628\u0648\u062f\u06cc\u0627\u0641\u062a\u0647:\n{rep.get('refined_response', '')}"
        )

    if subcommand == "export":
        out_path = arg.strip() or "data/alignment_dpo.jsonl"
        res = alignment_export_dataset(out_path)
        if res.get("success"):
            return f"\u2705 \u062a\u0639\u062f\u0627\u062f {res.get('exported_pairs_count')} \u062c\u0641\u062a \u062a\u0631\u062c\u06cc\u062d\u06cc DPO \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u062f\u0631 '{out_path}' \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f."
        return f"\u274c \u062e\u0637\u0627 \u062f\u0631 \u0635\u0627\u062f\u0631\u0627\u062a: {res.get('error')}"

    return f"\u274c \u0632\u06cc\u0631\u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0634\u0646\u0627\u062e\u062a\u0647 '{subcommand}'. \u0628\u0631\u0627\u06cc \u0631\u0627\u0647\u0646\u0645\u0627 '/align' \u0631\u0627 \u0628\u0632\u0646\u06cc\u062f."
