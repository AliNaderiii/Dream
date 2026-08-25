"""Error taxonomy for the autonomous research engine.

Everything the engine raises for *expected* failures is a
:class:`ResearchError`. The bridge layer maps it onto ``INVALID_PARAMS`` so a
bad request never leaks a traceback, and the session state machine turns it
into a controlled ``FAILED`` transition rather than a hang.
"""

from __future__ import annotations

__all__ = [
    "ResearchCancelled",
    "ResearchError",
    "ResearchSecurityError",
    "ResearchTimeout",
]


class ResearchError(ValueError):
    """A recoverable, user-facing research failure."""


class ResearchTimeout(ResearchError):
    """A step or a session exceeded its hard deadline."""


class ResearchCancelled(ResearchError):
    """The user (or the supervisor) cancelled the run."""


class ResearchSecurityError(ResearchError):
    """A security guard refused an action (injection, risk tier, traversal)."""
