"""Tests for Dialectic Memory & Self-Reflective Knowledge Graph subsystem."""

from __future__ import annotations

import pytest

from dream.dialectic import (
    BeliefNode,
    DialecticEngine,
    DialecticStatus,
    RelationType,
    dialectic_get_belief_graph,
    dialectic_observe,
    dialectic_query_traits,
    dialectic_reconcile,
    dialectic_reflect,
    get_dialectic_tools,
    handle_dialectic_command,
    reset_global_dialectic_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


def test_belief_node_creation_and_dict():
    node = BeliefNode(
        belief_id="b_001",
        domain="coding",
        statement="Prefers static typing and mypy verification",
        confidence=0.9,
    )
    assert node.belief_id == "b_001"
    assert node.status == DialecticStatus.ACTIVE
    d = node.to_dict()
    assert d["domain"] == "coding"
    assert d["confidence"] == 0.9


def test_dialectic_engine_observation_and_link():
    engine = DialecticEngine()
    b1 = engine.observe_statement("User values async architecture", domain="tech")
    b2 = engine.observe_statement("User works primarily on Linux backend services", domain="tech")

    assert len(engine._nodes) == 2
    assert b1.status == DialecticStatus.ACTIVE

    rel = engine.link_beliefs(
        source_id=b1.belief_id,
        target_id=b2.belief_id,
        relation_type=RelationType.SUPPORTS,
        notes="Complementary technical stack",
    )
    assert rel.relation_type == RelationType.SUPPORTS
    assert len(engine._relations) == 1

    with pytest.raises(KeyError):
        engine.link_beliefs("invalid_1", "invalid_2", RelationType.SUPPORTS)


def test_dialectic_contradiction_detection_and_reconciliation():
    engine = DialecticEngine()
    b1 = engine.add_belief("workflow", "User prefers concise summary outputs", confidence=0.8)
    b2 = engine.add_belief(
        "workflow", "User prefers detailed breakdown of all steps", confidence=0.8
    )

    tensions = engine.detect_tensions()
    assert len(tensions) >= 1
    assert b1.status == DialecticStatus.CONTRADICTED
    assert b2.status == DialecticStatus.CONTRADICTED

    ten_id = tensions[0].tension_id
    nuanced_stmt = "User prefers concise summaries by default, but detailed breakdowns on request"
    synth_node = engine.reconcile_tension(ten_id, nuanced_stmt)

    assert synth_node.statement == nuanced_stmt
    assert synth_node.status == DialecticStatus.ACTIVE
    assert b1.status == DialecticStatus.NUANCED
    assert b2.status == DialecticStatus.NUANCED
    assert tensions[0].resolved is True


def test_dialectic_reflection_and_query():
    engine = DialecticEngine()
    engine.observe_statement("Always write clean Python code", domain="engineering")
    engine.observe_statement("Favor modular micro-packages", domain="engineering")

    results = engine.query_beliefs("Python")
    assert len(results) >= 1
    assert "Always write clean Python code" in results[0].statement

    snapshot = engine.reflect_and_synthesize()
    assert snapshot.nodes_count >= 2
    assert "Dialectic Mental Model Summary" in snapshot.synthesized_summary

    engine.reset()
    assert len(engine._nodes) == 0


def test_dialectic_tools_and_slash():
    reset_global_dialectic_engine()
    tools = get_dialectic_tools()
    assert len(tools) == 5

    obs_res = dialectic_observe("User prefers async programming", domain="paradigm")
    assert obs_res["success"] is True

    reflect_res = dialectic_reflect()
    assert reflect_res["success"] is True
    assert reflect_res["snapshot"]["nodes_count"] >= 1

    graph_res = dialectic_get_belief_graph()
    assert graph_res["success"] is True

    query_res = dialectic_query_traits("async")
    assert query_res["success"] is True
    assert len(query_res["results"]) >= 1

    rec_fail = dialectic_reconcile("non_existing_tension", "some resolution")
    assert rec_fail["success"] is False

    # Slash command tests
    lines = []
    handle_dialectic_command("/dialectic status", output=lines.append)
    assert any("Dialectic" in line or "DIALECTIC" in line for line in lines)

    lines.clear()
    handle_dialectic_command("/dialectic observe User prefers fast tests", output=lines.append)
    assert any("fast tests" in line for line in lines)

    lines.clear()
    handle_dialectic_command("/dialectic reflect", output=lines.append)
    assert len(lines) >= 1

    lines.clear()
    handle_dialectic_command("/dialectic reset", output=lines.append)
    assert len(lines) >= 1

    reset_global_dialectic_engine()


def test_toolset_includes_dialectic():
    assert "dialectic" in BUILTIN_TOOLSETS
    toolset = get_toolset("dialectic")
    assert toolset is not None
    assert len(toolset.tools) >= 5
    assert "dialectic_observe" in toolset.tools
    assert "dialectic_reflect" in toolset.tools
