#!/usr/bin/env python3
"""Standalone installer for Phase 28 (Multimodal Temporal Knowledge Graph, Timeline Reasoning & Entity Linking).

Applies:
- `dream/knowledge/types.py`
- `dream/knowledge/graph.py`
- `dream/knowledge/engine.py`
- `dream/knowledge/tools.py`
- `dream/knowledge/slash.py`
- `dream/knowledge/__init__.py`
- `dream/tools/toolsets.py`
- `tests/test_temporal_knowledge_graph.py`
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

FILES = {
    "dream/knowledge/types.py": r'''"""Domain types and data models for Multimodal Temporal Knowledge Graph and Entity Linking."""

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
''',
    "dream/knowledge/graph.py": r'''"""Multimodal Temporal Knowledge Graph Memory Structure and Graph Traversal."""

from __future__ import annotations

import collections
import json
import time
import uuid
from pathlib import Path
from typing import Any

from dream.knowledge.types import (
    EntityNode,
    EntityType,
    ModalityType,
    RelationEdge,
    RelationType,
    TemporalInterval,
    TemporalTimelineEvent,
)
from dream.security.pathsafety import is_sensitive_path

PERSIAN_NORM_MAP = str.maketrans({
    "ي": "ی",
    "ك": "ک",
    "ة": "ه",
    "۰": "0",
    "۱": "1",
    "۲": "2",
    "۳": "3",
    "۴": "4",
    "۵": "5",
    "۶": "6",
    "۷": "7",
    "۸": "8",
    "۹": "9",
    "\u200c": " ",  # ZWNJ to space for index matching
})


def normalize_entity_key(text: str) -> str:
    """Normalize text key for robust entity indexing and lookup."""
    return text.translate(PERSIAN_NORM_MAP).strip().lower()


class MultimodalTemporalGraph:
    """In-memory multi-indexed temporal knowledge graph for cross-modal entities."""

    def __init__(self) -> None:
        self._nodes: dict[str, EntityNode] = {}
        self._name_index: dict[str, str] = {}  # normalized_name -> node_id
        self._type_index: dict[EntityType, set[str]] = collections.defaultdict(set)
        self._modality_index: dict[ModalityType, set[str]] = collections.defaultdict(set)

        self._edges: dict[str, RelationEdge] = {}
        self._edges_out: dict[str, list[str]] = collections.defaultdict(list)  # src_id -> edge_ids
        self._edges_in: dict[str, list[str]] = collections.defaultdict(list)  # tgt_id -> edge_ids

        self._timeline_events: list[TemporalTimelineEvent] = []

    def add_node(
        self,
        name: str,
        entity_type: EntityType = EntityType.CONCEPT,
        aliases: list[str] | None = None,
        modalities: list[ModalityType] | None = None,
        attributes: dict[str, Any] | None = None,
        temporal: TemporalInterval | None = None,
        confidence: float = 1.0,
        node_id: str | None = None,
    ) -> EntityNode:
        """Insert or update an entity node in the multimodal graph."""
        norm_key = normalize_entity_key(name)
        existing_id = self._name_index.get(norm_key)

        now = time.time()
        mod_list = modalities or [ModalityType.TEXT]
        alias_list = aliases or []
        attr_dict = attributes or {}
        temp_interval = temporal or TemporalInterval(valid_from=now)

        if existing_id and existing_id in self._nodes:
            # Merge into existing node
            existing = self._nodes[existing_id]
            merged_aliases = list(set(existing.aliases + alias_list))
            merged_modalities = list(set(existing.modalities + mod_list))
            merged_attrs = {**existing.attributes, **attr_dict}

            # Update indices for new aliases
            for alias in alias_list:
                self._name_index[normalize_entity_key(alias)] = existing_id

            for m in mod_list:
                self._modality_index[m].add(existing_id)

            existing.aliases = merged_aliases
            existing.modalities = merged_modalities
            existing.attributes = merged_attrs
            existing.last_seen_at = now
            existing.confidence = max(existing.confidence, confidence)
            return existing

        # Create brand new node
        nid = node_id or f"node_{uuid.uuid4().hex[:10]}"
        node = EntityNode(
            id=nid,
            name=name.strip(),
            entity_type=entity_type,
            aliases=alias_list,
            modalities=mod_list,
            attributes=attr_dict,
            temporal=temp_interval,
            confidence=confidence,
            created_at=now,
            last_seen_at=now,
        )

        self._nodes[nid] = node
        self._name_index[norm_key] = nid
        for alias in alias_list:
            self._name_index[normalize_entity_key(alias)] = nid

        self._type_index[entity_type].add(nid)
        for m in mod_list:
            self._modality_index[m].add(nid)

        return node

    def get_node(self, node_id: str) -> EntityNode | None:
        """Retrieve entity node by its unique identifier."""
        return self._nodes.get(node_id)

    def find_node(self, name_or_alias: str) -> EntityNode | None:
        """Find entity node by exact name or alias matching."""
        norm_key = normalize_entity_key(name_or_alias)
        nid = self._name_index.get(norm_key)
        if nid and nid in self._nodes:
            return self._nodes[nid]

        # Partial fallback matching
        for k, v_id in self._name_index.items():
            if norm_key in k or k in norm_key:
                if v_id in self._nodes:
                    return self._nodes[v_id]
        return None

    def add_edge(
        self,
        source: str | EntityNode,
        target: str | EntityNode,
        relation_type: RelationType,
        weight: float = 1.0,
        modality: ModalityType = ModalityType.TEXT,
        context_snippet: str = "",
        timestamp: float | None = None,
        confidence: float = 1.0,
        edge_id: str | None = None,
    ) -> RelationEdge:
        """Create a directed relation edge between two entities."""
        src_node = (
            source
            if isinstance(source, EntityNode)
            else (self.find_node(source) or self.add_node(source))
        )
        tgt_node = (
            target
            if isinstance(target, EntityNode)
            else (self.find_node(target) or self.add_node(target))
        )

        edge_time = timestamp if timestamp is not None else time.time()

        # Check existing edge
        for eid in self._edges_out.get(src_node.id, []):
            edge = self._edges.get(eid)
            if edge and edge.target_id == tgt_node.id and edge.relation_type == relation_type:
                edge.weight = max(edge.weight, weight)
                edge.timestamp = max(edge.timestamp, edge_time)
                if context_snippet:
                    edge.context_snippet = context_snippet
                return edge

        eid = edge_id or f"edge_{uuid.uuid4().hex[:10]}"
        edge = RelationEdge(
            id=eid,
            source_id=src_node.id,
            target_id=tgt_node.id,
            relation_type=relation_type,
            weight=weight,
            timestamp=edge_time,
            modality=modality,
            context_snippet=context_snippet,
            confidence=confidence,
        )

        self._edges[eid] = edge
        self._edges_out[src_node.id].append(eid)
        self._edges_in[tgt_node.id].append(eid)

        return edge

    def add_timeline_event(
        self,
        entity: str | EntityNode,
        event_type: str,
        modality: ModalityType,
        description: str,
        jalali_date: str = "",
        related_entities: list[str] | None = None,
        timestamp: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TemporalTimelineEvent:
        """Record a chronological event attached to an entity."""
        node = (
            entity
            if isinstance(entity, EntityNode)
            else (self.find_node(entity) or self.add_node(entity))
        )

        ev_time = timestamp if timestamp is not None else time.time()
        event = TemporalTimelineEvent(
            timestamp=ev_time,
            jalali_date=jalali_date,
            entity_id=node.id,
            entity_name=node.name,
            event_type=event_type,
            modality=modality,
            description=description,
            related_entities=related_entities or [],
            metadata=metadata or {},
        )
        self._timeline_events.append(event)
        # Keep events sorted chronologically
        self._timeline_events.sort(key=lambda x: x.timestamp)
        return event

    def query_k_hop(
        self,
        root_name: str,
        max_hops: int = 2,
    ) -> list[dict[str, Any]]:
        """Traverse k-hop neighborhood from root entity."""
        root = self.find_node(root_name)
        if not root:
            return []

        visited: set[str] = {root.id}
        queue: collections.deque[tuple[str, int]] = collections.deque([(root.id, 0)])
        paths: list[dict[str, Any]] = []

        while queue:
            curr_id, hop = queue.popleft()
            if hop >= max_hops:
                continue

            curr_node = self._nodes.get(curr_id)
            curr_name = curr_node.name if curr_node else curr_id

            for eid in self._edges_out.get(curr_id, []):
                edge = self._edges.get(eid)
                if not edge:
                    continue
                tgt_node = self._nodes.get(edge.target_id)
                tgt_name = tgt_node.name if tgt_node else edge.target_id

                paths.append({
                    "source": curr_name,
                    "relation": edge.relation_type.value,
                    "target": tgt_name,
                    "hop": hop + 1,
                    "weight": edge.weight,
                    "modality": edge.modality.value,
                    "context": edge.context_snippet,
                    "timestamp": edge.timestamp,
                })

                if edge.target_id not in visited:
                    visited.add(edge.target_id)
                    queue.append((edge.target_id, hop + 1))

        return paths

    def query_timeline(
        self,
        start_time: float | None = None,
        end_time: float | None = None,
        entity_name: str | None = None,
        modalities: list[ModalityType] | None = None,
        limit: int = 50,
    ) -> list[TemporalTimelineEvent]:
        """Query timeline events filtered by timestamp range, entity, and modality."""
        results = []
        target_node = self.find_node(entity_name) if entity_name else None

        for ev in self._timeline_events:
            if start_time is not None and ev.timestamp < start_time:
                continue
            if end_time is not None and ev.timestamp > end_time:
                continue
            if target_node:
                matches_id = ev.entity_id == target_node.id
                matches_rel = target_node.name in ev.related_entities
                if not (matches_id or matches_rel):
                    continue
            if modalities and ev.modality not in modalities:
                continue

            results.append(ev)
            if len(results) >= limit:
                break

        return results

    def get_stats(self) -> dict[str, Any]:
        """Compute statistical summary of graph nodes, edges, and modalities."""
        mod_counts = {m.value: len(nodes) for m, nodes in self._modality_index.items()}
        type_counts = {t.value: len(nodes) for t, nodes in self._type_index.items()}

        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "total_timeline_events": len(self._timeline_events),
            "modalities_distribution": mod_counts,
            "entity_types_distribution": type_counts,
        }

    def export_json(self, file_path: str) -> None:
        """Export serialized knowledge graph to JSON file with path safety check."""
        if is_sensitive_path(file_path):
            raise PermissionError(f"Permission denied: '{file_path}' is a sensitive system path.")

        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges.values()],
            "timeline_events": [ev.to_dict() for ev in self._timeline_events],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def import_json(self, file_path: str) -> None:
        """Load serialized knowledge graph from JSON file."""
        if is_sensitive_path(file_path):
            raise PermissionError(f"Permission denied: '{file_path}' is a sensitive system path.")

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Knowledge graph file '{file_path}' not found.")

        data = json.loads(path.read_text(encoding="utf-8"))

        for n in data.get("nodes", []):
            raw_type = n.get("entity_type", "concept")
            e_type = (
                EntityType(raw_type)
                if raw_type in [e.value for e in EntityType]
                else EntityType.CONCEPT
            )
            mods = [
                ModalityType(m)
                for m in n.get("modalities", [])
                if m in [x.value for x in ModalityType]
            ]
            temp_d = n.get("temporal", {})
            temp = TemporalInterval(
                valid_from=temp_d.get("valid_from", time.time()),
                valid_to=temp_d.get("valid_to"),
                jalali_date=temp_d.get("jalali_date", ""),
            )
            self.add_node(
                name=n["name"],
                entity_type=e_type,
                aliases=n.get("aliases", []),
                modalities=mods,
                attributes=n.get("attributes", {}),
                temporal=temp,
                confidence=n.get("confidence", 1.0),
                node_id=n.get("id"),
            )

        for e in data.get("edges", []):
            raw_rel = e.get("relation_type", "references")
            r_type = (
                RelationType(raw_rel)
                if raw_rel in [r.value for r in RelationType]
                else RelationType.REFERENCES
            )
            raw_mod = e.get("modality", "text")
            mod = (
                ModalityType(raw_mod)
                if raw_mod in [x.value for x in ModalityType]
                else ModalityType.TEXT
            )
            self.add_edge(
                source=self._nodes.get(e["source_id"], e["source_id"]),
                target=self._nodes.get(e["target_id"], e["target_id"]),
                relation_type=r_type,
                weight=e.get("weight", 1.0),
                modality=mod,
                context_snippet=e.get("context_snippet", ""),
                timestamp=e.get("timestamp"),
                confidence=e.get("confidence", 1.0),
                edge_id=e.get("id"),
            )

        for ev in data.get("timeline_events", []):
            raw_mod = ev.get("modality", "text")
            mod = (
                ModalityType(raw_mod)
                if raw_mod in [x.value for x in ModalityType]
                else ModalityType.TEXT
            )
            self.add_timeline_event(
                entity=ev.get("entity_name") or ev.get("entity_id", ""),
                event_type=ev.get("event_type", "event"),
                modality=mod,
                description=ev.get("description", ""),
                jalali_date=ev.get("jalali_date", ""),
                related_entities=ev.get("related_entities", []),
                timestamp=ev.get("timestamp"),
                metadata=ev.get("metadata", {}),
            )
''',
    "dream/knowledge/engine.py": r'''"""Temporal Knowledge Graph Engine, Jalali Date Alignment & Cross-Modal Reasoning."""

from __future__ import annotations

import re
import time
from typing import Any

from dream.knowledge.graph import MultimodalTemporalGraph, normalize_entity_key
from dream.knowledge.types import (
    EntityNode,
    EntityType,
    ModalityType,
    RelationType,
    TemporalInterval,
    TemporalQueryResult,
)


def jalali_to_timestamp(jalali_str: str) -> float:
    """Convert Jalali date string (e.g. '1403/06/25' or '1403-06-25') to Unix timestamp."""
    digits_normalized = jalali_str.translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    )
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", digits_normalized)
    if not m:
        return time.time()

    jy, jm, jd = int(m.group(1)), int(m.group(2)), int(m.group(3))

    # Approximate epoch conversion for Jalali 1348-1450 (1348 SH approx 1970 AD)
    if jm <= 6:
        day_of_year = (jm - 1) * 31 + jd
    else:
        day_of_year = 6 * 31 + (jm - 7) * 30 + jd

    # 1348/10/11 is approx 1970-01-01 (Unix Epoch)
    total_days = int((jy - 1348) * 365.242) + day_of_year - 287
    return max(0.0, total_days * 86400.0)


def timestamp_to_jalali(ts: float) -> str:
    """Convert Unix timestamp to approximate Jalali date string (YYYY/MM/DD)."""
    days = int(ts / 86400.0) + 287
    jy = 1348 + int(days / 365.242)
    day_in_year = int(days % 365.242)

    if day_in_year <= 186:
        jm = max(1, min(6, int(day_in_year / 31) + 1))
        jd = max(1, min(31, int(day_in_year % 31) + 1))
    else:
        rem = day_in_year - 186
        jm = max(7, min(12, int(rem / 30) + 7))
        jd = max(1, min(30, int(rem % 30) + 1))

    return f"{jy:04d}/{jm:02d}/{jd:02d}"


class TemporalKnowledgeEngine:
    """Orchestrates cross-modal entity linking, temporal indexing, and multi-hop queries."""

    def __init__(self, graph: MultimodalTemporalGraph | None = None) -> None:
        self.graph = graph or MultimodalTemporalGraph()

    def ingest_ocr_result(
        self,
        ocr_data: Any,
        artifact_id: str = "",
    ) -> list[EntityNode]:
        """Extract and link entities, transactions, and temporal events from OCR result."""
        fields: dict[str, Any] = {}
        cleaned_text: str = ""
        file_path: str = ""

        if hasattr(ocr_data, "to_dict"):
            d = ocr_data.to_dict()
            fields = d.get("extracted_fields", {})
            cleaned_text = d.get("cleaned_text", "")
            file_path = d.get("file_path", "")
        elif isinstance(ocr_data, dict):
            fields = ocr_data.get("extracted_fields", {})
            cleaned_text = ocr_data.get("cleaned_text", "")
            file_path = ocr_data.get("file_path", "")
        elif isinstance(ocr_data, str):
            cleaned_text = ocr_data

        nodes_created: list[EntityNode] = []
        now = time.time()

        # 1. Parse Date and Temporal Interval
        jalali_str = fields.get("date", "")
        ts = jalali_to_timestamp(jalali_str) if jalali_str else now
        if not jalali_str:
            jalali_str = timestamp_to_jalali(ts)

        temporal = TemporalInterval(valid_from=ts, jalali_date=jalali_str)

        # 2. Document/Invoice Node
        clean_name = file_path.replace("\\", "/").split("/")[-1] if file_path else ""
        doc_label = (
            f"\u0633\u0646\u062f OCR: {clean_name}"
            if clean_name
            else "\u0633\u0646\u062f \u0627\u0633\u06a9\u0646 \u0634\u062f\u0647"
        )
        is_invoice = "total_amount" in fields
        doc_node = self.graph.add_node(
            name=doc_label,
            entity_type=EntityType.INVOICE if is_invoice else EntityType.DOCUMENT,
            modalities=[ModalityType.OCR],
            attributes={
                "file_path": file_path,
                "tracking_code": fields.get("tracking_code", ""),
                "iban": fields.get("iban", ""),
                "total_amount": fields.get("total_amount"),
                "tax": fields.get("tax"),
            },
            temporal=temporal,
        )
        nodes_created.append(doc_node)

        # 3. Vendor / Organization Node
        vendor_name = fields.get("vendor", "").strip()
        if vendor_name:
            vendor_node = self.graph.add_node(
                name=vendor_name,
                entity_type=EntityType.VENDOR,
                modalities=[ModalityType.OCR, ModalityType.TEXT],
                attributes={"iban": fields.get("iban", "")},
                temporal=temporal,
            )
            nodes_created.append(vendor_node)
            self.graph.add_edge(
                source=doc_node,
                target=vendor_node,
                relation_type=RelationType.ISSUED_BY,
                modality=ModalityType.OCR,
                context_snippet=cleaned_text[:120],
                timestamp=ts,
            )

        # 4. Financial Transaction Node
        if "total_amount" in fields:
            t_amt = fields["total_amount"]
            tx_name = (
                f"\u062a\u0631\u0627\u06a9\u0646\u0634: "
                f"{t_amt} \u062a\u0648\u0645\u0627\u0646"
            )
            tx_node = self.graph.add_node(
                name=tx_name,
                entity_type=EntityType.TRANSACTION,
                modalities=[ModalityType.OCR, ModalityType.STRUCTURED],
                attributes={
                    "amount": fields["total_amount"],
                    "tax": fields.get("tax", 0),
                    "tracking_code": fields.get("tracking_code", ""),
                    "iban": fields.get("iban", ""),
                },
                temporal=temporal,
            )
            nodes_created.append(tx_node)
            self.graph.add_edge(
                source=doc_node,
                target=tx_node,
                relation_type=RelationType.CONTAINS_ITEM,
                modality=ModalityType.OCR,
                timestamp=ts,
            )

        # 5. Record Chronological Timeline Event
        v_title = vendor_name or doc_label
        amt_str = str(fields.get("total_amount", "\u0646\u0627\u0645\u0634\u062e\u0635"))
        desc = (
            f"\u0627\u0633\u062a\u062e\u0631\u0627\u062c \u0633\u0646\u062f OCR \u0627\u0632 "
            f"{v_title} \u0628\u0647 \u0645\u0628\u0644\u063a {amt_str}"
        )
        self.graph.add_timeline_event(
            entity=doc_node,
            event_type="ocr_extraction",
            modality=ModalityType.OCR,
            description=desc,
            jalali_date=jalali_str,
            related_entities=[n.name for n in nodes_created if n.id != doc_node.id],
            timestamp=ts,
            metadata={"fields": fields},
        )

        return nodes_created

    def ingest_speech_result(
        self,
        speech_data: Any,
        speaker_name: str = "\u06a9\u0627\u0631\u0628\u0631",
        artifact_id: str = "",
    ) -> list[EntityNode]:
        """Extract and link entities, vocal emotions, and events from Speech results."""
        text: str = ""
        duration: float = 0.0
        audio_path: str = ""
        emotion: str = "neutral"
        blend_d: dict[str, Any] | None = None

        if hasattr(speech_data, "to_dict"):
            d = speech_data.to_dict()
            text = d.get("text", "")
            duration = d.get("duration", d.get("duration_seconds", 0.0))
            audio_path = d.get("audio_path", "")
            emotion = d.get("overall_emotion", d.get("emotion_applied", "neutral"))
            blend_d = d.get("emotion_blend")
        elif isinstance(speech_data, dict):
            text = speech_data.get("text", "")
            duration = speech_data.get("duration", speech_data.get("duration_seconds", 0.0))
            audio_path = speech_data.get("audio_path", "")
            emotion = speech_data.get("overall_emotion") or speech_data.get(
                "emotion_applied", "neutral"
            )
            blend_d = speech_data.get("emotion_blend")
        elif isinstance(speech_data, str):
            text = speech_data

        nodes_created: list[EntityNode] = []
        now = time.time()
        jalali_str = timestamp_to_jalali(now)
        temporal = TemporalInterval(valid_from=now, jalali_date=jalali_str)

        # 1. Speaker Person Node
        speaker_node = self.graph.add_node(
            name=speaker_name,
            entity_type=EntityType.PERSON,
            modalities=[ModalityType.AUDIO, ModalityType.TEXT],
            temporal=temporal,
        )
        nodes_created.append(speaker_node)

        # 2. Audio Note Node
        snippet = text[:25]
        note_name = (
            f"\u06cc\u0627\u062f\u062f\u0627\u0634\u062a \u0635\u0648\u062a\u06cc: {snippet}..."
            if snippet
            else "\u0641\u0627\u06cc\u0644 \u0635\u0648\u062a\u06cc"
        )
        audio_node = self.graph.add_node(
            name=note_name,
            entity_type=EntityType.AUDIO_NOTE,
            modalities=[ModalityType.AUDIO],
            attributes={
                "audio_path": audio_path,
                "duration": duration,
                "transcription": text,
                "emotion": emotion,
                "emotion_blend": blend_d,
            },
            temporal=temporal,
        )
        nodes_created.append(audio_node)

        # Edge: AudioNote -> Speaker
        self.graph.add_edge(
            source=audio_node,
            target=speaker_node,
            relation_type=RelationType.DISCUSSED_IN,
            modality=ModalityType.AUDIO,
            context_snippet=text[:100],
            timestamp=now,
        )

        # 3. Emotion Node
        emotion_node = self.graph.add_node(
            name=f"\u062d\u0627\u0644\u062a \u0627\u062d\u0633\u0627\u0633\u06cc: {emotion}",
            entity_type=EntityType.CONCEPT,
            modalities=[ModalityType.AUDIO],
            attributes={"emotion_name": emotion, "blend": blend_d},
            temporal=temporal,
        )
        nodes_created.append(emotion_node)

        self.graph.add_edge(
            source=audio_node,
            target=emotion_node,
            relation_type=RelationType.EMOTIONAL_TONE,
            modality=ModalityType.AUDIO,
            timestamp=now,
        )

        # 4. Record Timeline Event
        snip60 = text[:60]
        desc = (
            f"\u062b\u0628\u062a \u06af\u0641\u062a\u0627\u0631 "
            f"\u0635\u0648\u062a\u06cc \u062a\u0648\u0633\u0637 {speaker_name} "
            f"\u0628\u0627 \u0627\u062d\u0633\u0627\u0633 [{emotion}]: \"{snip60}\""
        )
        self.graph.add_timeline_event(
            entity=audio_node,
            event_type="speech_interaction",
            modality=ModalityType.AUDIO,
            description=desc,
            jalali_date=jalali_str,
            related_entities=[speaker_node.name, emotion_node.name],
            timestamp=now,
            metadata={"duration": duration, "text": text},
        )

        return nodes_created

    def ingest_text_entity(
        self,
        name: str,
        entity_type: EntityType = EntityType.CONCEPT,
        aliases: list[str] | None = None,
        attributes: dict[str, Any] | None = None,
        valid_from_jalali: str = "",
    ) -> EntityNode:
        """Manually add or update text-based entity."""
        ts = jalali_to_timestamp(valid_from_jalali) if valid_from_jalali else time.time()
        j_str = valid_from_jalali or timestamp_to_jalali(ts)
        temp = TemporalInterval(valid_from=ts, jalali_date=j_str)

        return self.graph.add_node(
            name=name,
            entity_type=entity_type,
            aliases=aliases,
            modalities=[ModalityType.TEXT],
            attributes=attributes or {},
            temporal=temp,
        )

    def query_temporal_knowledge(
        self,
        query: str,
        entity_types: list[EntityType] | None = None,
        start_jalali: str = "",
        end_jalali: str = "",
        limit: int = 20,
    ) -> TemporalQueryResult:
        """Run cross-modal temporal search and narrative synthesis across knowledge graph."""
        start_ts = jalali_to_timestamp(start_jalali) if start_jalali else None
        end_ts = jalali_to_timestamp(end_jalali) if end_jalali else None

        norm_q = normalize_entity_key(query)

        # 1. Matched Nodes
        matched_nodes: list[EntityNode] = []
        for node in self.graph._nodes.values():
            if entity_types and node.entity_type not in entity_types:
                continue

            node_key = normalize_entity_key(node.name)
            alias_match = any(norm_q in normalize_entity_key(a) for a in node.aliases)
            attr_match = any(norm_q in str(v).lower() for v in node.attributes.values())
            if norm_q in node_key or alias_match or attr_match:
                matched_nodes.append(node)

        # 2. Matched Timeline Events
        events = self.graph.query_timeline(
            start_time=start_ts,
            end_time=end_ts,
            entity_name=query if matched_nodes else None,
            limit=limit,
        )

        # 3. Matched Edges
        matched_edges: list[Any] = []
        matched_ids = {n.id for n in matched_nodes}
        for edge in self.graph._edges.values():
            if edge.source_id in matched_ids or edge.target_id in matched_ids:
                matched_edges.append(edge)

        # 4. Synthesize Story Narrative
        narrative_lines = [
            f"\U0001f50d \u0646\u062a\u0627\u06cc\u062c \u062c\u0633\u062a\u062c\u0648\u06cc "
            f"\u06af\u0631\u0627\u0641 \u062f\u0627\u0646\u0634 \u0632\u0645\u0627\u0646\u06cc "
            f"(\u06a9\u0644\u06cc\u062f\u0648\u0627\u0698\u0647: '{query}'):",
        ]
        if matched_nodes:
            cnt_n = len(matched_nodes)
            f_hdr = (
                f"\u2022 \u062a\u0639\u062f\u0627\u062f {cnt_n} "
                f"\u0645\u0648\u062c\u0648\u062f\u06cc\u062a "
                f"(Entity) \u06cc\u0627\u0641\u062a \u0634\u062f:"
            )
            narrative_lines.append(f_hdr)
            for n in matched_nodes[:5]:
                mods = ",".join(m.value for m in n.modalities)
                narrative_lines.append(f"   - [{n.entity_type.value}] {n.name} (Modality: {mods})")

        if events:
            cnt_e = len(events)
            ev_hdr = (
                f"\u2022 \u062a\u0627\u06cc\u0645\u200c\u0644\u0627\u06cc\u0646 "
                f"\u0631\u0648\u06cc\u062f\u0627\u062f\u0647\u0627 "
                f"({cnt_e} \u0645\u0648\u0631\u062f):"
            )
            narrative_lines.append(ev_hdr)
            for ev in events[:5]:
                j_d = ev.jalali_date or "N/A"
                narrative_lines.append(f"   [{j_d}] ({ev.modality.value}) {ev.description}")

        narrative = "\n".join(narrative_lines)

        return TemporalQueryResult(
            query=query,
            matched_nodes=matched_nodes,
            matched_edges=matched_edges,
            timeline_events=events,
            summary_narrative=narrative,
            total_matches=len(matched_nodes) + len(events),
        )
''',
    "dream/knowledge/tools.py": r'''"""LLM Tool bindings for Multimodal Temporal Knowledge Graph and Entity Linking."""

from __future__ import annotations

from typing import Any

from dream.knowledge.engine import TemporalKnowledgeEngine
from dream.knowledge.types import EntityType, RelationType

_GLOBAL_KNOWLEDGE_ENGINE: TemporalKnowledgeEngine | None = None


def get_global_knowledge_engine() -> TemporalKnowledgeEngine:
    """Get or initialize singleton TemporalKnowledgeEngine."""
    global _GLOBAL_KNOWLEDGE_ENGINE
    if _GLOBAL_KNOWLEDGE_ENGINE is None:
        _GLOBAL_KNOWLEDGE_ENGINE = TemporalKnowledgeEngine()
    return _GLOBAL_KNOWLEDGE_ENGINE


def reset_global_knowledge_engine() -> None:
    """Reset TemporalKnowledgeEngine singleton instance."""
    global _GLOBAL_KNOWLEDGE_ENGINE
    _GLOBAL_KNOWLEDGE_ENGINE = None


def knowledge_add_entity(
    name: str,
    entity_type: str = "concept",
    aliases: list[str] | str = "",
    attributes: dict[str, Any] | None = None,
    valid_from_jalali: str = "",
) -> dict[str, Any]:
    """Add or update an entity node in the temporal knowledge graph."""
    engine = get_global_knowledge_engine()

    e_type = EntityType.CONCEPT
    try:
        e_type = EntityType(entity_type.lower())
    except ValueError:
        pass

    alias_list: list[str] = []
    if isinstance(aliases, list):
        alias_list = aliases
    elif isinstance(aliases, str) and aliases:
        alias_list = [a.strip() for a in aliases.split(",") if a.strip()]

    node = engine.ingest_text_entity(
        name=name,
        entity_type=e_type,
        aliases=alias_list,
        attributes=attributes or {},
        valid_from_jalali=valid_from_jalali,
    )
    return {"success": True, "entity": node.to_dict()}


def knowledge_add_relation(
    source_name: str,
    target_name: str,
    relation_type: str = "references",
    context_snippet: str = "",
    weight: float = 1.0,
) -> dict[str, Any]:
    """Create a directed relationship between two entities."""
    engine = get_global_knowledge_engine()

    r_type = RelationType.REFERENCES
    try:
        r_type = RelationType(relation_type.lower())
    except ValueError:
        pass

    edge = engine.graph.add_edge(
        source=source_name,
        target=target_name,
        relation_type=r_type,
        weight=weight,
        context_snippet=context_snippet,
    )
    return {"success": True, "relation": edge.to_dict()}


def knowledge_query_temporal(
    query: str,
    entity_types: list[str] | None = None,
    start_jalali: str = "",
    end_jalali: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Query multimodal knowledge graph using keywords, Persian dates, or entity types."""
    engine = get_global_knowledge_engine()

    parsed_types: list[EntityType] | None = None
    if entity_types:
        parsed_types = []
        for t in entity_types:
            try:
                parsed_types.append(EntityType(t.lower()))
            except ValueError:
                pass

    res = engine.query_temporal_knowledge(
        query=query,
        entity_types=parsed_types,
        start_jalali=start_jalali,
        end_jalali=end_jalali,
        limit=limit,
    )
    return {"success": True, **res.to_dict()}


