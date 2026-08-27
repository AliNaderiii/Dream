"""Errors for HITL page reads."""

from __future__ import annotations


class BrowseError(ValueError):
    """User-facing browse failure."""


class BrowseSecurityError(BrowseError):
    """Fail-closed refusal."""
