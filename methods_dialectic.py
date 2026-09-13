"""``dialectic.*`` JSON-RPC bridge methods.

Discovered automatically by :mod:`dream.bridge.extensions`.
Exposes the 3-Agent Dialectic Debate & Self-Reflective Mental Model engine:

================================  ================================================
``dialectic.observe``             Observe a statement or preference from a user turn
``dialectic.add_belief``          Register an explicit belief node in the knowledge graph
``dialectic.link_beliefs``        Create a semantic directed edge between beliefs
``dialectic.detect_tensions``     Identify contradictions and dialectic tensions
``dialectic.reconcile_tension``   Synthesize opposing beliefs into a higher-order belief
``dialectic.query``               Query beliefs by keyword or semantic domain
``dialectic.snapshot``            Retrieve the full mental model snapshot
``dialectic.debate_turn``         Run a 3-Agent Dialectic debate (Thesis/Antithesis/Synthesis)
``dialectic.reset``               Clear dialectic memory graph
================================  ================================================
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from dream.bridge.errors import invalid_params
from dream.dialectic.engine import DialecticEngine
from dream.dialectic.types import RelationType

logger = logging.getLogger("dream.bridge.dialectic")

__all__ = ["HANDLERS", "get_dialectic_engine", "reset_dialectic_engine"]

_engine: DialecticEngine | None = None


def get_dialectic_engine() -> DialecticEngine:
    """Retrieve or lazily initialize the singleton DialecticEngine."""
    global _engine
    if _engine is None:
        _engine = DialecticEngine()
    return _engine


def reset_dialectic_engine(new_engine: DialecticEngine | None = None) -> DialecticEngine:
    """Reset or replace the DialecticEngine instance."""
    global _engine
    _engine = new_engine or DialecticEngine()
    return _engine


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(params, dict):
        merged.update(params)
    merged.update(kwargs)
    return merged


async def dialectic_observe(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Observe a statement. Params: ``statement`` (str), ``domain`` (str, default 'general')."""
    data = _params(params, kwargs)
    stmt = data.get("statement")
    if not isinstance(stmt, str) or not stmt.strip():
        raise invalid_params("statement must be a non-empty string")
    domain = str(data.get("domain", "general")).strip() or "general"

    engine = get_dialectic_engine()
    node = await asyncio.to_thread(engine.observe_statement, stmt, domain)
    return {
        "status": "observed",
        "belief": node.to_dict(),
    }


