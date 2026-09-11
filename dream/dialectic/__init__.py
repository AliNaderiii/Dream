"""Dialectic Memory & Self-Reflective Knowledge Graph subsystem for Dream Agent."""

from __future__ import annotations

from dream.dialectic.engine import DialecticEngine
from dream.dialectic.slash import handle_dialectic_command
from dream.dialectic.tools import (
    dialectic_get_belief_graph,
    dialectic_observe,
    dialectic_query_traits,
    dialectic_reconcile,
    dialectic_reflect,
    get_dialectic_tools,
    get_global_dialectic_engine,
    reset_global_dialectic_engine,
)
from dream.dialectic.types import (
    BeliefNode,
    DialecticMemorySnapshot,
    DialecticRelation,
    DialecticStatus,
    DialecticTension,
    RelationType,
)

__all__ = [
    "BeliefNode",
    "DialecticEngine",
    "DialecticMemorySnapshot",
    "DialecticRelation",
    "DialecticStatus",
    "DialecticTension",
    "RelationType",
    "dialectic_get_belief_graph",
    "dialectic_observe",
    "dialectic_query_traits",
    "dialectic_reconcile",
    "dialectic_reflect",
    "get_dialectic_tools",
    "get_global_dialectic_engine",
    "handle_dialectic_command",
    "reset_global_dialectic_engine",
]

try:
    from dream.tools import toolsets

    if hasattr(toolsets, "register_toolset") and "dialectic" not in toolsets.BUILTIN_TOOLSETS:
        toolsets.register_toolset(
            "dialectic",
            [
                "dialectic_observe",
                "dialectic_reflect",
                "dialectic_get_belief_graph",
                "dialectic_reconcile",
                "dialectic_query_traits",
            ],
            description="Self-reflective dialectic user modeling and knowledge synthesis",
        )
except Exception:
    pass