def knowledge_get_entity_timeline(
    entity_name: str,
    limit: int = 50,
) -> dict[str, Any]:
    """Retrieve chronological events and relationship history for a specific entity."""
    engine = get_global_knowledge_engine()
    events = engine.graph.query_timeline(entity_name=entity_name, limit=limit)
    k_hop = engine.graph.query_k_hop(entity_name, max_hops=2)

    return {
        "success": True,
        "entity_name": entity_name,
        "timeline_events": [ev.to_dict() for ev in events],
        "relationships": k_hop,
    }


def knowledge_link_multimodal_artifact(
    artifact_type: str,
    artifact_data: dict[str, Any] | str,
) -> dict[str, Any]:
    """Ingest and link OCR, Speech, or Text multimodal artifacts into the graph."""
    engine = get_global_knowledge_engine()
    a_type = artifact_type.lower().strip()

    if a_type in ("ocr", "invoice", "document"):
        nodes = engine.ingest_ocr_result(artifact_data)
        return {
            "success": True,
            "artifact_type": "ocr",
            "linked_nodes": [n.to_dict() for n in nodes],
        }
    elif a_type in ("speech", "audio", "stt", "tts"):
        nodes = engine.ingest_speech_result(artifact_data)
        return {
            "success": True,
            "artifact_type": "speech",
            "linked_nodes": [n.to_dict() for n in nodes],
        }
    else:
        # Default text entity
        if isinstance(artifact_data, str):
            name = artifact_data
        else:
            name = artifact_data.get("name", "")
        node = engine.ingest_text_entity(name)
        return {
            "success": True,
            "artifact_type": "text",
            "linked_nodes": [node.to_dict()],
        }


