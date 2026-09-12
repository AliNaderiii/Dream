"""Slash command handlers for Semantic Caching & Token Economics."""

from __future__ import annotations

from typing import Any

from dream.cache.tools import (
    cache_clear,
    cache_get_economics,
    cache_lookup_query,
    cache_warmup,
)


def handle_cache_slash_command(command_str: str) -> str:
    """Handle /cache CLI slash commands.

    Usage:
        /cache stats
        /cache clear
        /cache warmup
        /cache lookup <query>
    """
    parts = command_str.strip().split(maxsplit=2)
    if len(parts) < 2:
        return (
            "\U0001f4be \u062f\u0633\u062a\u0648\u0631\u0627\u062a \u06a9\u0634 \u0645\u0639\u0646\u0627\u06cc\u06cc \u0648 \u0645\u062f\u06cc\u0631\u06cc\u062a \u062a\u0648\u06a9\u0646 (Cache & Token Economics):\n"
            "  /cache stats                      \u06af\u0632\u0627\u0631\u0634 \u0622\u0645\u0627\u0631 \u0635\u0631\u0641\u0647\u200c\u062c\u0648\u06cc\u06cc \u062a\u0648\u06a9\u0646 \u0648 \u0647\u0632\u06cc\u0646\u0647\n"
            "  /cache clear                      \u067e\u0627\u06a9\u0633\u0627\u0632\u06cc \u062d\u0627\u0641\u0638\u0647 \u06a9\u0634\n"
            "  /cache warmup                     \u0622\u0645\u0627\u062f\u0647\u200c\u0633\u0627\u0632\u06cc \u067e\u0627\u0633\u062e\u200c\u0647\u0627\u06cc \u067e\u06cc\u0634\u200c\u0641\u0631\u0636\n"
            "  /cache lookup <query>             \u062c\u0633\u062a\u062c\u0648\u06cc \u0645\u0639\u0646\u0627\u06cc\u06cc \u062f\u0631 \u06a9\u0634"
        )

    subcommand = parts[1].lower()
    arg = parts[2] if len(parts) > 2 else ""

    if subcommand == "stats":
        econ = cache_get_economics()
        hits = econ.get("total_hits", 0)
        reqs = econ.get("total_requests", 0)
        ratio = econ.get("hit_ratio", 0.0) * 100
        tokens = econ.get("total_tokens_saved", 0)
        cost = econ.get("estimated_cost_saved_usd", 0.0)
        latency = econ.get("total_latency_saved_ms", 0.0) / 1000.0

        return (
            f"\U0001f4ca \u06af\u0632\u0627\u0631\u0634 \u0627\u0642\u062a\u0635\u0627\u062f \u062a\u0648\u06a9\u0646 \u0648 \u06a9\u0634 \u0645\u0639\u0646\u0627\u06cc\u06cc:\n"
            f"- \u062a\u0639\u062f\u0627\u062f \u062f\u0631\u062e\u0648\u0627\u0633\u062a\u200c\u0647\u0627: {reqs} (\u0627\u0635\u0627\u0628\u062a\u200c\u0647\u0627: {hits} | \u0646\u0631\u062e \u0627\u0635\u0627\u0628\u062a: {ratio:.1f}%)\n"
            f"- \u062a\u0648\u06a9\u0646\u200c\u0647\u0627\u06cc \u0635\u0631\u0641\u0647\u200c\u062c\u0648\u06cc\u06cc\u200c\u0634\u062f\u0647: {tokens:,} \u062a\u0648\u06a9\u0646\n"
            f"- \u06a9\u0627\u0647\u0634 \u062a\u0627\u062e\u06cc\u0631 (Latency Saved): {latency:.2f} \u062b\u0627\u0646\u06cc\u0647\n"
            f"- \u0635\u0631\u0641\u0647\u200c\u062c\u0648\u06cc\u06cc \u0645\u0627\u0644\u06cc \u062a\u062e\u0645\u06cc\u0646\u06cc: ${cost:.4f} USD\n"
            f"- \u062a\u0639\u062f\u0627\u062f \u067e\u0627\u0633\u062e\u200c\u0647\u0627\u06cc \u0641\u0639\u0627\u0644 \u062f\u0631 \u06a9\u0634: {econ.get('active_entries_count', 0)}"
        )

    if subcommand == "clear":
        res = cache_clear()
        return f"\u2705 \u062d\u0627\u0641\u0638\u0647 \u06a9\u0634 \u067e\u0627\u06a9\u0633\u0627\u0632\u06cc \u0634\u062f. ({res.get('cleared_entries_count', 0)} \u0645\u0648\u0631\u062f \u062d\u0630\u0641 \u06af\u0631\u062f\u06cc\u062f)"

    if subcommand == "warmup":
        res = cache_warmup()
        return f"\u2705 \u062a\u0639\u062f\u0627\u062f {res.get('warmed_up_count', 0)} \u067e\u0627\u0633\u062e \u067e\u06cc\u0634\u200c\u0641\u0631\u0636 \u062f\u0631 \u06a9\u0634 \u0628\u0627\u0631\u06af\u0630\u0627\u0631\u06cc \u0634\u062f."

    if subcommand == "lookup":
        if not arg:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0639\u0628\u0627\u0631\u062a \u062c\u0633\u062a\u062c\u0648 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = cache_lookup_query(arg)
        if res.get("hit"):
            return (
                f"\U0001f3af \u0627\u0635\u0627\u0628\u062a \u0628\u0647 \u06a9\u0634 ({res.get('tier')} - \u0634\u0628\u0627\u0647\u062a: {res.get('similarity_score', 0):.2f}):\n"
                f"{res.get('response')}"
            )
        return "\u274c \u0645\u0648\u0631\u062f\u06cc \u062f\u0631 \u06a9\u0634 \u06cc\u0627\u0641\u062a \u0646\u0634\u062f (Cache Miss)."

    return f"\u274c \u0632\u06cc\u0631\u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0634\u0646\u0627\u062e\u062a\u0647 '{subcommand}'. \u0628\u0631\u0627\u06cc \u0631\u0627\u0647\u0646\u0645\u0627 '/cache' \u0631\u0627 \u0628\u0632\u0646\u06cc\u062f."
