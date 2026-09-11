"""Data types and domain models for hybrid semantic retrieval and knowledge graph memory."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Entity:
    """A semantic entity in the knowledge graph (e.g. Person, Project, Concept)."""

    id: str
    name: str
    entity_type: str = "concept"  # person, project, tool, preference, concept, organization
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    user_id: str = "default"

    def matches(self, term: str) -> bool:
        """Check if term matches entity name or any alias case-insensitively."""
        t = term.strip().lower()
        if self.name.lower() == t:
            return True
        return any(a.lower() == t for a in self.aliases)


@dataclass(slots=True)
class Relation:
    """A directed semantic edge connecting two entities in the knowledge graph."""

    id: str
    source_id: str
    target_id: str
    relation_type: str  # uses, builds, prefers, belongs_to, works_at, relates_to, depends_on
    weight: float = 1.0
    context: str = ""
    created_at: float = field(default_factory=time.time)
    user_id: str = "default"


@dataclass(slots=True)
class RetrievalScoreBreakdown:
    """Detailed score decomposition for a hybrid search result."""

    sparse_bm25_score: float = 0.0
    sparse_bm25_rank: int = 0
    dense_vector_score: float = 0.0
    dense_vector_rank: int = 0
    rrf_score: float = 0.0
    temporal_multiplier: float = 1.0
    graph_boost: float = 0.0
    final_score: float = 0.0


@dataclass(slots=True)
class RetrievalResult:
    """Ranked search result item returned by the hybrid engine."""

    doc_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    breakdown: RetrievalScoreBreakdown = field(default_factory=RetrievalScoreBreakdown)
    related_entities: list[str] = field(default_factory=list)
    graph_context: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HybridSearchConfig:
    """Configuration tunables for hybrid semantic retrieval and fusion."""

    dense_weight: float = 0.5
    sparse_weight: float = 0.5
    rrf_k: int = 60
    fusion_mode: str = "rrf"  # "rrf" or "linear"
    temporal_decay_half_life_days: float = 30.0
    enable_temporal_decay: bool = True
    graph_hop_limit: int = 2
    min_score_threshold: float = 0.01
