"""Errors for Space-bot groups."""

from __future__ import annotations


class GroupError(ValueError):
    """User-facing group failure."""


class GroupSecurityError(GroupError):
    """Fail-closed refusal."""