def knowledge_get_stats() -> dict[str, Any]:
    """Get overall statistics and modality distribution of the knowledge graph."""
    engine = get_global_knowledge_engine()
    return {"success": True, **engine.graph.get_stats()}


def get_knowledge_tools() -> list[Any]:
    """Return Knowledge Graph tool functions for agent registration."""
    return [
        knowledge_add_entity,
        knowledge_add_relation,
        knowledge_query_temporal,
        knowledge_get_entity_timeline,
        knowledge_link_multimodal_artifact,
        knowledge_get_stats,
    ]
''',
    "dream/knowledge/slash.py": r'''"""Interactive slash command handler for Multimodal Temporal Knowledge Graph."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.knowledge.tools import (
    knowledge_get_entity_timeline,
    knowledge_get_stats,
    knowledge_query_temporal,
)


def handle_knowledge_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/kg` or `/knowledge` slash command in interactive REPL or TUI."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors

    parts = cmd_text.strip().split(maxsplit=2)
    subcmd = parts[1].lower() if len(parts) > 1 else "stats"

    if subcmd in ("stats", "status", "info"):
        res = knowledge_get_stats()
        title = (
            "\U0001f4ca "
            "\u0622\u0645\u0627\u0631 "
            "\u06af\u0631\u0627\u0641 "
            "\u062f\u0627\u0646\u0634 \u0632\u0645\u0627\u0646\u06cc "
            "(Temporal KG):"
        )
        output(cm.bold(title))
        output(
            f"  \u2022 \u062a\u0639\u062f\u0627\u062f "
            f"\u06af\u0631\u0647\u200c\u0647\u0627 (Nodes): {res.get('total_nodes', 0)}"
        )
        output(
            f"  \u2022 \u062a\u0639\u062f\u0627\u062f "
            f"\u06cc\u0627\u0644\u200c\u0647\u0627 (Edges): {res.get('total_edges', 0)}"
        )
        output(
            f"  \u2022 \u0631\u0648\u06cc\u062f\u0627\u062f\u0647\u0627\u06cc "
            f"\u0632\u0645\u0627\u0646\u06cc (Timeline Events): "
            f"{res.get('total_timeline_events', 0)}"
        )
        mod_dist = res.get("modalities_distribution", {})
        m_lbl = (
            "\u062a\u0648\u0632\u06cc\u0639 "
            "\u0645\u0648\u062f\u0627\u0644\u06cc\u062a\u0647\u0627:"
        )
        output(f"  \u2022 {m_lbl} {mod_dist}")
        return True

    if subcmd in ("query", "search", "q"):
        if len(parts) < 3:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0639\u0628\u0627\u0631\u062a "
                "\u062c\u0633\u062a\u062c\u0648 \u0631\u0627 "
                "\u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        q_text = parts[2]
        res = knowledge_query_temporal(q_text)
        narrative = res.get("summary_narrative", "")
        if narrative:
            output(cm.green(narrative))
        else:
            no_match = (
                "\u2717 \u0645\u0648\u0631\u062f\u06cc "
                "\u06cc\u0627\u0641\u062a \u0646\u0634\u062f."
            )
            output(cm.yellow(no_match))
        return True

    if subcmd in ("timeline", "events", "t"):
        if len(parts) < 3:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0646\u0627\u0645 \u0645\u0648\u062c\u0648\u062f\u06cc\u062a "
                "\u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        ent_name = parts[2]
        res = knowledge_get_entity_timeline(ent_name)
        events = res.get("timeline_events", [])
        cnt_ev = len(events)
        title = (
            f"\U0001f4c5 \u062a\u0627\u06cc\u0645\u200c\u0644\u0627\u06cc\u0646 "
            f"\u0632\u0645\u0627\u0646\u06cc: {ent_name} "
            f"({cnt_ev} \u0631\u0648\u06cc\u062f\u0627\u062f)"
        )
        output(cm.bold(title))
        for ev in events:
            j_date = ev.get("jalali_date") or "N/A"
            mod = ev.get("modality", "text")
            output(f"  \u2022 [{j_date}] ({mod}) {ev.get('description')}")
        return True

    # Help
    h_title = (
        "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
        "\u062f\u0633\u062a\u0648\u0631 /kg:"
    )
    output(cm.bold(h_title))
    output(
        "  /kg stats                           - "
        "\u0622\u0645\u0627\u0631 \u06af\u0631\u0627\u0641 \u062f\u0627\u0646\u0634 / KG Statistics"
    )
    output(
        "  /kg query <text>                    - "
        "\u062c\u0633\u062a\u062c\u0648\u06cc \u0632\u0645\u0627\u0646\u06cc / Temporal Search"
    )
    output(
        "  /kg timeline <entity>               - "
        "\u062a\u0627\u06cc\u0645\u200c\u0644\u0627\u06cc\u0646 / Entity Timeline"
    )
    return True
''',
    "dream/knowledge/__init__.py": r'''"""Multimodal Temporal Knowledge Graph, Entity Linking, and Timeline Reasoning Subsystem."""

from .engine import (
    TemporalKnowledgeEngine,
    jalali_to_timestamp,
    timestamp_to_jalali,
)
from .graph import MultimodalTemporalGraph, normalize_entity_key
from .slash import handle_knowledge_command
from .tools import (
    get_global_knowledge_engine,
    get_knowledge_tools,
    knowledge_add_entity,
    knowledge_add_relation,
    knowledge_get_entity_timeline,
    knowledge_get_stats,
    knowledge_link_multimodal_artifact,
    knowledge_query_temporal,
    reset_global_knowledge_engine,
)
from .types import (
    EntityNode,
    EntityType,
    ModalityType,
    RelationEdge,
    RelationType,
    TemporalInterval,
    TemporalQueryResult,
    TemporalTimelineEvent,
)

__all__ = [
    "EntityNode",
    "EntityType",
    "ModalityType",
    "MultimodalTemporalGraph",
    "RelationEdge",
    "RelationType",
    "TemporalInterval",
    "TemporalKnowledgeEngine",
    "TemporalQueryResult",
    "TemporalTimelineEvent",
    "get_global_knowledge_engine",
    "get_knowledge_tools",
    "handle_knowledge_command",
    "jalali_to_timestamp",
    "knowledge_add_entity",
    "knowledge_add_relation",
    "knowledge_get_entity_timeline",
    "knowledge_get_stats",
    "knowledge_link_multimodal_artifact",
    "knowledge_query_temporal",
    "normalize_entity_key",
    "reset_global_knowledge_engine",
    "timestamp_to_jalali",
]
''',
    "dream/tools/toolsets.py": r'''"""Toolset categorization, grouping, and dynamic tool management."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from dream.tools.base import REGISTRY, Tool


