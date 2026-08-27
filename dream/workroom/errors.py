"""Errors for the company workroom."""

from __future__ import annotations


class WorkroomError(ValueError):
    """User-facing workroom failure."""


class WorkroomSecurityError(WorkroomError):
    """Fail-closed refusal."""
