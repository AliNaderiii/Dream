"""Data types and domain models for Dialectic Memory & Self-Reflective Knowledge Graph."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DialecticStatus(str, Enum):
    """Status of a belief or trait in the dialectic graph."""

    ACTIVE = "active"
    CONTRADICTED = "contradicted"
    SUPERSEDED = "superseded"
    NUANCED = "nuanced"


class RelationType(str, Enum):
    """Semantic relation types between nodes in the knowledge graph."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    REFINES = "refines"
    ORIGINATES_FROM = "originates_from"
    CAUSES = "causes"


@dataclass(slots=True)
class BeliefNode:
    """A node in the dialectic graph representing a user belief, preference, or trait."""

    belief_id: str
    domain: str
    statement: str
    confidence: float = 0.8
    status: DialecticStatus = DialecticStatus.ACTIVE
    evidence: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize belief node to dictionary."""
        s_val = (
            self.status.value
            if isinstance(self.status, DialecticStatus)
            else self.status
        )
        return {
            "belief_id": self.belief_id,
            "domain": self.domain,
            "statement": self.statement,
            "confidence": self.confidence,
            "status": s_val,
            "evidence": self.evidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class DialecticRelation:
    """A directed semantic edge between two belief nodes."""

    relation_id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize relation to dictionary."""
        r_val = (
            self.relation_type.value
            if isinstance(self.relation_type, RelationType)
            else self.relation_type
        )
        return {
            "relation_id": self.relation_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": r_val,
            "notes": self.notes,
        }


@dataclass(slots=True)
class DialecticTension:
    """An active contradiction or tension between multiple beliefs requiring reconciliation."""

    tension_id: str
    belief_ids: list[str]
    description: str
    detected_at: float = field(default_factory=time.time)
    resolved: bool = False
    resolution_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize dialectic tension to dictionary."""
        return {
            "tension_id": self.tension_id,
            "belief_ids": self.belief_ids,
            "description": self.description,
            "detected_at": self.detected_at,
            "resolved": self.resolved,
            "resolution_notes": self.resolution_notes,
        }


@dataclass(slots=True)
class DialecticMemorySnapshot:
    """Full snapshot of the dialectic memory and user mental model."""

    nodes_count: int
    tensions_count: int
    unresolved_tensions: int
    top_beliefs: list[dict[str, Any]]
    synthesized_summary: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize snapshot to dictionary."""
        return {
            "nodes_count": self.nodes_count,
            "tensions_count": self.tensions_count,
            "unresolved_tensions": self.unresolved_tensions,
            "top_beliefs": self.top_beliefs,
            "synthesized_summary": self.synthesized_summary,
            "timestamp": self.timestamp,
        }