@dataclass(frozen=True)
class Toolset:
    """Group of related tools identified by name."""

    name: str
    description: str
    tools: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


# Default built-in toolsets matching Dream's core capabilities
BUILTIN_TOOLSETS: dict[str, Toolset] = {
    "core": Toolset(
        name="core",
        description="Fundamental utilities (datetime, math calculation)",
        tools=("get_datetime", "calculate"),
    ),
    "workspace": Toolset(
        name="workspace",
        description="Workspace note inspection and editing",
        tools=("read_note", "list_notes", "write_note"),
    ),
    "web": Toolset(
        name="web",
        description="Public internet search and page fetching",
        tools=("search_web", "read_page"),
    ),
    "skills": Toolset(
        name="skills",
        description="Reusable skill management, hub discovery, and autonomous evolution",
        tools=(
            "save_skill",
            "use_skill",
            "list_skills",
            "skill_view",
            "edit_skill",
            "delete_skill",
            "save_skill_bundle",
            "apply_skill_proposal",
            "discard_skill_proposal",
            "hub_search_skills",
            "hub_install_skill",
            "skill_evolve_optimize",
            "skill_export_bundle",
            "skill_import_bundle",
        ),
    ),
    "reminders": Toolset(
        name="reminders",
        description="Scheduled reminders and tasks",
        tools=("create_reminder", "cancel_reminder"),
    ),
    "system": Toolset(
        name="system",
        description="System commands and external communication",
        tools=("run_shell", "send_email"),
    ),
    "mcp": Toolset(
        name="mcp",
        description="Model Context Protocol servers, discovery, and tool execution",
        tools=(
            "mcp_list_servers",
            "mcp_list_tools",
            "mcp_call_tool",
            "mcp_read_resource",
            "mcp_reload",
        ),
    ),
    "subagents": Toolset(
        name="subagents",
        description="Multi-agent orchestration, delegation, and worker lifecycle",
        tools=(
            "subagent_spawn",
            "subagent_wait",
            "subagent_delegate_task",
            "subagent_list",
            "subagent_terminate",
        ),
    ),
    "scheduler": Toolset(
        name="scheduler",
        description="Autonomous cron scheduling, reminders, and multi-channel delivery",
        tools=(
            "schedule_task",
            "list_schedules",
            "cancel_schedule",
            "trigger_schedule",
        ),
    ),
    "retrieval": Toolset(
        name="retrieval",
        description="Hybrid semantic retrieval and knowledge graph memory association",
        tools=(
            "search_hybrid_memory",
            "query_knowledge_graph",
        ),
    ),
    "distill": Toolset(
        name="distill",
        description="Autonomous trajectory recording, distillation, and evaluation benchmarks",
        tools=(
            "distill_record_trajectory",
            "distill_export_dataset",
            "eval_run_benchmark",
        ),
    ),
    "profiles": Toolset(
        name="profiles",
        description="Multi-profile persona scoping and isolated workspace management",
        tools=(
            "profile_list",
            "profile_get_current",
            "profile_switch",
            "profile_create",
        ),
    ),
    "context": Toolset(
        name="context",
        description="Prioritized context files (SOUL, AGENTS, USER, MEMORY) and budgeting",
        tools=(
            "context_get_tier",
            "context_update_tier",
            "context_get_budget_report",
            "context_assemble_prompt",
            "context_reload_all",
        ),
    ),
    "terminal": Toolset(
        name="terminal",
        description="Multi-backend isolated execution (Local, Docker, SSH, Cloud Sandboxes)",
        tools=(
            "terminal_execute",
            "terminal_list_backends",
            "terminal_switch_backend",
        ),
    ),
    "browser": Toolset(
        name="browser",
        description="Multi-driver browser control, DOM extraction, and visual interaction",
        tools=(
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_screenshot",
            "browser_extract_content",
            "browser_close",
            "browser_get_status",
        ),
    ),
    "dialectic": Toolset(
        name="dialectic",
        description="Self-reflective dialectic user modeling and knowledge synthesis",
        tools=(
            "dialectic_observe",
            "dialectic_reflect",
            "dialectic_get_belief_graph",
            "dialectic_reconcile",
            "dialectic_query_traits",
        ),
    ),
    "acp": Toolset(
        name="acp",
        description="Agent Client Protocol (ACP) IDE integration and diff tools",
        tools=(
            "acp_apply_diff",
            "acp_read_diagnostics",
            "acp_get_session_status",
            "acp_list_agents",
            "acp_call_agent",
        ),
    ),
    "plugins": Toolset(
        name="plugins",
        description="Dynamic plugin installation, lifecycle management, and extension hooks",
        tools=(
            "plugin_list",
            "plugin_install",
            "plugin_enable",
            "plugin_disable",
            "plugin_get_info",
        ),
    ),
    "swarm": Toolset(
        name="swarm",
        description="Distributed swarm orchestration, DAG task execution, and consensus",
        tools=(
            "swarm_spawn_node",
            "swarm_plan_workflow",
            "swarm_execute_step",
            "swarm_run_all",
            "swarm_reach_consensus",
            "swarm_get_status",
            "swarm_broadcast_message",
        ),
    ),
    "speech": Toolset(
        name="speech",
        description="Voice synthesis (TTS), recognition (STT), and HybridEmo emotion modeling",
        tools=(
            "speech_text_to_speech",
            "speech_speech_to_text",
            "speech_analyze_voice_emotion",
            "speech_list_voices",
        ),
    ),
    "ocr": Toolset(
        name="ocr",
        description="Persian document OCR, receipt parsing, and invoice field extraction",
        tools=(
            "ocr_extract_document",
            "ocr_extract_invoice",
        ),
    ),
    "knowledge": Toolset(
        name="knowledge",
        description=(
            "Multimodal temporal knowledge graph, timeline reasoning, "
            "and cross-modal entity linking"
        ),
        tools=(
            "knowledge_add_entity",
            "knowledge_add_relation",
            "knowledge_query_temporal",
            "knowledge_get_entity_timeline",
            "knowledge_link_multimodal_artifact",
            "knowledge_get_stats",
        ),
    ),
}

