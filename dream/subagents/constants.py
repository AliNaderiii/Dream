"""Constants, hard limits, default budgets, and string utilities for subagents."""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

SUBAGENT_STATUSES: frozenset[str] = frozenset(
    {"idle", "running", "paused", "completed", "failed", "cancelled", "timeout"}
)
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "failed", "cancelled", "timeout"}
)

DEFAULT_MAX_TURNS = 8
DEFAULT_MAX_TOKENS = 20_000
DEFAULT_MAX_DURATION = 120.0
DEFAULT_GRACE_SECONDS = 2.0

# Explicit bounds: every subagent operation is strictly capped.
MAX_PROMPT_CHARS = 16_000
MAX_CONTEXT_CHARS = 32_000
MAX_SYSTEM_PROMPT_CHARS = 8_000
MAX_NAME_CHARS = 120
MAX_TOOL_GRANTS = 32
MAX_TOOL_NAME_CHARS = 100
MAX_TURNS_CAP = 100
MAX_TOKENS_CAP = 200_000
MAX_DURATION_CAP = 3_600.0
MAX_PIPELINE_STAGES = 16
MAX_LOG_ENTRIES = 500
MAX_LOG_MESSAGE_CHARS = 2_000
MAX_RETAINED_SUBAGENTS = 200

DEFAULT_TOOL_GRANT: tuple[str, ...] = (
    "calculate",
    "get_datetime",
    "remember_fact",
    "search_memory",
)

REGISTRY_LOCK = threading.RLock()
_CHARS_PER_TOKEN = 4


def _truncate(text: str, limit: int) -> str:
    """Clamp *text* to *limit* characters with an explicit marker."""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _safe_error(exc: BaseException) -> str:
    """A bounded, secret-free description of a child's failure."""
    from dream.security.secrets import redact_text

    return _truncate(
        redact_text(f"{type(exc).__name__}: {exc}"), MAX_LOG_MESSAGE_CHARS
    )


def estimate_tokens(text: str | None) -> int:
    """Approximate token count from string length (conservative rule of thumb)."""
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)
