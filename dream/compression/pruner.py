"""Observation pruning: folds bulky older tool outputs into concise representations."""

from __future__ import annotations

import copy
from typing import Any

from dream.compression.base import DEFAULT_TOOL_PRUNE_THRESHOLD_CHARS


def prune_tool_observations(
    messages: list[dict[str, Any]],
    *,
    keep_recent_turns: int = 2,
    max_chars: int = DEFAULT_TOOL_PRUNE_THRESHOLD_CHARS,
) -> tuple[list[dict[str, Any]], int, int]:
    """Prune bulky tool results in older turns while preserving recent turns verbatim.

    Returns:
        tuple of (new_messages_list, count_of_pruned_tool_results, total_chars_saved)
    """
    if not messages:
        return [], 0, 0

    # Deepcopy to avoid mutating input history in place
    pruned: list[dict[str, Any]] = [copy.deepcopy(m) for m in messages]

    # Calculate cutoff index: keep the last N user-assistant turns unpruned
    user_indices = [i for i, m in enumerate(pruned) if m.get("role") == "user"]
    cutoff_index = (
        user_indices[-keep_recent_turns]
        if len(user_indices) >= keep_recent_turns
        else 0
    )

    pruned_count = 0
    chars_saved = 0

    for i in range(cutoff_index):
        msg = pruned[i]
        if msg.get("role") == "tool" or msg.get("kind") == "tool_result":
            content = str(msg.get("content") or "")
            if len(content) > max_chars:
                name = str(msg.get("name") or "tool")
                preview = content[: max_chars // 2].rstrip()
                tail = content[-(max_chars // 4) :].lstrip() if max_chars >= 200 else ""
                
                omitted = len(content) - len(preview) - len(tail)
                if tail:
                    new_content = (
                        f"[Tool '{name}' output summary: {preview} ... "
                        f"[omitted {omitted} chars] ... {tail}]"
                    )
                else:
                    new_content = (
                        f"[Tool '{name}' output summary: {preview} ... "
                        f"[omitted {omitted} chars]]"
                    )
                
                chars_saved += max(0, len(content) - len(new_content))
                msg["content"] = new_content
                msg["_pruned"] = True
                pruned_count += 1

    return pruned, pruned_count, chars_saved
