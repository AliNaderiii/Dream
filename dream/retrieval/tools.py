"""Agent tool definitions for hybrid semantic search and knowledge graph memory."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from dream.retrieval.engine import UnifiedRetrievalEngine

_GLOBAL_ENGINE: UnifiedRetrievalEngine | None = None


def get_global_retrieval_engine() -> UnifiedRetrievalEngine:
    """Retrieve or initialize singleton retrieval engine."""
    global _GLOBAL_ENGINE
    if _GLOBAL_ENGINE is None:
        _GLOBAL_ENGINE = UnifiedRetrievalEngine()
    return _GLOBAL_ENGINE


def set_global_retrieval_engine(engine: UnifiedRetrievalEngine) -> None:
    """Set global retrieval engine instance."""
    global _GLOBAL_ENGINE
    _GLOBAL_ENGINE = engine


def search_hybrid_memory(query: str, limit: int = 5) -> str:
    """Perform hybrid BM25 + Dense Semantic search across agent associative memory.

    Args:
        query: Search query in English or Persian.
        limit: Max number of relevant memories to retrieve (default 5).

    Returns:
        JSON string containing ranked memories with relevance scores and graph links.
    """
    engine = get_global_retrieval_engine()
    results = engine.search(query, top_k=limit)
    if not results:
        return json.dumps(
            {"status": "empty", "query": query, "results": []},
            ensure_ascii=False,
        )

    formatted = []
    for r in results:
        formatted.append(
            {
                "doc_id": r.doc_id,
                "content": r.content,
                "score": round(r.score, 4),
                "breakdown": {
                    "bm25_score": round(r.breakdown.sparse_bm25_score, 3),
                    "vector_score": round(r.breakdown.dense_vector_score, 3),
                    "rrf_score": round(r.breakdown.rrf_score, 4),
                    "temporal_decay": round(r.breakdown.temporal_multiplier, 3),
                },
                "graph_associations": r.graph_context,
            }
        )

    return json.dumps(
        {"status": "ok", "query": query, "count": len(formatted), "results": formatted},
        ensure_ascii=False,
        indent=2,
    )


def query_knowledge_graph(entity_name: str, max_hops: int = 2) -> str:
    """Query relationships and multi-hop semantic links for an entity in Knowledge Graph.

    Args:
        entity_name: Target entity name (e.g. 'Ali', 'Dream', 'Python').
        max_hops: Exploration depth (1 or 2 hops).

    Returns:
        JSON string describing entity details and related knowledge graph paths.
    """
    engine = get_global_retrieval_engine()
    entity = engine.graph.find_entity(entity_name)
    if not entity:
        return json.dumps(
            {
                "status": "not_found",
                "entity": entity_name,
                "message": f"Entity '{entity_name}' not found in knowledge graph.",
            },
            ensure_ascii=False,
        )

    neighbors = engine.graph.query_neighbors(entity.name, max_hops=max_hops)
    return json.dumps(
        {
            "status": "ok",
            "entity": {
                "id": entity.id,
                "name": entity.name,
                "type": entity.entity_type,
                "description": entity.description,
                "aliases": entity.aliases,
            },
            "relationships_count": len(neighbors),
            "relationships": neighbors,
        },
        ensure_ascii=False,
        indent=2,
    )


def get_retrieval_tools() -> dict[str, Callable[..., Any]]:
    """Return dict of retrieval tools for registration."""
    return {
        "search_hybrid_memory": search_hybrid_memory,
        "query_knowledge_graph": query_knowledge_graph,
    }
