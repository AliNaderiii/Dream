"""``episodic.*`` JSON-RPC bridge methods.

Discovered automatically by :mod:`dream.bridge.extensions`.
Exposes the Hierarchical Episodic Memory & Temporal Knowledge Graph Subsystem:

================================  ================================================
``episodic.record_event``         Record working turn / episodic event
``episodic.compress_session``     Compress working memory into a durable episode
``episodic.query_timeline``       Query episodic events with Jalali temporal filters
``episodic.link_entity_fact``     Link episodic facts to the Temporal Knowledge Graph
``episodic.consolidate``          Trigger Tier-3 long-term persona consolidation
``episodic.get_hierarchy_stats``  Retrieve multi-tier memory metrics and distribution
``episodic.reset``                Clear working buffers and caches
================================  ================================================
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from dream.bridge.errors import invalid_params
from dream.memory.hierarchical_episodic import get_episodic_engine

logger = logging.getLogger("dream.bridge.episodic")

__all__ = ["HANDLERS"]


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(params, dict):
        merged.update(params)
    merged.update(kwargs)
    return merged


async def episodic_record_event(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Record a working turn / event.

    Params: ``session_id``, ``speaker``, ``text``, ``sentiment``.
    """
    data = _params(params, kwargs)
    sid = data.get("session_id")
    if sid is not None and not isinstance(sid, str):
        raise invalid_params("session_id must be a string")
    sid = sid or "default_session"

    speaker = data.get("speaker", "user")
    if not isinstance(speaker, str):
        raise invalid_params("speaker must be a string")

    text = data.get("text")
    if text is None or not isinstance(text, str):
        raise invalid_params("text must be a string")

    sentiment = data.get("sentiment", 0.0)
    if not isinstance(sentiment, (int, float)) or isinstance(sentiment, bool):
        raise invalid_params("sentiment must be a number")

    meta = data.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        raise invalid_params("metadata must be an object")

    engine = get_episodic_engine()
    turn = await asyncio.to_thread(
        engine.record_working_turn,
        session_id=sid,
        speaker=speaker,
        text=text,
        sentiment=float(sentiment),
        metadata=meta,
    )
    return {"status": "recorded", "turn": turn.to_dict()}


async def episodic_compress_session(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Compress working memory turns into a durable episode. Params: ``session_id``, ``domain``."""
    data = _params(params, kwargs)
    sid = data.get("session_id")
    if sid is not None and not isinstance(sid, str):
        raise invalid_params("session_id must be a string")
    sid = sid or "default_session"

    domain = data.get("domain", "general")
    if not isinstance(domain, str):
        raise invalid_params("domain must be a string")

    turns = data.get("turns")
    if turns is not None:
        if not isinstance(turns, list) or not all(isinstance(t, dict) for t in turns):
            raise invalid_params("turns must be a list of turn objects")

    engine = get_episodic_engine()
    episode = await asyncio.to_thread(
        engine.compress_session,
        session_id=sid,
        turns=turns,
        domain=domain,
    )
    return {"status": "compressed", "episode": episode.to_dict()}


async def episodic_query_timeline(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Query episodic timeline. Params: ``query``, ``start_jalali``, ``end_jalali``, ``limit``."""
    data = _params(params, kwargs)
    q = data.get("query", "")
    if not isinstance(q, str):
        raise invalid_params("query must be a string")

    start_j = data.get("start_jalali", "")
    if not isinstance(start_j, str):
        raise invalid_params("start_jalali must be a string")

    end_j = data.get("end_jalali", "")
    if not isinstance(end_j, str):
        raise invalid_params("end_jalali must be a string")

    min_imp = data.get("min_importance", 1)
    if not isinstance(min_imp, int) or isinstance(min_imp, bool):
        raise invalid_params("min_importance must be an integer")

    limit = data.get("limit", 20)
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise invalid_params("limit must be an integer")

    engine = get_episodic_engine()
    episodes = await asyncio.to_thread(
        engine.query_timeline,
        query=q,
        start_jalali=start_j,
        end_jalali=end_j,
        min_importance=min_imp,
        limit=limit,
    )
    return {
        "status": "ok",
        "count": len(episodes),
        "episodes": [e.to_dict() for e in episodes],
    }


async def episodic_link_entity_fact(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Link episode to Temporal Knowledge Graph. Params: ``episode_id``, ``entity_name``."""
    data = _params(params, kwargs)
    ep_id = data.get("episode_id")
    if ep_id is not None and not isinstance(ep_id, str):
        raise invalid_params("episode_id must be a string")
    ep_id = ep_id or "ep_default"

    entity_name = data.get("entity_name")
    if entity_name is None or not isinstance(entity_name, str) or not entity_name.strip():
        raise invalid_params("entity_name must be a non-empty string")

    entity_type = data.get("entity_type", "concept")
    if not isinstance(entity_type, str):
        raise invalid_params("entity_type must be a string")

    relation_type = data.get("relation_type", "references")
    if not isinstance(relation_type, str):
        raise invalid_params("relation_type must be a string")

    target_entity = data.get("target_entity", "DreamAgent")
    if not isinstance(target_entity, str):
        raise invalid_params("target_entity must be a string")

    jalali_date = data.get("jalali_date")
    if jalali_date is not None and not isinstance(jalali_date, str):
        raise invalid_params("jalali_date must be a string")

    engine = get_episodic_engine()
    fact = await asyncio.to_thread(
        engine.link_entity_fact,
        episode_id=ep_id,
        entity_name=entity_name.strip(),
        entity_type=entity_type,
        relation_type=relation_type,
        target_entity=target_entity,
        jalali_date=jalali_date,
    )
    return {"status": "linked", "fact": fact.to_dict()}


async def episodic_consolidate(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Consolidate long-term persona and competencies."""
    data = _params(params, kwargs)
    force = bool(data.get("force_decay", False))
    min_episodes = data.get("min_episodes", 1)
    if not isinstance(min_episodes, int) or isinstance(min_episodes, bool):
        raise invalid_params("min_episodes must be an integer")

    engine = get_episodic_engine()
    persona = await asyncio.to_thread(
        engine.consolidate,
        force_decay=force,
        min_episodes=min_episodes,
    )
    return {"status": "consolidated", "persona": persona.to_dict()}


async def episodic_get_hierarchy_stats(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Retrieve multi-tier hierarchical memory statistics."""
    engine = get_episodic_engine()
    return await asyncio.to_thread(engine.get_hierarchy_stats)


async def episodic_reset(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Reset working memory buffers and cached state."""
    engine = get_episodic_engine()
    await asyncio.to_thread(engine.reset)
    return {"status": "reset", "tier_0_working_turns": 0, "tier_1_episodes_count": 0}


HANDLERS = {
    "episodic.record_event": episodic_record_event,
    "episodic.compress_session": episodic_compress_session,
    "episodic.query_timeline": episodic_query_timeline,
    "episodic.link_entity_fact": episodic_link_entity_fact,
    "episodic.consolidate": episodic_consolidate,
    "episodic.get_hierarchy_stats": episodic_get_hierarchy_stats,
    "episodic.reset": episodic_reset,
}
