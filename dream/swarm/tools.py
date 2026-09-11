"""LLM Tool bindings for Multi-Agent Swarm orchestration and consensus."""

from __future__ import annotations

from typing import Any

from dream.swarm.coordinator import SwarmCoordinator

_GLOBAL_SWARM_COORDINATOR: SwarmCoordinator | None = None


def get_global_swarm_coordinator() -> SwarmCoordinator:
    """Get or create singleton SwarmCoordinator."""
    global _GLOBAL_SWARM_COORDINATOR
    if _GLOBAL_SWARM_COORDINATOR is None:
        _GLOBAL_SWARM_COORDINATOR = SwarmCoordinator()
    return _GLOBAL_SWARM_COORDINATOR


def reset_global_swarm_coordinator() -> None:
    """Reset singleton SwarmCoordinator for tests."""
    global _GLOBAL_SWARM_COORDINATOR
    _GLOBAL_SWARM_COORDINATOR = None


def swarm_spawn_node(
    name: str,
    role: str = "specialist",
    model: str = "gpt-4o",
    capabilities: list[str] | None = None,
) -> dict[str, Any]:
    """Spawn and register a new specialized agent node in the swarm cluster."""
    coord = get_global_swarm_coordinator()
    node = coord.topology.register_node(
        name=name,
        role=role,
        model=model,
        capabilities=capabilities or [],
    )
    return node.to_dict()


def swarm_plan_workflow(goal: str) -> list[dict[str, Any]]:
    """Decompose a complex goal into an orchestrated Swarm Task DAG."""
    coord = get_global_swarm_coordinator()
    tasks = coord.plan_workflow(goal)
    return [t.to_dict() for t in tasks]


def swarm_execute_step() -> dict[str, Any]:
    """Execute the next available ready tasks in the Swarm DAG."""
    coord = get_global_swarm_coordinator()
    return coord.execute_next_step()


def swarm_run_all(goal: str = "") -> dict[str, Any]:
    """Plan (if goal provided) and execute all tasks in the Swarm DAG to completion."""
    coord = get_global_swarm_coordinator()
    if goal:
        coord.plan_workflow(goal)
    return coord.run_all_steps()


def swarm_reach_consensus(proposal: str) -> dict[str, Any]:
    """Initiate a multi-agent voting and deliberation process across swarm nodes."""
    coord = get_global_swarm_coordinator()
    decision = coord.vote_on_proposal(proposal)
    return decision.to_dict()


def swarm_get_status() -> dict[str, Any]:
    """Retrieve comprehensive real-time status of the Swarm cluster."""
    coord = get_global_swarm_coordinator()
    return coord.get_status_summary()


def swarm_broadcast_message(topic: str, message: str) -> dict[str, Any]:
    """Publish a broadcast message to all nodes on the swarm event bus."""
    coord = get_global_swarm_coordinator()
    msg = coord.bus.publish(
        sender_id="agent",
        topic=topic,
        payload={"message": message},
    )
    return msg.to_dict()


def get_swarm_tools() -> list[Any]:
    """Return all Swarm management tools for LLM agent binding."""
    return [
        swarm_spawn_node,
        swarm_plan_workflow,
        swarm_execute_step,
        swarm_run_all,
        swarm_reach_consensus,
        swarm_get_status,
        swarm_broadcast_message,
    ]
