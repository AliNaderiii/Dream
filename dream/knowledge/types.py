"""Domain types and data models for Multimodal Temporal Knowledge Graph and Entity Linking."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EntityType(str, Enum):
    """Categorical types of entities tracked across modalities."""

    PERSON = "person"
    ORGANIZATION = "organization"
    VENDOR = "vendor"
    DOCUMENT = "document"
    INVOICE = "invoice"
    AUDIO_NOTE = "audio_note"
    TOPIC = "topic"
    PROJECT = "project"
    TRANSACTION = "transaction"
    EVENT = "event"
    LOCATION = "location"
    CONCEPT = "concept"


class RelationType(str, Enum):
    """Semantic and temporal relations connecting entities."""

    ISSUED_BY = "issued_by"
    PAID_TO = "paid_to"
    DISCUSSED_IN = "discussed_in"
    RECORDED_AT = "recorded_at"
    CONTAINS_ITEM = "contains_item"
    BELONGS_TO = "belongs_to"
    EMOTIONAL_TONE = "emotional_tone"
    TEMPORAL_PRECEDES = "temporal_precedes"
    REFERENCES = "references"
    CO_OCCURS_WITH = "co_occurs_with"
    ALIAS_OF = "alias_of"


class ModalityType(str, Enum):
    """Evidence modality source for entities and relationships."""

    TEXT = "text"
    AUDIO = "audio"
    OCR = "ocr"
    CODE = "code"
    STRUCTURED = "structured"


@dataclass(slots=True)
class TemporalInterval:
    """Validity or occurrence time window of an entity or event."""

    valid_from: float = field(default_factory=time.time)
    valid_to: float | None = None
    jalali_date: str = ""

    def is_active_at(self, timestamp: float) -> bool:
        """Check if temporal interval covers the given timestamp."""
        if timestamp < self.valid_from:
            return False
        if self.valid_to is not None and timestamp > self.valid_to:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """Serialize temporal interval to dictionary."""
        return {
            "valid_from": round(self.valid_from, 3),
            "valid_to": round(self.valid_to, 3) if self.valid_to is not None else None,
            "jalali_date": self.jalali_date,
        }


@dataclass(slots=True)
class EntityNode:
    """Multimodal entity node within the temporal knowledge graph."""

    id: str
    name: str
    entity_type: EntityType = EntityType.CONCEPT
    aliases: list[str] = field(default_factory=list)
    modalities: list[ModalityType] = field(default_factory=lambda: [ModalityType.TEXT])
    attributes: dict[str, Any] = field(default_factory=dict)
    temporal: TemporalInterval = field(default_factory=TemporalInterval)
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize entity node to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "entity_type": self.entity_type.value,
            "aliases": self.aliases,
            "modalities": [m.value for m in self.modalities],
            "attributes": self.attributes,
            "temporal": self.temporal.to_dict(),
            "confidence": round(self.confidence, 3),
            "created_at": round(self.created_at, 3),
            "last_seen_at": round(self.last_seen_at, 3),
        }


@dataclass(slots=True)
class RelationEdge:
    """Directed relation edge connecting two multimodal entity nodes."""

    id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    weight: float = 1.0
    timestamp: float = field(default_factory=time.time)
    modality: ModalityType = ModalityType.TEXT
    context_snippet: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize relation edge to dictionary."""
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type.value,
            "weight": round(self.weight, 3),
            "timestamp": round(self.timestamp, 3),
            "modality": self.modality.value,
            "context_snippet": self.context_snippet,
            "confidence": round(self.confidence, 3),
        }


@dataclass(slots=True)
class TemporalTimelineEvent:
    """Chronological event linking multiple multimodal entities."""

    timestamp: float
    jalali_date: str
    entity_id: str
    entity_name: str
    event_type: str
    modality: ModalityType
    description: str
    related_entities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize timeline event to dictionary."""
        return {
            "timestamp": round(self.timestamp, 3),
            "jalali_date": self.jalali_date,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "event_type": self.event_type,
            "modality": self.modality.value,
            "description": self.description,
            "related_entities": self.related_entities,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class TemporalQueryResult:
    """Outcome of a temporal or multimodal knowledge graph query."""

    query: str
    matched_nodes: list[EntityNode] = field(default_factory=list)
    matched_edges: list[RelationEdge] = field(default_factory=list)
    timeline_events: list[TemporalTimelineEvent] = field(default_factory=list)
    summary_narrative: str = ""
    total_matches: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize query result to dictionary."""
        return {
            "query": self.query,
            "matched_nodes": [n.to_dict() for n in self.matched_nodes],
            "matched_edges": [e.to_dict() for e in self.matched_edges],
            "timeline_events": [ev.to_dict() for ev in self.timeline_events],
            "summary_narrative": self.summary_narrative,
            "total_matches": self.total_matches,
        }
