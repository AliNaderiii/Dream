"""LLM Tool bindings for Multimodal Temporal Knowledge Graph and Entity Linking."""

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
