"""Domain models and data structures for Interactive Canvas and Visual Artifact Studio."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any


class ArtifactType(str, Enum):
    """Supported artifact formats and interactive components."""

    CODE = "code"
    MARKDOWN = "markdown"
    HTML = "html"
    SVG = "svg"
    MERMAID = "mermaid"
    JSON = "json"
    CSV = "csv"
    REACT_JSX = "react_jsx"
    DIAGRAM = "diagram"


class CanvasExportFormat(str, Enum):
    """Output bundle formats for canvas sessions."""

    HTML_STANDALONE = "html"
    MARKDOWN_BUNDLE = "markdown"
    JSON = "json"


@dataclass(slots=True)
class ArtifactVersion:
    """Historical snapshot of an artifact at a point in time."""

    version_number: int
    content: str
    diff_summary: str = ""
    timestamp: float = field(default_factory=time.time)
    author: str = "assistant"

    def to_dict(self) -> dict[str, Any]:
        """Serialize artifact version to dictionary."""
        return {
            "version_number": self.version_number,
            "content": self.content,
            "diff_summary": self.diff_summary,
            "timestamp": round(self.timestamp, 2),
            "author": self.author,
        }


@dataclass(slots=True)
class CanvasArtifact:
    """Core artifact entity representing code, documentation, or interactive UI."""

    id: str
    title: str
    artifact_type: ArtifactType
    content: str
    language: str = ""
    version: int = 1
    versions: list[ArtifactVersion] = field(default_factory=list)
    description_fa: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize canvas artifact to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "artifact_type": self.artifact_type.value,
            "content": self.content,
            "language": self.language,
            "version": self.version,
            "versions_count": len(self.versions),
            "description_fa": self.description_fa,
            "metadata": self.metadata,
            "created_at": round(self.created_at, 2),
            "updated_at": round(self.updated_at, 2),
        }


@dataclass(slots=True)
class CanvasSession:
    """Container holding active artifacts and visual studio state."""

    session_id: str
    name: str = "default_canvas"
    artifacts: dict[str, CanvasArtifact] = field(default_factory=dict)
    active_artifact_id: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize canvas session to dictionary."""
        return {
            "session_id": self.session_id,
            "name": self.name,
            "total_artifacts": len(self.artifacts),
            "active_artifact_id": self.active_artifact_id,
            "created_at": round(self.created_at, 2),
            "updated_at": round(self.updated_at, 2),
        }
