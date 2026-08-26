"""Live-loop errors. Fail closed."""

from __future__ import annotations


class LiveLoopError(ValueError):
    """Owner-facing live-loop failure, bilingual when it leaves the kernel."""


class LiveLoopSecurityError(LiveLoopError):
    """Grant widening, dangerous arm, or a live turn that cannot run safely."""
