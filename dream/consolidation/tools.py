"""LLM tool bindings for Memory Consolidation, Entropy Pruning, and Epistemic Distillation."""

from __future__ import annotations

from typing import Any

from dream.consolidation.engine import ConsolidationEngine
from dream.consolidation.types import MemoryNodeType

_GLOBAL_CONSOLIDATION_ENGINE: ConsolidationEngine | None = None


def get_global_consolidation_engine() -> ConsolidationEngine:
    """Get or initialize singleton ConsolidationEngine."""
    global _GLOBAL_CONSOLIDATION_ENGINE
    if _GLOBAL_CONSOLIDATION_ENGINE is None:
        _GLOBAL_CONSOLIDATION_ENGINE = ConsolidationEngine()
    return _GLOBAL_CONSOLIDATION_ENGINE


def reset_global_consolidation_engine() -> None:
    """Reset singleton ConsolidationEngine."""
    global _GLOBAL_CONSOLIDATION_ENGINE
    _GLOBAL_CONSOLIDATION_ENGINE = None


def consolidation_add_memory(
    content: str,
    node_type: str = "episodic",
    importance: float = 0.5,
) -> dict[str, Any]:
    """Store a new memory item in the consolidation engine."""
    engine = get_global_consolidation_engine()
    try:
        nt = MemoryNodeType(node_type.lower())
    except ValueError:
        nt = MemoryNodeType.EPISODIC

    item = engine.add_memory(content=content, node_type=nt, importance=importance)
    return {"success": True, "memory": item.to_dict()}


def consolidation_run_cycle(dry_run: bool = False) -> dict[str, Any]:
    """Run full sleep-phase memory consolidation, Ebbinghaus decay, and entropy pruning cycle."""
    engine = get_global_consolidation_engine()
    report = engine.run_consolidation_cycle(dry_run=dry_run)
    return {"success": True, "report": report.to_dict()}


def consolidation_distill_session(raw_transcript: str) -> dict[str, Any]:
    """Distill raw multi-turn conversation into atomic semantic facts and user traits."""
    engine = get_global_consolidation_engine()
    facts = engine.distiller.distill_transcript(raw_transcript)
    for f in facts:
        engine._memories[f.memory_id] = f
    return {
        "success": True,
        "distilled_facts_count": len(facts),
        "facts": [f.to_dict() for f in facts],
    }


def consolidation_get_stats() -> dict[str, Any]:
    """Retrieve memory repository health score, node counts, and compression rates."""
    engine = get_global_consolidation_engine()
    stats = engine.get_health_stats()
    return {"success": True, "stats": stats.to_dict()}


def consolidation_export_report() -> dict[str, Any]:
    """Export formatted Markdown report of memory consolidation and retention health."""
    engine = get_global_consolidation_engine()
    report_md = engine.format_consolidation_report()
    return {"success": True, "markdown_report": report_md}


def consolidation_reset_all() -> dict[str, Any]:
    """Reset all stored memories and consolidation history."""
    engine = get_global_consolidation_engine()
    engine.reset()
    return {"success": True, "message": "\u062d\u0627\u0641\u0638\u0647 \u0648 \u062a\u0627\u0631\u06cc\u062e\u0686\u0647 \u062a\u062b\u0628\u06cc\u062a \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."}


def get_consolidation_tools() -> list[Any]:
    """Return consolidation tool functions for agent registration."""
    return [
        consolidation_add_memory,
        consolidation_run_cycle,
        consolidation_distill_session,
        consolidation_get_stats,
        consolidation_export_report,
        consolidation_reset_all,
    ]
