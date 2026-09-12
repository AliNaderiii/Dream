"""Domain models and data structures for Deep Research & Multi-Source Synthesis Engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ResearchStatus(str, Enum):
    """Lifecycle states of a deep research investigation."""

    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceCredibility(str, Enum):
    """Reliability tier of information sources."""

    PRIMARY_ACADEMIC = "primary_academic"
    OFFICIAL_DOCUMENTATION = "official_documentation"
    NEWS_ORGANIZATION = "news_organization"
    EXPERT_ANALYSIS = "expert_analysis"
    COMMUNITY_FORUM = "community_forum"
    UNVERIFIED = "unverified"


@dataclass(slots=True)
class ResearchSource:
    """An external or local information artifact analyzed during research."""

    id: str
    url: str
    title: str
    snippet: str
    credibility: SourceCredibility = SourceCredibility.EXPERT_ANALYSIS
    credibility_score: float = 0.8
    domain: str = ""
    extracted_claims: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize source to dictionary."""
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "credibility": self.credibility.value,
            "credibility_score": round(self.credibility_score, 2),
            "domain": self.domain,
            "extracted_claims": self.extracted_claims,
            "timestamp": round(self.timestamp, 2),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class SourceCitation:
    """Exact inline citation grounding a specific claim."""

    index: int
    source_id: str
    url: str
    title: str
    exact_quote: str = ""
    relevance_score: float = 0.9

    def to_citation_tag(self) -> str:
        """Format standard markdown citation link."""
        return f"[{self.index}]({self.url})"

    def to_dict(self) -> dict[str, Any]:
        """Serialize citation to dictionary."""
        return {
            "index": self.index,
            "source_id": self.source_id,
            "url": self.url,
            "title": self.title,
            "exact_quote": self.exact_quote,
            "relevance_score": round(self.relevance_score, 2),
        }


@dataclass(slots=True)
class ResearchFinding:
    """A substantiated factual finding or verified thesis point."""

    id: str
    sub_topic: str
    claim: str
    evidence_summary: str
    citations: list[SourceCitation] = field(default_factory=list)
    confidence_score: float = 0.85
    contradictions_noted: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize research finding to dictionary."""
        return {
            "id": self.id,
            "sub_topic": self.sub_topic,
            "claim": self.claim,
            "evidence_summary": self.evidence_summary,
            "citations": [c.to_dict() for c in self.citations],
            "confidence_score": round(self.confidence_score, 2),
            "contradictions_noted": self.contradictions_noted,
        }


@dataclass(slots=True)
class ResearchPlan:
    """Structured decomposition and exploration agenda for a research topic."""

    session_id: str
    topic: str
    hypotheses: list[str]
    sub_questions: list[str]
    target_depth: int = 2
    max_sources: int = 15
    sources_collected: list[ResearchSource] = field(default_factory=list)
    findings: list[ResearchFinding] = field(default_factory=list)
    status: ResearchStatus = ResearchStatus.PLANNING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize research plan to dictionary."""
        return {
            "session_id": self.session_id,
            "topic": self.topic,
            "hypotheses": self.hypotheses,
            "sub_questions": self.sub_questions,
            "target_depth": self.target_depth,
            "max_sources": self.max_sources,
            "sources_collected_count": len(self.sources_collected),
            "findings_count": len(self.findings),
            "status": self.status.value,
            "created_at": round(self.created_at, 2),
            "updated_at": round(self.updated_at, 2),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class ResearchReport:
    """Final comprehensive multi-source synthesized intelligence report."""

    session_id: str
    topic: str
    executive_summary_fa: str
    executive_summary_en: str
    key_takeaways: list[str]
    detailed_sections: dict[str, str]  # section title -> markdown content
    bibliography: list[SourceCitation]
    total_sources_analyzed: int
    confidence_level: float
    generated_at: float = field(default_factory=time.time)
    markdown_content: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize full report to dictionary."""
        return {
            "session_id": self.session_id,
            "topic": self.topic,
            "executive_summary_fa": self.executive_summary_fa,
            "executive_summary_en": self.executive_summary_en,
            "key_takeaways": self.key_takeaways,
            "detailed_sections": self.detailed_sections,
            "bibliography": [b.to_dict() for b in self.bibliography],
            "total_sources_analyzed": self.total_sources_analyzed,
            "confidence_level": round(self.confidence_level, 2),
            "generated_at": round(self.generated_at, 2),
            "markdown_content": self.markdown_content,
        }
