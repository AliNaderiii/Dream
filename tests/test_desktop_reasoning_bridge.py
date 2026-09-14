"""Tests for ``reasoning.*`` JSON-RPC bridge methods."""

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.methods_reasoning import (
    reasoning_backtrack,
    reasoning_expand_branch,
    reasoning_get_tree_stats,
    reasoning_mcts_search,
    reasoning_plan_tree,
    reasoning_reset,
    reasoning_step_critique,
    reasoning_synthesize_solution,
)


@pytest.fixture(autouse=True)
async def clean_reasoning_state():
    await reasoning_reset()
    yield
    await reasoning_reset()


@pytest.mark.anyio
async def test_reasoning_plan_tree_and_stats():
    res = await reasoning_plan_tree({"goal": "طراحی سیستم ارکستراسیون عامل‌ها"})
    assert res["status"] == "initialized"
    assert "trajectory_id" in res
    assert "root_node_id" in res

    stats = await reasoning_get_tree_stats({"trajectory_id": res["trajectory_id"]})
    assert stats["status"] == "healthy"
    assert stats["active_nodes_count"] >= 1


@pytest.mark.anyio
async def test_reasoning_expand_and_critique():
    plan = await reasoning_plan_tree({"goal": "مسئله تست"})
    tid = plan["trajectory_id"]
    root_id = plan["root_node_id"]

    expanded = await reasoning_expand_branch(
        {
            "trajectory_id": tid,
            "parent_node_id": root_id,
            "thoughts": ["گام ۱: تفکیک وظایف", "گام ۲: تحلیل ریسک‌ها"],
        }
    )
    assert expanded["status"] == "expanded"
    assert len(expanded["nodes"]) == 2

    critique = await reasoning_step_critique(
        {
            "trajectory_id": tid,
            "node_id": expanded["nodes"][0]["node_id"],
        }
    )
    assert critique["status"] == "critiqued"
    assert "score" in critique


@pytest.mark.anyio
async def test_reasoning_mcts_and_synthesis():
    plan = await reasoning_plan_tree({"goal": "برنامه‌ریزی جامع"})
    tid = plan["trajectory_id"]

    mcts_res = await reasoning_mcts_search({"trajectory_id": tid})
    assert mcts_res["status"] == "searched"

    backtrack_res = await reasoning_backtrack({"trajectory_id": tid, "min_threshold": 0.2})
    assert backtrack_res["status"] == "backtracked"

    synth = await reasoning_synthesize_solution({"trajectory_id": tid})
    assert synth["status"] == "synthesized"
    assert "confidence" in synth


@pytest.mark.anyio
async def test_reasoning_invalid_params_handling():
    with pytest.raises(BridgeError):
        await reasoning_plan_tree({"goal": ""})

    with pytest.raises(BridgeError):
        await reasoning_expand_branch(
            {"trajectory_id": "nonexistent", "parent_node_id": "x", "thoughts": []}
        )
