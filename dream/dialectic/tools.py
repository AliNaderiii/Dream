"""LLM Tool bindings for Dialectic Memory and Reflective Knowledge Graph."""

from __future__ import annotations

from typing import Any

from dream.dialectic.engine import DialecticEngine

_GLOBAL_DIALECTIC_ENGINE: DialecticEngine | None = None


def get_global_dialectic_engine() -> DialecticEngine:
    """Get or create singleton DialecticEngine."""
    global _GLOBAL_DIALECTIC_ENGINE
    if _GLOBAL_DIALECTIC_ENGINE is None:
        _GLOBAL_DIALECTIC_ENGINE = DialecticEngine()
    return _GLOBAL_DIALECTIC_ENGINE


def reset_global_dialectic_engine() -> None:
    """Reset singleton DialecticEngine instance for testing."""
    global _GLOBAL_DIALECTIC_ENGINE
    _GLOBAL_DIALECTIC_ENGINE = None


def dialectic_observe(statement: str, domain: str = "general") -> dict[str, Any]:
    """Observe and record a new fact, preference, or trait into the user dialectic model."""
    engine = get_global_dialectic_engine()
    node = engine.observe_statement(statement=statement, domain=domain)
    return {"success": True, "belief": node.to_dict()}


def dialectic_reflect() -> dict[str, Any]:
    """Perform self-reflection over memory graph, detecting tensions and synthesizing insights."""
    engine = get_global_dialectic_engine()
    snapshot = engine.reflect_and_synthesize()
    return {"success": True, "snapshot": snapshot.to_dict()}


def dialectic_get_belief_graph() -> dict[str, Any]:
    """Retrieve full active dialectic knowledge graph with beliefs, edges, and tensions."""
    engine = get_global_dialectic_engine()
    snapshot = engine.get_snapshot()
    return {"success": True, "graph": snapshot.to_dict()}


def dialectic_reconcile(tension_id: str, resolution: str) -> dict[str, Any]:
    """Resolve an identified dialectic tension between contradictory beliefs with synthesis."""
    engine = get_global_dialectic_engine()
    try:
        node = engine.reconcile_tension(tension_id=tension_id, nuanced_statement=resolution)
        return {"success": True, "nuanced_belief": node.to_dict()}
    except KeyError as exc:
        return {"success": False, "error": str(exc)}


def dialectic_query_traits(query: str) -> dict[str, Any]:
    """Query user beliefs and preferences matching a semantic domain or keyword."""
    engine = get_global_dialectic_engine()
    nodes = engine.query_beliefs(query=query)
    return {"success": True, "results": [n.to_dict() for n in nodes]}


def get_dialectic_tools() -> list[Any]:
    """Return list of dialectic memory tool functions for agent registration."""
    return [
        dialectic_observe,
        dialectic_reflect,
        dialectic_get_belief_graph,
        dialectic_reconcile,
        dialectic_query_traits,
    ]
