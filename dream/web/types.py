"""Type definitions and data models for the Web Search and Extraction subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SearchBackendType(str, Enum):
    """Supported web search backends."""

    DUCKDUCKGO = "duckduckgo"
    TAVILY = "tavily"
    BRAVE = "brave"
    FIRECRAWL = "firecrawl"
    MOCK = "mock"


@dataclass
class SearchResultItem:
    """Individual web search result entry."""

    title: str
    url: str
    snippet: str
    score: float = 0.0
    published_date: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize search item to dictionary."""
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "score": self.score,
            "published_date": self.published_date,
            "metadata": self.metadata,
        }


@dataclass
class SearchResponse:
    """Aggregate search response from a search backend."""

    query: str
    backend: SearchBackendType
    results: list[SearchResultItem] = field(default_factory=list)
    total_found: int = 0
    duration_ms: float = 0.0
    error_message: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_success(self) -> bool:
        """Check if search completed without fatal errors."""
        return self.error_message is None

    def to_dict(self) -> dict[str, Any]:
        """Serialize search response to dictionary."""
        return {
            "query": self.query,
            "backend": self.backend.value,
            "total_found": self.total_found,
            "results": [r.to_dict() for r in self.results],
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ExtractedWebContent:
    """Extracted and normalized Markdown web content."""

    url: str
    title: str
    markdown: str
    raw_html_bytes: int
    cleaned_bytes: int
    is_truncated: bool = False
    quarantined_injections: int = 0
    extracted_links: list[str] = field(default_factory=list)
    error_message: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Serialize extracted content to dictionary."""
        return {
            "url": self.url,
            "title": self.title,
            "markdown": self.markdown,
            "raw_html_bytes": self.raw_html_bytes,
            "cleaned_bytes": self.cleaned_bytes,
            "is_truncated": self.is_truncated,
            "quarantined_injections": self.quarantined_injections,
            "extracted_links": self.extracted_links,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
        }
