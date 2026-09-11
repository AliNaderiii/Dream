"""Deterministic multi-strategy context compression, fast-mode, and budget accounting."""

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
from dream.compression.fast_mode import (
    FastMode,
    FastModeController,
    get_fast_mode_controller,
    reset_fast_mode_controller,
)
from dream.compression.pruner import prune_tool_observations
from dream.compression.slash import handle_compress_command, handle_fast_command
from dream.compression.strategies import (
    BaseCompressionStrategy,
    CodePreservingStrategy,
    CompressionStrategyType,
    HybridStrategy,
    LossyStrategy,
    compress_messages,
)
from dream.compression.summarizer import (
    deterministic_summary,
    extract_persian_timeline,
    generate_structured_summary,
)
from dream.compression.tools import get_insights_report, set_fast_mode

__all__ = [
    "BaseCompressionStrategy",
    "CHARS_PER_TOKEN",
    "CodePreservingStrategy",
    "CompactionResult",
    "CompressionStrategyType",
    "ContextBudget",
    "ContextCompressionEngine",
    "ContextUsage",
    "DEFAULT_ECHO_CONTEXT_TOKENS",
    "DEFAULT_HEADROOM_TOKENS",
    "DEFAULT_MODEL_CONTEXT_TOKENS",
    "DEFAULT_THRESHOLD",
    "DEFAULT_TOOL_PRUNE_THRESHOLD_CHARS",
    "FastMode",
    "FastModeController",
    "HybridStrategy",
    "LossyStrategy",
    "compress_messages",
    "deterministic_summary",
    "estimate_tokens",
    "extract_persian_timeline",
    "generate_structured_summary",
    "get_fast_mode_controller",
    "get_insights_report",
    "handle_compress_command",
    "handle_fast_command",
    "prune_tool_observations",
    "reset_fast_mode_controller",
    "set_fast_mode",
    "split_for_compaction",
    "usage",
]