_TOOLSETS: dict[str, Toolset] = dict(BUILTIN_TOOLSETS)


def register_toolset(
    name: str,
    tools: Collection[str],
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> Toolset:
    """Register a new named toolset or update an existing one."""
    toolset = Toolset(
        name=name,
        description=description,
        tools=tuple(sorted(set(tools))),
        metadata=metadata or {},
    )
    _TOOLSETS[name] = toolset
    return toolset


def unregister_toolset(name: str) -> bool:
    """Remove a registered toolset (returns True if removed)."""
    if name in _TOOLSETS:
        del _TOOLSETS[name]
        return True
    return False


def get_toolset(name: str) -> Toolset | None:
    """Return a Toolset by name, or None if not registered."""
    return _TOOLSETS.get(name)


def list_toolsets() -> list[Toolset]:
    """Return a list of all registered Toolsets."""
    return list(_TOOLSETS.values())


def filter_tools(
    toolsets: Collection[str] | None = None,
    include_tools: Collection[str] | None = None,
    exclude_tools: Collection[str] | None = None,
    registry: Mapping[str, Tool] | None = None,
) -> dict[str, Tool]:
    """Filter registered tools by toolset names and explicit inclusions/exclusions."""
    source = REGISTRY if registry is None else registry

    if toolsets is None and include_tools is None and exclude_tools is None:
        return dict(source)

    allowed_names: set[str] = set()

    if toolsets is not None:
        for ts_name in toolsets:
            ts = _TOOLSETS.get(ts_name)
            if ts:
                allowed_names.update(ts.tools)

    if include_tools is not None:
        allowed_names.update(include_tools)

    if toolsets is None and include_tools is None:
        allowed_names.update(source.keys())

    if exclude_tools is not None:
        allowed_names.difference_update(exclude_tools)

    return {name: tool for name, tool in source.items() if name in allowed_names}
''',
    "tests/test_temporal_knowledge_graph.py": r'''"""Comprehensive tests for Multimodal Temporal Knowledge Graph and Entity Linking."""

from __future__ import annotations

import tempfile
from pathlib import Path

from dream.knowledge import (
    EntityType,
    ModalityType,
    MultimodalTemporalGraph,
    RelationType,
    TemporalInterval,
    TemporalKnowledgeEngine,
    get_knowledge_tools,
    handle_knowledge_command,
    jalali_to_timestamp,
    knowledge_add_entity,
    knowledge_add_relation,
    knowledge_get_entity_timeline,
    knowledge_get_stats,
    knowledge_link_multimodal_artifact,
    knowledge_query_temporal,
    reset_global_knowledge_engine,
    timestamp_to_jalali,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


def test_temporal_types_and_jalali_conversion():
    # Jalali conversion test
    j_date = "1403/06/25"
    ts = jalali_to_timestamp(j_date)
    assert ts > 0.0
    converted_back = timestamp_to_jalali(ts)
    assert converted_back.startswith("1403/06")

    # Interval test
    interval = TemporalInterval(valid_from=ts, jalali_date=j_date)
    assert interval.is_active_at(ts + 100) is True
    assert interval.is_active_at(ts - 1000) is False
    d_int = interval.to_dict()
    assert d_int["jalali_date"] == j_date


def test_multimodal_temporal_graph_operations():
    graph = MultimodalTemporalGraph()

    # Add Node with aliases and modalities
    node1 = graph.add_node(
        name="شرکت فناوری دریم",
        entity_type=EntityType.ORGANIZATION,
        aliases=["دریم تک", "Dream Tech"],
        modalities=[ModalityType.TEXT, ModalityType.OCR],
    )
    assert node1.name == "شرکت فناوری دریم"
    assert "Dream Tech" in node1.aliases
    assert ModalityType.OCR in node1.modalities

    # Alias lookup
    found = graph.find_node("Dream Tech")
    assert found is not None
    assert found.id == node1.id

    # Add second node & edge
    node2 = graph.add_node(
        name="پروژه دستیار هوشمند",
        entity_type=EntityType.PROJECT,
        modalities=[ModalityType.TEXT],
    )
    edge = graph.add_edge(
        source=node1,
        target=node2,
        relation_type=RelationType.BELONGS_TO,
        weight=1.5,
        modality=ModalityType.TEXT,
        context_snippet="توسعه فازهای پیشرفته",
    )
    assert edge.source_id == node1.id
    assert edge.target_id == node2.id
    assert edge.weight == 1.5

    # k-hop query
    k_hops = graph.query_k_hop("شرکت فناوری دریم", max_hops=2)
    assert len(k_hops) == 1
    assert k_hops[0]["target"] == "پروژه دستیار هوشمند"

    # Export & Import JSON
    with tempfile.TemporaryDirectory() as tmpdir:
        json_file = str(Path(tmpdir) / "kg_backup.json")
        graph.export_json(json_file)
        assert Path(json_file).exists()

        new_graph = MultimodalTemporalGraph()
        new_graph.import_json(json_file)
        assert len(new_graph._nodes) == 2
        assert len(new_graph._edges) == 1


def test_engine_ingest_ocr_invoice_multimodal():
    engine = TemporalKnowledgeEngine()

    mock_ocr = {
        "file_path": "/workspace/invoices/invoice_1042.pdf",
        "cleaned_text": "فاکتور خرید خدمات هوش مصنوعی بازرگانی امید",
        "extracted_fields": {
            "vendor": "بازرگانی امید",
            "date": "1403/06/25",
            "total_amount": 5500000,
            "tax": 550000,
            "tracking_code": "TRK-778899",
            "iban": "IR120000000000000000000001",
        },
    }

    nodes = engine.ingest_ocr_result(mock_ocr)
    assert len(nodes) >= 3

    # Verify Vendor Node
    vendor = engine.graph.find_node("بازرگانی امید")
    assert vendor is not None
    assert vendor.entity_type == EntityType.VENDOR
    assert ModalityType.OCR in vendor.modalities

    # Verify Transaction Node
    tx_nodes = [n for n in nodes if n.entity_type == EntityType.TRANSACTION]
    assert len(tx_nodes) == 1
    assert tx_nodes[0].attributes["amount"] == 5500000

    # Verify Timeline Events
    timeline = engine.graph.query_timeline()
    assert len(timeline) >= 1
    assert timeline[0].modality == ModalityType.OCR
    assert timeline[0].jalali_date == "1403/06/25"


def test_engine_ingest_speech_audio_multimodal():
    engine = TemporalKnowledgeEngine()

    mock_speech = {
        "audio_path": "/workspace/audio/voice_note_1.wav",
        "duration": 4.5,
        "text": "جلسه بررسی عملکرد مدل دریم با موفقیت انجام شد",
        "overall_emotion": "joyful",
        "emotion_blend": {
            "primary_emotion": "joyful",
            "secondary_emotion": "enthusiastic",
            "blend_ratio": 0.8,
        },
    }

    nodes = engine.ingest_speech_result(mock_speech, speaker_name="علی")
    assert len(nodes) >= 3

    speaker = engine.graph.find_node("علی")
    assert speaker is not None
    assert speaker.entity_type == EntityType.PERSON
    assert ModalityType.AUDIO in speaker.modalities

    # Emotion node
    emo_nodes = [n for n in nodes if "joyful" in n.name]
    assert len(emo_nodes) == 1


def test_cross_modal_temporal_query_and_narrative():
    engine = TemporalKnowledgeEngine()

    # Ingest OCR artifact
    engine.ingest_ocr_result({
        "file_path": "inv_01.txt",
        "extracted_fields": {
            "vendor": "فروشگاه مرکزی دریم",
            "date": "1403/06/25",
            "total_amount": 1200000,
        },
    })

    # Ingest Speech artifact
    engine.ingest_speech_result({
        "audio_path": "audio_01.wav",
        "text": "خرید از فروشگاه مرکزی دریم تایید شد",
        "overall_emotion": "calm",
    })

    # Query by keyword across modalities
    res = engine.query_temporal_knowledge(query="دریم")
    assert res.total_matches >= 2
    assert len(res.matched_nodes) >= 1
    assert len(res.timeline_events) >= 1
    assert "دریم" in res.summary_narrative


def test_knowledge_tools_and_security():
    reset_global_knowledge_engine()

    tools = get_knowledge_tools()
    assert len(tools) == 6

    # 1. Add entity
    res_ent = knowledge_add_entity(
        name="سرور ابری تهران",
        entity_type="organization",
        aliases="ابر تهران, Cloud Tehran",
        attributes={"region": "tehran-1"},
        valid_from_jalali="1403/01/01",
    )
    assert res_ent["success"] is True
    assert res_ent["entity"]["name"] == "سرور ابری تهران"

    # 2. Add relation
    res_rel = knowledge_add_relation(
        source_name="سرور ابری تهران",
        target_name="پروژه دریم",
        relation_type="belongs_to",
        context_snippet="زیرساخت اصلی پردازش ابری",
    )
    assert res_rel["success"] is True

    # 3. Query temporal
    q_res = knowledge_query_temporal(query="تهران")
    assert q_res["success"] is True
    assert len(q_res["matched_nodes"]) >= 1

    # 4. Get entity timeline
    t_res = knowledge_get_entity_timeline("سرور ابری تهران")
    assert t_res["success"] is True
    assert len(t_res["relationships"]) >= 1

    # 5. Link multimodal artifact
    link_res = knowledge_link_multimodal_artifact(
        artifact_type="ocr",
        artifact_data={
            "file_path": "server_invoice.pdf",
            "extracted_fields": {
                "vendor": "سرور ابری تهران",
                "total_amount": 3000000,
                "date": "1403/06/25",
            },
        },
    )
    assert link_res["success"] is True
    assert len(link_res["linked_nodes"]) >= 2

    # 6. Stats
    stats_res = knowledge_get_stats()
    assert stats_res["success"] is True
    assert stats_res["total_nodes"] >= 2

    reset_global_knowledge_engine()


def test_knowledge_slash_command_and_toolset_registration():
    reset_global_knowledge_engine()

    lines = []
    handle_knowledge_command("/kg stats", output=lines.append)
    assert any("Temporal KG" in line for line in lines)

    lines.clear()
    handle_knowledge_command("/kg query دریم", output=lines.append)
    assert len(lines) >= 1

    lines.clear()
    handle_knowledge_command("/kg timeline سرور", output=lines.append)
    assert len(lines) >= 1

    # Toolset check
    assert "knowledge" in BUILTIN_TOOLSETS
    kg_ts = get_toolset("knowledge")
    assert kg_ts is not None
    assert "knowledge_add_entity" in kg_ts.tools
    assert "knowledge_query_temporal" in kg_ts.tools

    reset_global_knowledge_engine()
''',
}


def main() -> None:
    root = Path.cwd()
    if not (root / "dream").is_dir():
        print("[-] Error: run this script from the root of the dream repository.")
        sys.exit(1)

    print("[*] Applying Phase 28 (Multimodal Temporal Knowledge Graph & Entity Linking)...")

    for rel_path, content in FILES.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"  [+] Wrote {rel_path}")

    # Ensure git author email is set to compliant user config
    try:
        subprocess.run(["git", "config", "user.name", "Ali Naderi"], check=False)
        subprocess.run(["git", "config", "user.email", "alinaderi@users.noreply.github.com"], check=False)
        print("  [+] Configured compliant git author credentials (Ali Naderi <alinaderi@users.noreply.github.com>)")
    except Exception:
        pass

    print("[✓] Successfully applied Phase 28 files.")


if __name__ == "__main__":
    main()
