"""Unit and bridge tests for ``swarm.*`` JSON-RPC endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.methods_swarm import (
    swarm_broadcast_message,
    swarm_execute_step,
    swarm_get_status,
    swarm_list_nodes,
    swarm_plan_workflow,
    swarm_reset,
    swarm_run_all,
    swarm_spawn_node,
    swarm_vote_consensus,
)


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def clean_swarm_state():
    _run(swarm_reset())
    yield
    _run(swarm_reset())


def test_swarm_status_and_nodes():
    status = _run(swarm_get_status())
    assert status["status"] == "healthy"
    assert "nodes_count" in status

    nodes = _run(swarm_list_nodes())
    assert nodes["status"] == "success"
    assert nodes["total_nodes"] >= 1


def test_swarm_spawn_node():
    res = _run(
        swarm_spawn_node(
            {
                "name": "Security Auditor",
                "role": "critic",
                "model": "gpt-4o",
                "capabilities": ["audit", "fuzzing"],
            }
        )
    )
    assert res["status"] == "spawned"
    assert res["node"]["name"] == "Security Auditor"
    assert res["node"]["role"] == "critic"


def test_swarm_plan_and_execute_workflow():
    plan = _run(swarm_plan_workflow({"goal": "طراحی سیستم ارکستراسیون سوارم"}))
    assert plan["status"] == "planned"
    assert plan["total_tasks"] == 4
    assert len(plan["tasks"]) == 4

    step_res = _run(swarm_execute_step())
    assert step_res["status"] == "executed"


def test_swarm_run_all():
    res = _run(swarm_run_all({"goal": "پیاده‌سازی ماژول شبکه عصبی"}))
    assert res["status"] == "completed"
    assert res["is_complete"] is True
    assert res["progress"]["completed"] >= 1


def test_swarm_vote_consensus():
    decision = _run(
        swarm_vote_consensus(
            {"proposal": "مهاجرت به معماری گذرگاه رویداد ناهمگام"}
        )
    )
    assert decision["status"] == "decided"
    assert "decision" in decision
    assert decision["decision"]["passed"] is True


def test_swarm_broadcast_message():
    res = _run(
        swarm_broadcast_message(
            {"topic": "cluster.heartbeat", "message": "all nodes operational"}
        )
    )
    assert res["status"] == "published"
    assert res["message"]["topic"] == "cluster.heartbeat"


def test_swarm_invalid_params():
    with pytest.raises(BridgeError):
        _run(swarm_spawn_node({"name": ""}))

    with pytest.raises(BridgeError):
        _run(swarm_plan_workflow({"goal": ""}))

    with pytest.raises(BridgeError):
        _run(swarm_vote_consensus({"proposal": ""}))
