"""Data types and tier models for Layered Context Hierarchy subsystem."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ContextTier(str, Enum):
    """Context hierarchy tiers in decreasing order of priority."""

    SOUL = "soul"
    AGENTS = "agents"
    USER = "user"
    MEMORY = "memory"


@dataclass(slots=True)
class ContextFile:
    """Represents an individual tracked context markdown file."""

    tier: ContextTier
    filename: str
    path: Path
    content: str = ""
    mtime: float = 0.0
    checksum: str = ""
    default_char_budget: int = 2000
    allocated_char_budget: int = 2000
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize context file metadata to dictionary."""
        return {
            "tier": self.tier.value if isinstance(self.tier, ContextTier) else self.tier,
            "filename": self.filename,
            "path": str(self.path),
            "char_length": len(self.content),
            "checksum": self.checksum,
            "default_char_budget": self.default_char_budget,
            "allocated_char_budget": self.allocated_char_budget,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class ContextAssembly:
    """Assembled prompt context combining all prioritized tiers within token budget."""

    rendered_text: str
    tier_lengths: dict[str, int] = field(default_factory=dict)
    total_chars: int = 0
    estimated_tokens: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize assembly output to dictionary."""
        return {
            "rendered_text": self.rendered_text,
            "tier_lengths": self.tier_lengths,
            "total_chars": self.total_chars,
            "estimated_tokens": self.estimated_tokens,
            "timestamp": self.timestamp,
        }
