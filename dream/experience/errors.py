"""Errors for experience-to-skill drafts."""

from __future__ import annotations


class ExperienceError(ValueError):
    """User-facing experience failure."""


class ExperienceSecurityError(ExperienceError):
    """Fail-closed refusal."""
