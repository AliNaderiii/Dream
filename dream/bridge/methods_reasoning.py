"""``reasoning.*`` JSON-RPC bridge methods.

Discovered automatically by :mod:`dream.bridge.extensions`.
Exposes the Tree-of-Thought & Self-Reflective MCTS Reasoning Planner:

================================  ================================================
``reasoning.plan_tree``           Initialize a Tree-of-Thought search tree for a goal
``reasoning.expand_branch``       Expand alternative thought hypotheses from a node
``reasoning.step_critique``       Perform self-reflective critique on a node
``reasoning.mcts_search``         Execute MCTS search, evaluation, and backpropagation
``reasoning.backtrack``           Prune unviable branches and update exploration frontier
``reasoning.synthesize_solution`` Synthesize final structured solution from winning path
``reasoning.get_tree_stats``      Retrieve live tree size, depth, and best trajectory
``reasoning.reset``               Clear reasoning search trees and caches
================================  ================================================
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from dream.bridge.errors import invalid_params
from dream.reasoning.tools import get_global_reasoning_engine

logger = logging.getLogger("dream.bridge.reasoning")

__all__ = ["HANDLERS"]


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(params, dict):
        merged.update(params)
    merged.update(kwargs)
    return merged


async def reasoning_plan_tree(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Initialize a Tree-of-Thought exploration tree.

    Params: ``goal`` (str, required), ``strategy`` (str, optional).
    """
    data = _params(params, kwargs)
    goal = data.get("goal")
    if goal is None or not isinstance(goal, str) or not goal.strip():
        raise invalid_params("goal must be a non-empty string")

    strategy = data.get("strategy", "tree_of_thought")
    if not isinstance(strategy, str):
        raise invalid_params("strategy must be a string")

    engine = get_global_reasoning_engine()
    traj, root_id = await asyncio.to_thread(
        engine.create_thought_tree,
        goal=goal.strip(),
        strategy=strategy,
    )
    return {
        "status": "initialized",
        "trajectory_id": traj.trajectory_id,
        "root_node_id": root_id,
        "trajectory": traj.to_tree_dict(),
    }


