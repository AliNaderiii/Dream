"""Tests for Dialectic Reasoning Bridge and JSON-RPC Methods."""

from __future__ import annotations

import asyncio

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.extensions import Registry
from dream.bridge.methods_dialectic import (
    dialectic_add_belief,
    dialectic_debate_turn,
    dialectic_detect_tensions,
    dialectic_link_beliefs,
    dialectic_observe,
    dialectic_query,
    dialectic_reconcile_tension,
    dialectic_reset,
    dialectic_snapshot,
    reset_dialectic_engine,
)


@pytest.fixture(autouse=True)
def _clean_engine():
    """Reset dialectic engine before and after each test."""
    reset_dialectic_engine()
    yield
    reset_dialectic_engine()


def test_dialectic_bridge_extension_discovery():
    """Verify dialectic.* methods are automatically registered in the Bridge Registry."""
    handlers = Registry.publish({})
    assert "dialectic.observe" in handlers
    assert "dialectic.add_belief" in handlers
    assert "dialectic.link_beliefs" in handlers
    assert "dialectic.detect_tensions" in handlers
    assert "dialectic.reconcile_tension" in handlers
    assert "dialectic.query" in handlers
    assert "dialectic.snapshot" in handlers
    assert "dialectic.debate_turn" in handlers
    assert "dialectic.reset" in handlers


def test_dialectic_observe_and_query():
    """Test dialectic.observe and dialectic.query."""
    async def _test():
        res = await dialectic_observe(
            {"statement": "TypeScript provides static type safety", "domain": "engineering"}
        )
        assert res["status"] == "observed"
        assert "belief" in res
        assert res["belief"]["domain"] == "engineering"

        query_res = await dialectic_query({"query": "TypeScript", "limit": 5})
        assert query_res["status"] == "ok"
        assert query_res["count"] >= 1
        assert any("TypeScript" in b["statement"] for b in query_res["beliefs"])

        with pytest.raises(BridgeError):
            await dialectic_observe({"statement": ""})

    asyncio.run(_test())


def test_dialectic_add_link_and_tensions():
    """Test add belief, link them with contradiction, and detect tensions."""
    async def _test():
        b1 = await dialectic_add_belief(
            {
                "statement": "Monolithic architectures simplify operational deployment",
                "domain": "architecture",
                "confidence": 0.85,
            }
        )
        b2 = await dialectic_add_belief(
            {
                "statement": "Microservices are required for organizational scaling",
                "domain": "architecture",
                "confidence": 0.90,
            }
        )
        id1 = b1["belief"]["belief_id"]
        id2 = b2["belief"]["belief_id"]

        link_res = await dialectic_link_beliefs(
            {
                "source_id": id1,
                "target_id": id2,
                "relation_type": "contradicts",
                "notes": "Architectural tension",
            }
        )
        assert link_res["status"] == "linked"

        tensions_res = await dialectic_detect_tensions()
        assert tensions_res["status"] == "ok"
        assert tensions_res["count"] >= 1
        tension_id = tensions_res["tensions"][0]["tension_id"]

        # Reconcile tension
        nuanced_stmt = (
            "Modular monolith with clear domain boundaries balances agility and simplicity"
        )
        rec_res = await dialectic_reconcile_tension(
            {
                "tension_id": tension_id,
                "nuanced_statement": nuanced_stmt,
            }
        )
        assert rec_res["status"] == "reconciled"
        assert "nuanced_belief" in rec_res

    asyncio.run(_test())


def test_dialectic_debate_turn_and_snapshot():
    """Test 3-agent dialectic debate turn."""
    async def _test():
        turn_res = await dialectic_debate_turn(
            {"topic": "Hybrid Semantic Caching v3", "domain": "performance"}
        )
        assert turn_res["status"] == "completed"
        assert "thesis" in turn_res
        assert "antithesis" in turn_res
        assert "synthesis" in turn_res
        assert "graph_snapshot" in turn_res
        assert len(turn_res["graph_snapshot"]["beliefs"]) >= 3

        # Snapshot retrieval
        snap_res = await dialectic_snapshot()
        assert "beliefs" in snap_res
        assert len(snap_res["beliefs"]) >= 3

        # Reset
        reset_res = await dialectic_reset()
        assert reset_res["status"] == "reset"
        empty_snap = await dialectic_snapshot()
        assert len(empty_snap["beliefs"]) == 0

    asyncio.run(_test())


def test_dialectic_invalid_params():
    """Ensure invalid parameters properly raise BridgeError."""
    async def _test():
        with pytest.raises(BridgeError):
            await dialectic_add_belief({"statement": "   "})

        with pytest.raises(BridgeError):
            await dialectic_link_beliefs({"source_id": "", "target_id": "b2"})

        with pytest.raises(BridgeError):
            await dialectic_reconcile_tension({"tension_id": "", "nuanced_statement": "test"})

        with pytest.raises(BridgeError):
            await dialectic_debate_turn({"topic": ""})

    asyncio.run(_test())
