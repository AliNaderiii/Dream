"""Errors for the Google Workspace connector."""

from __future__ import annotations


class GwsError(ValueError):
    """User-facing connector failure."""


class GwsSecurityError(GwsError):
    """Fail-closed security refusal."""
