"""Domain models for associative memories, 4-tier context files, and user personas."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any

KINDS: tuple[str, ...] = ("semantic", "episodic", "procedural")
_MISSING = object()


@dataclass(slots=True)
class Memory:
    """A single distilled memory row."""

    id: int
    kind: str
    content: str
    norm: str
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5
    created_at: float = 0.0
    last_used_at: float = 0.0
    use_count: int = 0
    source: str = ""
    archived: bool = False
    superseded_by: int | None = None
    pinned: bool = False
    score: float = 0.0

    @classmethod
    def from_row(cls, row: sqlite3.Row, score: float = 0.0) -> Memory:
        try:
            tags = json.loads(row["tags"] or "[]")
        except (TypeError, ValueError):
            tags = []
        return cls(
            id=row["id"],
            kind=row["kind"],
            content=row["content"],
            norm=row["norm"],
            tags=list(tags),
            importance=float(row["importance"]),
            created_at=float(row["created_at"]),
            last_used_at=float(row["last_used_at"]),
            use_count=int(row["use_count"]),
            source=row["source"] or "",
            archived=bool(row["archived"]),
            superseded_by=(
                int(row["superseded_by"]) if row["superseded_by"] is not None else None
            ),
            pinned=bool(row["pinned"]),
            score=score,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "content": self.content,
            "tags": list(self.tags),
            "importance": self.importance,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "use_count": self.use_count,
            "source": self.source,
            "archived": self.archived,
            "superseded_by": self.superseded_by,
            "pinned": self.pinned,
            "score": self.score,
        }


@dataclass(slots=True)
class ContextFile:
    """A single character-budgeted Tier-4 context file (SOUL.md, USER.md, MEMORY.md, AGENTS.md)."""

    name: str
    capacity_limit: int
    content: str = ""
    last_updated: float = field(default_factory=time.time)

    @property
    def used_chars(self) -> int:
        return len(self.content)

    @property
    def usage_percent(self) -> float:
        if self.capacity_limit <= 0:
            return 0.0
        return round((self.used_chars / self.capacity_limit) * 100.0, 1)

    @property
    def is_near_capacity(self) -> bool:
        return self.usage_percent >= 90.0

    def capacity_header(self) -> str:
        pct = int(round(self.usage_percent))
        return f"[{self.name.upper()}: {pct}% — {self.used_chars:,}/{self.capacity_limit:,} chars]"


@dataclass(slots=True)
class CapacityReport:
    """Aggregate capacity usage across all Tier-4 context files."""

    files: dict[str, ContextFile] = field(default_factory=dict)

    def total_used(self) -> int:
        return sum(f.used_chars for f in self.files.values())

    def total_capacity(self) -> int:
        return sum(f.capacity_limit for f in self.files.values())

    def format_summary(self) -> str:
        parts = [f.capacity_header() for f in self.files.values()]
        return " ".join(parts)


@dataclass(slots=True)
class UserPersona:
    """Dialectical user model capturing preferences, interaction styles, and context."""

    user_id: str = "local"
    language_preference: str = "fa"
    interaction_style: str = "concise"
    known_facts: list[str] = field(default_factory=list)
    active_projects: list[str] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)

    def render_markdown(self) -> str:
        lines = [
            "# User Profile & Interaction Preferences",
            f"- **Language Preference:** {self.language_preference}",
            f"- **Interaction Style:** {self.interaction_style}",
        ]
        if self.active_projects:
            lines.append("- **Active Projects:** " + ", ".join(self.active_projects))
        if self.known_facts:
            lines.append("## Key Invariants & Facts")
            for fact in self.known_facts:
                lines.append(f"- {fact}")
        return "\n".join(lines)
