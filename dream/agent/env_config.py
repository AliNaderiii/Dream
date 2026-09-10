"""``DREAM_*`` environment variable parsing helpers.

Every helper in this module is a pure function that returns a *bounded*
value or the module default. Nothing here raises, logs warnings, or has
side effects beyond a single ``log.warning`` per rejection: a malformed
override must never crash a turn.

The naming convention is consistent: a ``_resolve_*`` helper reads a
single environment variable, a ``_positive_int`` / ``_fraction`` helper
takes a raw string and returns a validated value, and the user-agent
helpers live in :mod:`dream.agent.user_agent` because they also need
the product version.
"""

from __future__ import annotations

from dream.agent.constants import (
    DEFAULT_EXTRACTION_TIMEOUT_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MEMORY_BLOCK_CHAR_LIMIT,
    DEFAULT_RETRY_BACKOFF_SECONDS,
    DEFAULT_TEMPERATURE,
)


def _resolve_temperature(raw: str | None) -> float:
    """Parse ``DREAM_TEMPERATURE``, falling back to the default on any problem.

    Anything unset, non-numeric, or outside the 0.0 to 2.0 band a sampler
    accepts resolves to the default rather than raising mid-turn.
    """
    if not raw:
        return DEFAULT_TEMPERATURE
    try:
        value = float(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_TEMPERATURE
    if not 0.0 <= value <= 2.0:
        return DEFAULT_TEMPERATURE
    return value


def _positive_int(
    raw: str | None, default: int, minimum: int = 1, maximum: int = 1_000_000
) -> int:
    """Parse a bounded positive integer environment setting safely."""
    try:
        value = int(raw or default)
    except (TypeError, ValueError):
        return default
    return value if minimum <= value <= maximum else default


def _fraction(raw: str | None, default: float) -> float:
    """Parse a safe compaction threshold between zero and one."""
    try:
        value = float(raw or default)
    except (TypeError, ValueError):
        return default
    return value if 0.1 <= value < 1.0 else default


def _resolve_memory_block_char_limit(raw: str | None) -> int:
    """Parse ``DREAM_MEMORY_BLOCK_CHAR_LIMIT`` without risking a failed turn."""
    if not raw:
        return DEFAULT_MEMORY_BLOCK_CHAR_LIMIT
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_MEMORY_BLOCK_CHAR_LIMIT
    if not 1 <= value <= 100_000:
        return DEFAULT_MEMORY_BLOCK_CHAR_LIMIT
    return value


def _resolve_max_retries(raw: str | None) -> int:
    """Parse ``DREAM_MAX_RETRIES``, falling back to the default on any problem."""
    if not raw:
        return DEFAULT_MAX_RETRIES
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_MAX_RETRIES
    if not 0 <= value <= 10:
        return DEFAULT_MAX_RETRIES
    return value


def _resolve_retry_backoff(raw: str | None) -> float:
    """Parse ``DREAM_RETRY_BACKOFF_SECONDS``, falling back safely on bad input."""
    if not raw:
        return DEFAULT_RETRY_BACKOFF_SECONDS
    try:
        value = float(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_RETRY_BACKOFF_SECONDS
    if not 0.0 <= value <= 60.0:
        return DEFAULT_RETRY_BACKOFF_SECONDS
    return value


def _resolve_extraction_timeout(raw: str | None) -> float:
    """Parse ``DREAM_EXTRACTION_TIMEOUT_SECONDS``, falling back safely."""
    if not raw:
        return DEFAULT_EXTRACTION_TIMEOUT_SECONDS
    try:
        value = float(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_EXTRACTION_TIMEOUT_SECONDS
    if not 0.1 <= value <= 60.0:
        return DEFAULT_EXTRACTION_TIMEOUT_SECONDS
    return value