async def reasoning_expand_branch(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Expand candidate branches from a parent thought node.

    Params: ``trajectory_id`` (str), ``parent_node_id`` (str), ``thoughts`` (list[str]).
    """
    data = _params(params, kwargs)
    tid = data.get("trajectory_id")
    if tid is None or not isinstance(tid, str):
        raise invalid_params("trajectory_id must be a string")

    parent_id = data.get("parent_node_id")
    if parent_id is None or not isinstance(parent_id, str):
        raise invalid_params("parent_node_id must be a string")

    thoughts = data.get("thoughts")
    if thoughts is None or not isinstance(thoughts, list):
        raise invalid_params("thoughts must be a list of strings")

    sanitized_thoughts: list[str] = []
    for item in thoughts:
        if not isinstance(item, str) or not item.strip():
            raise invalid_params("each thought must be a non-empty string")
        sanitized_thoughts.append(item.strip())

    if not sanitized_thoughts:
        raise invalid_params("thoughts list must not be empty")

    engine = get_global_reasoning_engine()
    try:
        new_nodes = await asyncio.to_thread(
            engine.expand_node,
            trajectory_id=tid,
            parent_node_id=parent_id,
            thoughts=sanitized_thoughts,
        )
    except KeyError as exc:
        raise invalid_params(str(exc)) from exc

    return {
        "status": "expanded",
        "trajectory_id": tid,
        "parent_node_id": parent_id,
        "nodes": [n.to_dict() for n in new_nodes],
    }


async def reasoning_step_critique(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Perform self-reflective critique on a node.

    Params: ``trajectory_id`` (str), ``node_id`` (str).
    """
    data = _params(params, kwargs)
    tid = data.get("trajectory_id")
    if tid is None or not isinstance(tid, str):
        raise invalid_params("trajectory_id must be a string")

    node_id = data.get("node_id")
    if node_id is None or not isinstance(node_id, str):
        raise invalid_params("node_id must be a string")

    engine = get_global_reasoning_engine()
    try:
        result = await asyncio.to_thread(
            engine.step_critique,
            trajectory_id=tid,
            node_id=node_id,
        )
    except KeyError as exc:
        raise invalid_params(str(exc)) from exc

    return {"status": "critiqued", **result}


async def reasoning_mcts_search(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Execute MCTS search, evaluation, and backpropagation.

    Params: ``trajectory_id`` (str), ``candidate_thoughts`` (list[str], optional).
    """
    data = _params(params, kwargs)
    tid = data.get("trajectory_id")
    if tid is None or not isinstance(tid, str):
        raise invalid_params("trajectory_id must be a string")

    candidates = data.get("candidate_thoughts")
    if candidates is not None:
        if not isinstance(candidates, list) or not all(
            isinstance(c, str) for c in candidates
        ):
            raise invalid_params("candidate_thoughts must be a list of strings")

    engine = get_global_reasoning_engine()
    try:
        result = await asyncio.to_thread(
            engine.mcts_search_step,
            trajectory_id=tid,
            candidate_thoughts=candidates,
        )
    except KeyError as exc:
        raise invalid_params(str(exc)) from exc

    return {"status": "searched", **result}


async def reasoning_backtrack(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Prune unviable branches and update exploration frontier.

    Params: ``trajectory_id`` (str), ``min_threshold`` (float, optional).
    """
    data = _params(params, kwargs)
    tid = data.get("trajectory_id")
    if tid is None or not isinstance(tid, str):
        raise invalid_params("trajectory_id must be a string")

    threshold = data.get("min_threshold", 0.35)
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise invalid_params("min_threshold must be a float between 0 and 1")

    engine = get_global_reasoning_engine()
    try:
        result = await asyncio.to_thread(
            engine.backtrack_and_prune,
            trajectory_id=tid,
            min_threshold=float(threshold),
        )
    except KeyError as exc:
        raise invalid_params(str(exc)) from exc

    return {"status": "backtracked", **result}


async def reasoning_synthesize_solution(
    params: Any = None, **kwargs: Any
) -> dict[str, Any]:
    """Synthesize final solution from winning trajectory path.

    Params: ``trajectory_id`` (str).
    """
    data = _params(params, kwargs)
    tid = data.get("trajectory_id")
    if tid is None or not isinstance(tid, str):
        raise invalid_params("trajectory_id must be a string")

    engine = get_global_reasoning_engine()
    try:
        result = await asyncio.to_thread(
            engine.synthesize_solution,
            trajectory_id=tid,
        )
    except KeyError as exc:
        raise invalid_params(str(exc)) from exc

    return {"status": "synthesized", **result}


async def reasoning_get_tree_stats(
    params: Any = None, **kwargs: Any
) -> dict[str, Any]:
    """Retrieve live tree size, depth, and best trajectory.

    Params: ``trajectory_id`` (str, optional).
    """
    data = _params(params, kwargs)
    tid = data.get("trajectory_id")
    if tid is not None and not isinstance(tid, str):
        raise invalid_params("trajectory_id must be a string")

    engine = get_global_reasoning_engine()
    return await asyncio.to_thread(engine.get_tree_stats, trajectory_id=tid)


async def reasoning_reset(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Clear reasoning search trees and caches."""
    engine = get_global_reasoning_engine()
    await asyncio.to_thread(engine.reset)
    return {"status": "reset", "message": "Reasoning trees cleared."}


HANDLERS: dict[str, Any] = {
    "reasoning.plan_tree": reasoning_plan_tree,
    "reasoning.expand_branch": reasoning_expand_branch,
    "reasoning.step_critique": reasoning_step_critique,
    "reasoning.mcts_search": reasoning_mcts_search,
    "reasoning.backtrack": reasoning_backtrack,
    "reasoning.synthesize_solution": reasoning_synthesize_solution,
    "reasoning.get_tree_stats": reasoning_get_tree_stats,
    "reasoning.reset": reasoning_reset,
}
