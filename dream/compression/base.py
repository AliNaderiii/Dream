"""Core dataclasses, budget calculations, and interfaces for context compression."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CHARS_PER_TOKEN = 4
DEFAULT_ECHO_CONTEXT_TOKENS = 16_384
DEFAULT_MODEL_CONTEXT_TOKENS = 8_192
DEFAULT_THRESHOLD = 0.80
DEFAULT_HEADROOM_TOKENS = 1_024
DEFAULT_TOOL_PRUNE_THRESHOLD_CHARS = 500


@dataclass(frozen=True)
class ContextUsage:
    """Conservative context estimate for an exchange window."""

    tokens: int
    window: int

    @property
    def ratio(self) -> float:
        return self.tokens / self.window if self.window else 1.0

    @property
    def remaining(self) -> int:
        return max(0, self.window - self.tokens)


@dataclass(frozen=True)
class ContextBudget:
    """Detailed token budget allocation across system prompt, history, and generation headroom."""

    total_window: int
    system_tokens: int
    history_tokens: int
    headroom_tokens: int = DEFAULT_HEADROOM_TOKENS
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def used_tokens(self) -> int:
        return self.system_tokens + self.history_tokens

    @property
    def available_for_history(self) -> int:
        return max(0, self.total_window - self.system_tokens - self.headroom_tokens)

    @property
    def is_over_budget(self) -> bool:
        return self.history_tokens > self.available_for_history


@dataclass(frozen=True)
class CompactionResult:
    """Outcome and telemetry from a context compaction cycle."""

    compacted: bool
    reason: str
    tokens_before: int
    tokens_after: int
    dropped_messages_count: int
    pruned_tools_count: int
    summary_text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def tokens_saved(self) -> int:
        return max(0, self.tokens_before - self.tokens_after)
