"""Dream Context Compression & Compaction System."""

from __future__ import annotations

from dream.compression.base import (
    CHARS_PER_TOKEN,
    DEFAULT_ECHO_CONTEXT_TOKENS,
    DEFAULT_HEADROOM_TOKENS,
    DEFAULT_MODEL_CONTEXT_TOKENS,
    DEFAULT_THRESHOLD,
    DEFAULT_TOOL_PRUNE_THRESHOLD_CHARS,
    CompactionResult,
    ContextBudget,
    ContextUsage,
)
from dream.compression.engine import (
    ContextCompressionEngine,
    estimate_tokens,
    split_for_compaction,
    usage,
)
from dream.compression.pruner import prune_tool_observations
from dream.compression.summarizer import (
    deterministic_summary,
    extract_persian_timeline,
    generate_structured_summary,
)

__all__ = [
    "CHARS_PER_TOKEN",
    "CompactionResult",
    "ContextBudget",
    "ContextCompressionEngine",
    "ContextUsage",
    "DEFAULT_ECHO_CONTEXT_TOKENS",
    "DEFAULT_HEADROOM_TOKENS",
    "DEFAULT_MODEL_CONTEXT_TOKENS",
    "DEFAULT_THRESHOLD",
    "DEFAULT_TOOL_PRUNE_THRESHOLD_CHARS",
    "deterministic_summary",
    "estimate_tokens",
    "extract_persian_timeline",
    "generate_structured_summary",
    "prune_tool_observations",
    "split_for_compaction",
    "usage",
]
