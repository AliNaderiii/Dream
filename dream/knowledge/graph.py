"""Multimodal Temporal Knowledge Graph Memory Structure and Graph Traversal."""

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
