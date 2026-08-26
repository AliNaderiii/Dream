"""Errors for the Space domain. Fail closed; never guess."""

from __future__ import annotations


class SpaceError(ValueError):
    """Owner-facing Space failure. Message is bilingual when it leaves the kernel."""


class SpaceSecurityError(SpaceError):
    """Traversal, injection, grant widening, or a dangerous action that must not run."""