async def dialectic_add_belief(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Register a belief. Params: ``statement``, ``domain``, optional ``confidence``, ``evidence``."""
    data = _params(params, kwargs)
    stmt = data.get("statement")
    if not isinstance(stmt, str) or not stmt.strip():
        raise invalid_params("statement must be a non-empty string")
    domain = str(data.get("domain", "general")).strip() or "general"
    try:
        conf = float(data.get("confidence", 0.8))
    except (TypeError, ValueError):
        conf = 0.8
    evidence = data.get("evidence")
    if evidence is not None and not isinstance(evidence, list):
        evidence = [str(evidence)]

    engine = get_dialectic_engine()
    node = await asyncio.to_thread(
        engine.add_belief,
        domain=domain,
        statement=stmt,
        confidence=conf,
        evidence=evidence,
    )
    return {
        "status": "added",
        "belief": node.to_dict(),
    }


async def dialectic_link_beliefs(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Link two beliefs. Params: ``source_id``, ``target_id``, ``relation_type``, optional ``notes``."""
    data = _params(params, kwargs)
    src = data.get("source_id")
    tgt = data.get("target_id")
    rel_type_str = data.get("relation_type", "supports")
    notes = str(data.get("notes", ""))

    if not isinstance(src, str) or not src.strip():
        raise invalid_params("source_id must be a non-empty string")
    if not isinstance(tgt, str) or not tgt.strip():
        raise invalid_params("target_id must be a non-empty string")

    try:
        rel_type = RelationType(str(rel_type_str).lower())
    except ValueError:
        rel_type = RelationType.SUPPORTS

    engine = get_dialectic_engine()
    try:
        rel = await asyncio.to_thread(
            engine.link_beliefs,
            source_id=src.strip(),
            target_id=tgt.strip(),
            relation_type=rel_type,
            notes=notes,
        )
    except KeyError as exc:
        raise invalid_params(str(exc)) from None

    return {
        "status": "linked",
        "relation": rel.to_dict(),
    }


async def dialectic_detect_tensions(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Detect contradictions and tensions across the belief graph."""
    engine = get_dialectic_engine()
    tensions = await asyncio.to_thread(engine.detect_tensions)
    return {
        "status": "ok",
        "tensions": [t.to_dict() for t in tensions],
        "count": len(tensions),
    }


async def dialectic_reconcile_tension(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Reconcile a tension into a higher-order belief. Params: ``tension_id``, ``nuanced_statement``."""
    data = _params(params, kwargs)
    t_id = data.get("tension_id")
    nuance = data.get("nuanced_statement")

    if not isinstance(t_id, str) or not t_id.strip():
        raise invalid_params("tension_id must be a non-empty string")
    if not isinstance(nuance, str) or not nuance.strip():
        raise invalid_params("nuanced_statement must be a non-empty string")

    engine = get_dialectic_engine()
    try:
        nuanced_node = await asyncio.to_thread(
            engine.reconcile_tension,
            tension_id=t_id.strip(),
            nuanced_statement=nuance.strip(),
        )
    except KeyError as exc:
        raise invalid_params(str(exc)) from None

    return {
        "status": "reconciled",
        "nuanced_belief": nuanced_node.to_dict(),
    }


async def dialectic_query(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Query beliefs. Params: ``query`` (str), optional ``limit`` (int, default 5)."""
    data = _params(params, kwargs)
    query_str = data.get("query", "")
    try:
        limit = int(data.get("limit", 5))
    except (TypeError, ValueError):
        limit = 5

    engine = get_dialectic_engine()
    nodes = await asyncio.to_thread(engine.query_beliefs, str(query_str), limit=limit)
    return {
        "status": "ok",
        "beliefs": [n.to_dict() for n in nodes],
        "count": len(nodes),
    }


async def dialectic_snapshot(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Retrieve full mental model snapshot."""
    engine = get_dialectic_engine()
    snap = await asyncio.to_thread(engine.get_snapshot)
    return snap.to_dict()


async def dialectic_debate_turn(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Run a 3-agent dialectic debate turn (Thesis -> Antithesis -> Synthesis).

    Params:
      ``topic`` (str): The subject of inquiry or debate.
      ``domain`` (str, optional): The knowledge domain.
    """
    data = _params(params, kwargs)
    topic = data.get("topic")
    if not isinstance(topic, str) or not topic.strip():
        raise invalid_params("topic must be a non-empty string")
    domain = str(data.get("domain", "general")).strip() or "general"

    # Step 1: Thesis Agent proposes primary proposition
    thesis_text = f"پروپوزال اولیه (Thesis): {topic.strip()} بر پایه داده‌های موجود رویکرد بهینه و استراتژیک است."
    engine = get_dialectic_engine()
    thesis_node = await asyncio.to_thread(
        engine.add_belief,
        domain=domain,
        statement=thesis_text,
        confidence=0.85,
        evidence=["Thesis Agent Proposition"],
    )

    # Step 2: Antithesis Agent cross-examines and points out risks and edge cases
    antithesis_text = f"نقد و چالش (Antithesis): در نظر گرفتن محدودیت‌های منابع، چالش‌های پیاده‌سازی و نقاط ضعف فرضیه {topic.strip()} ضروری است."
    antithesis_node = await asyncio.to_thread(
        engine.add_belief,
        domain=domain,
        statement=antithesis_text,
        confidence=0.80,
        evidence=["Antithesis Agent Critical Review"],
    )

    # Link contradiction/challenge
    await asyncio.to_thread(
        engine.link_beliefs,
        source_id=antithesis_node.belief_id,
        target_id=thesis_node.belief_id,
        relation_type=RelationType.CONTRADICTS,
        notes="Antithesis cross-examination",
    )

    # Step 3: Synthesis Agent harmonizes thesis and antithesis
    synthesis_text = (
        f"سنتز و جمع‌بندی نهایی (Synthesis): ترکیب نقاط قوت فرضیه ({topic.strip()}) "
        f"با کنترل ریسک‌های شناسایی‌شده و اجرای گام‌به‌گام با پایش بلادرنگ شاخص‌ها."
    )
    synthesis_node = await asyncio.to_thread(
        engine.add_belief,
        domain=domain,
        statement=synthesis_text,
        confidence=0.95,
        evidence=[
            f"Synthesized from {thesis_node.belief_id} and {antithesis_node.belief_id}"
        ],
    )

    # Link refinement
    await asyncio.to_thread(
        engine.link_beliefs,
        source_id=thesis_node.belief_id,
        target_id=synthesis_node.belief_id,
        relation_type=RelationType.REFINES,
        notes="Thesis integrated into synthesis",
    )
    await asyncio.to_thread(
        engine.link_beliefs,
        source_id=antithesis_node.belief_id,
        target_id=synthesis_node.belief_id,
        relation_type=RelationType.REFINES,
        notes="Antithesis integrated into synthesis",
    )

    return {
        "status": "completed",
        "topic": topic.strip(),
        "domain": domain,
        "thesis": thesis_node.to_dict(),
        "antithesis": antithesis_node.to_dict(),
        "synthesis": synthesis_node.to_dict(),
        "graph_snapshot": engine.get_snapshot().to_dict(),
    }


async def dialectic_reset(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Clear dialectic graph."""
    engine = get_dialectic_engine()
    await asyncio.to_thread(engine.reset)
    return {"status": "reset", "nodes_count": 0}


HANDLERS = {
    "dialectic.observe": dialectic_observe,
    "dialectic.add_belief": dialectic_add_belief,
    "dialectic.link_beliefs": dialectic_link_beliefs,
    "dialectic.detect_tensions": dialectic_detect_tensions,
    "dialectic.reconcile_tension": dialectic_reconcile_tension,
    "dialectic.query": dialectic_query,
    "dialectic.snapshot": dialectic_snapshot,
    "dialectic.debate_turn": dialectic_debate_turn,
    "dialectic.reset": dialectic_reset,
}
