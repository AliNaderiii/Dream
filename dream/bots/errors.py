"""Errors for the Space bot roster."""

from __future__ import annotations


class BotError(ValueError):
    """User-facing bot failure."""


class BotSecurityError(BotError):
    """Fail-closed security refusal."""
