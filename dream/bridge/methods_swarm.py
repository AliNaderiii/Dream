"""``swarm.*`` JSON-RPC bridge methods.

Discovered automatically by :mod:`dream.bridge.extensions`.
Exposes the Multi-Agent Swarm Neural Mesh, DAG Orchestration, and Consensus Engine:

================================  ================================================
``swarm.get_status``              Retrieve real-time cluster metrics, nodes, and DAG status
``swarm.list_nodes``              List all agent nodes registered in swarm topology
``swarm.spawn_node``              Spawn and register a new agent node in the cluster
``swarm.plan_workflow``           Decompose high-level goal into orchestrated Swarm DAG
``swarm.execute_step``            Execute next available ready tasks in the Swarm DAG
``swarm.run_all``                 Execute all DAG steps to completion
``swarm.vote_consensus``          Deliberate and vote across agents on a proposal
``swarm.broadcast_message``       Publish broadcast event on swarm neural message bus
``swarm.reset``                   Reset swarm cluster, task DAG, and message bus
================================  ================================================
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from dream.bridge.errors import INVALID_PARAMS, BridgeError, invalid_params
from dream.swarm.tools import (
    get_global_swarm_coordinator,
    reset_global_swarm_coordinator,
)

logger = logging.getLogger("dream.bridge.swarm")

__all__ = ["HANDLERS"]


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if params is not None:
        if not isinstance(params, dict):
            raise BridgeError(INVALID_PARAMS, "params must be an object")
        merged.update(params)
    merged.update(kwargs)
    return merged


async def swarm_get_status(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Retrieve real-time cluster status and metrics."""
    _params(params, kwargs)
    coord = get_global_swarm_coordinator()
    summary = await asyncio.to_thread(coord.get_status_summary)
    return {
        "status": "healthy",
        **summary,
    }


async def swarm_list_nodes(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """List all agent nodes in the swarm."""
    _params(params, kwargs)
    coord = get_global_swarm_coordinator()
    nodes = await asyncio.to_thread(coord.topology.list_nodes)
    leader = await asyncio.to_thread(coord.topology.get_leader)
    return {
        "status": "success",
        "nodes": [n.to_dict() for n in nodes],
        "total_nodes": len(nodes),
        "leader_id": leader.node_id if leader else None,
    }


async def swarm_spawn_node(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Spawn and register a new agent node in the cluster.

    Params: ``name`` (str, required), ``role`` (str, optional), ``model`` (str, optional).
    """
    data = _params(params, kwargs)
    name = data.get("name")
    if name is None or not isinstance(name, str) or not name.strip():
        raise invalid_params("name must be a non-empty string")

    role = data.get("role", "specialist")
    if not isinstance(role, str):
        raise invalid_params("role must be a string")

    model = data.get("model", "gpt-4o")
    if not isinstance(model, str):
        raise invalid_params("model must be a string")

    capabilities = data.get("capabilities", [])
    if not isinstance(capabilities, list) or not all(isinstance(c, str) for c in capabilities):
        raise invalid_params("capabilities must be a list of strings")

    coord = get_global_swarm_coordinator()
    node = await asyncio.to_thread(
        coord.topology.register_node,
        name=name.strip(),
        role=role.strip(),
        model=model.strip(),
        capabilities=capabilities,
    )
    return {
        "status": "spawned",
        "node": node.to_dict(),
    }


async def swarm_plan_workflow(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Decompose high-level goal into an orchestrated Swarm DAG.

    Params: ``goal`` (str, required).
    """
    data = _params(params, kwargs)
    goal = data.get("goal")
    if goal is None or not isinstance(goal, str) or not goal.strip():
        raise invalid_params("goal must be a non-empty string")

    coord = get_global_swarm_coordinator()
    tasks = await asyncio.to_thread(coord.plan_workflow, goal=goal.strip())
    return {
        "status": "planned",
        "goal": goal.strip(),
        "tasks": [t.to_dict() for t in tasks],
        "total_tasks": len(tasks),
    }


async def swarm_execute_step(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Execute next ready tasks in the Swarm DAG."""
    _params(params, kwargs)
    coord = get_global_swarm_coordinator()
    res = await asyncio.to_thread(coord.execute_next_step)
    return {
        "status": "executed",
        **res,
    }


async def swarm_run_all(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Execute all tasks in the DAG to completion.

    Params: ``goal`` (str, optional).
    """
    data = _params(params, kwargs)
    goal = data.get("goal")
    if goal is not None and not isinstance(goal, str):
        raise invalid_params("goal must be a string")

    coord = get_global_swarm_coordinator()
    if goal and goal.strip():
        await asyncio.to_thread(coord.plan_workflow, goal.strip())

    res = await asyncio.to_thread(coord.run_all_steps)
    return {
        "status": "completed",
        **res,
    }


async def swarm_vote_consensus(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Deliberate and vote across agents on a proposal.

    Params: ``proposal`` (str, required).
    """
    data = _params(params, kwargs)
    proposal = data.get("proposal")
    if proposal is None or not isinstance(proposal, str) or not proposal.strip():
        raise invalid_params("proposal must be a non-empty string")

    coord = get_global_swarm_coordinator()
    decision = await asyncio.to_thread(
        coord.vote_on_proposal,
        proposal.strip(),
    )
    return {
        "status": "decided",
        "decision": decision.to_dict(),
    }


async def swarm_broadcast_message(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Publish broadcast event on swarm neural message bus.

    Params: ``topic`` (str, required), ``message`` (str, required).
    """
    data = _params(params, kwargs)
    topic = data.get("topic")
    if topic is None or not isinstance(topic, str) or not topic.strip():
        raise invalid_params("topic must be a non-empty string")

    message = data.get("message")
    if message is None or not isinstance(message, str) or not message.strip():
        raise invalid_params("message must be a non-empty string")

    coord = get_global_swarm_coordinator()
    msg = await asyncio.to_thread(
        coord.bus.publish,
        sender_id="agent",
        topic=topic.strip(),
        payload={"message": message.strip()},
    )
    return {
        "status": "published",
        "message": msg.to_dict(),
    }


async def swarm_reset(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Reset swarm cluster, task DAG, and message bus."""
    _params(params, kwargs)
    reset_global_swarm_coordinator()
    return {
        "status": "reset",
        "message": "Swarm cluster reset successfully.",
    }


HANDLERS: dict[str, Any] = {
    "swarm.get_status": swarm_get_status,
    "swarm.list_nodes": swarm_list_nodes,
    "swarm.spawn_node": swarm_spawn_node,
    "swarm.plan_workflow": swarm_plan_workflow,
    "swarm.execute_step": swarm_execute_step,
    "swarm.run_all": swarm_run_all,
    "swarm.vote_consensus": swarm_vote_consensus,
    "swarm.broadcast_message": swarm_broadcast_message,
    "swarm.reset": swarm_reset,
}
