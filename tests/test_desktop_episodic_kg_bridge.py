"""Tests for Desktop JSON-RPC Bridge methods in episodic.* namespace."""

from __future__ import annotations

import asyncio

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.extensions import Registry
from dream.bridge.methods_episodic import (
    episodic_compress_session,
    episodic_consolidate,
    episodic_get_hierarchy_stats,
    episodic_link_entity_fact,
    episodic_query_timeline,
    episodic_record_event,
    episodic_reset,
)
from dream.memory.hierarchical_episodic import reset_global_episodic_engine


@pytest.fixture(autouse=True)
def _clean_engine():
    """Reset global episodic engine before and after each test."""
    reset_global_episodic_engine()
    yield
    reset_global_episodic_engine()


def test_episodic_bridge_extension_discovery():
    """Verify episodic.* handlers are discovered by Bridge Registry."""
    handlers = Registry.publish({})
    assert "episodic.record_event" in handlers
    assert "episodic.compress_session" in handlers
    assert "episodic.query_timeline" in handlers
    assert "episodic.link_entity_fact" in handlers
    assert "episodic.consolidate" in handlers
    assert "episodic.get_hierarchy_stats" in handlers
    assert "episodic.reset" in handlers


def test_episodic_record_event_and_compress():
    """Test episodic.record_event and episodic.compress_session via JSON-RPC."""
    async def _test():
        rec_res = await episodic_record_event(
            {
                "session_id": "live_chat_01",
                "speaker": "user",
                "text": "بررسی زیرسیستم حافظه اپیزودیک و گراف دانش زمانی",
                "sentiment": 0.75,
            }
        )
        assert rec_res["status"] == "recorded"
        assert rec_res["turn"]["speaker"] == "user"

        comp_res = await episodic_compress_session(
            {"session_id": "live_chat_01", "domain": "knowledge_architecture"}
        )
        assert comp_res["status"] == "compressed"
        assert "episode" in comp_res
        assert comp_res["episode"]["session_id"] == "live_chat_01"

        stats = await episodic_get_hierarchy_stats()
        assert stats["tier_1_episodes_count"] == 1

    asyncio.run(_test())


def test_episodic_link_and_query_timeline():
    """Test episodic.link_entity_fact and episodic.query_timeline."""
    async def _test():
        comp_res = await episodic_compress_session(
            {"session_id": "sess_vision", "domain": "computer_vision"}
        )
        ep_id = comp_res["episode"]["episode_id"]

        link_res = await episodic_link_entity_fact(
            {
                "episode_id": ep_id,
                "entity_name": "VisionStudio",
                "entity_type": "concept",
                "relation_type": "references",
                "target_entity": "DreamKernel",
            }
        )
        assert link_res["status"] == "linked"
        assert link_res["fact"]["entity_name"] == "VisionStudio"

        query_res = await episodic_query_timeline({"query": "vision", "limit": 10})
        assert query_res["status"] == "ok"
        assert query_res["count"] >= 1

    asyncio.run(_test())


def test_episodic_consolidate_and_reset():
    """Test episodic.consolidate and episodic.reset lifecycle."""
    async def _test():
        await episodic_compress_session({"session_id": "sess_1", "domain": "engineering"})
        cons_res = await episodic_consolidate({"min_episodes": 1})
        assert cons_res["status"] == "consolidated"
        assert "engineering" in cons_res["persona"]["primary_domains"]

        reset_res = await episodic_reset()
        assert reset_res["status"] == "reset"
        stats = await episodic_get_hierarchy_stats()
        assert stats["tier_1_episodes_count"] == 0

    asyncio.run(_test())


def test_episodic_invalid_params():
    """Verify strict parameter sanitization for fuzzing defense."""
    async def _test():
        with pytest.raises(BridgeError):
            await episodic_record_event({"text": 123})

        with pytest.raises(BridgeError):
            await episodic_compress_session({"turns": "invalid_not_list"})

        with pytest.raises(BridgeError):
            await episodic_link_entity_fact({"entity_name": ""})

        with pytest.raises(BridgeError):
            await episodic_query_timeline({"min_importance": "high"})

    asyncio.run(_test())
