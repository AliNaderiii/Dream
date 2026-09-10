"""Context compression engine orchestrating pruning, budget evaluation, and compaction."""

from __future__ import annotations

from typing import Any

from dream.compression.base import (
    CHARS_PER_TOKEN,
    DEFAULT_HEADROOM_TOKENS,
    DEFAULT_MODEL_CONTEXT_TOKENS,
    DEFAULT_THRESHOLD,
    DEFAULT_TOOL_PRUNE_THRESHOLD_CHARS,
    CompactionResult,
    ContextBudget,
    ContextUsage,
)
from dream.compression.pruner import prune_tool_observations
from dream.compression.summarizer import (
    generate_structured_summary,
)


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate tokens from serialised message content plus role overhead."""
    chars = 0
    for message in messages:
        chars += len(str(message.get("content") or "")) + 12
        chars += len(str(message.get("tool_calls") or ""))
    return max(1, (chars + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def usage(messages: list[dict[str, Any]], window: int) -> ContextUsage:
    """Return ContextUsage containing token estimation and total window."""
    return ContextUsage(estimate_tokens(messages), window)


def split_for_compaction(
    history: list[dict[str, Any]], preserve: int = 4
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep the active exchange intact and compact only completed older items."""
    if len(history) <= preserve:
        return [], list(history)
    return list(history[:-preserve]), list(history[-preserve:])


class ContextCompressionEngine:
    """Two-stage context optimizer: tool result pruning and structured conversation compaction."""

    def __init__(
        self,
        default_window: int = DEFAULT_MODEL_CONTEXT_TOKENS,
        default_threshold: float = DEFAULT_THRESHOLD,
        headroom_tokens: int = DEFAULT_HEADROOM_TOKENS,
    ) -> None:
        self.default_window = default_window
        self.default_threshold = default_threshold
        self.headroom_tokens = headroom_tokens

    def assess_budget(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        window: int | None = None,
    ) -> ContextBudget:
        """Calculate complete token budget across system prompt and dialogue."""
        win = window or self.default_window
        sys_tokens = (len(system_prompt) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN
        hist_tokens = estimate_tokens(messages)
        return ContextBudget(
            total_window=win,
            system_tokens=sys_tokens,
            history_tokens=hist_tokens,
            headroom_tokens=self.headroom_tokens,
        )

    def optimize_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        window: int | None = None,
        threshold: float | None = None,
        keep_messages: int = 4,
        keep_recent_turns: int = 1,
        max_tool_chars: int = DEFAULT_TOOL_PRUNE_THRESHOLD_CHARS,
        enable_tool_pruning: bool = True,
    ) -> tuple[list[dict[str, Any]], CompactionResult]:
        """Perform multi-stage compression: Stage 1 tool pruning + Stage 2 compaction if needed."""
        win = window or self.default_window
        thresh = threshold if threshold is not None else self.default_threshold

        initial_tokens = estimate_tokens(messages)
        pruned_tools_count = 0

        # Stage 1: Prune oversized tool observations in older turns
        working_messages = messages
        if enable_tool_pruning:
            working_messages, pruned_tools_count, _ = prune_tool_observations(
                working_messages,
                keep_recent_turns=keep_recent_turns,
                max_chars=max_tool_chars,
            )

        tokens_after_prune = estimate_tokens(working_messages)
        current_usage = ContextUsage(tokens_after_prune, win)

        # Stage 2: Check if still above compaction threshold
        if current_usage.ratio < thresh:
            # Under budget after stage 1
            return working_messages, CompactionResult(
                compacted=False,
                reason="under_threshold",
                tokens_before=initial_tokens,
                tokens_after=tokens_after_prune,
                dropped_messages_count=0,
                pruned_tools_count=pruned_tools_count,
                summary_text="",
            )

        # Perform split and compaction
        dropped, kept = split_for_compaction(working_messages, preserve=keep_messages)
        if not dropped:
            return working_messages, CompactionResult(
                compacted=False,
                reason="nothing_to_compact",
                tokens_before=initial_tokens,
                tokens_after=tokens_after_prune,
                dropped_messages_count=0,
                pruned_tools_count=pruned_tools_count,
                summary_text="",
            )

        summary = generate_structured_summary(dropped, reason="threshold")
        final_tokens = estimate_tokens(kept) + (len(summary) // CHARS_PER_TOKEN)

        return kept, CompactionResult(
            compacted=True,
            reason="threshold",
            tokens_before=initial_tokens,
            tokens_after=final_tokens,
            dropped_messages_count=len(dropped),
            pruned_tools_count=pruned_tools_count,
            summary_text=summary,
        )
