"""LLM tool bindings for Metacognitive Reasoning and Tree-of-Thought Engine."""

from __future__ import annotations

from typing import Any

from dream.reasoning.engine import ReasoningEngine

_GLOBAL_REASONING_ENGINE: ReasoningEngine | None = None


def get_global_reasoning_engine() -> ReasoningEngine:
    """Get or initialize singleton ReasoningEngine."""
    global _GLOBAL_REASONING_ENGINE
    if _GLOBAL_REASONING_ENGINE is None:
        _GLOBAL_REASONING_ENGINE = ReasoningEngine()
    return _GLOBAL_REASONING_ENGINE


def reset_global_reasoning_engine() -> None:
    """Reset singleton ReasoningEngine."""
    global _GLOBAL_REASONING_ENGINE
    _GLOBAL_REASONING_ENGINE = None


def reasoning_create_thought_tree(
    goal: str,
    strategy: str = "tree_of_thought",
) -> dict[str, Any]:
    """Initialize a structured reasoning tree for complex problem solving."""
    engine = get_global_reasoning_engine()
    traj, root_id = engine.create_thought_tree(goal, strategy=strategy)
    return {
        "success": True,
        "trajectory": traj.to_dict(),
        "root_node_id": root_id,
        "message": f"\u062f\u0631\u062e\u062a \u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u0628\u0631\u0627\u06cc \u0647\u062f\u0641 '{goal}' \u0627\u06cc\u062c\u0627\u062f \u0634\u062f.",
    }


def reasoning_expand_node(
    trajectory_id: str,
    parent_node_id: str,
    thoughts: list[str],
) -> dict[str, Any]:
    """Branch multiple thought hypotheses from a parent node in the strategy tree."""
    engine = get_global_reasoning_engine()
    try:
        nodes = engine.expand_node(
            trajectory_id=trajectory_id,
            parent_node_id=parent_node_id,
            thoughts=thoughts,
        )
        return {"success": True, "nodes": [n.to_dict() for n in nodes]}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def reasoning_evaluate_node(
    trajectory_id: str,
    node_id: str,
    score: float,
    rationale: str = "",
) -> dict[str, Any]:
    """Score a reasoning node and backpropagate metrics through the tree."""
    engine = get_global_reasoning_engine()
    try:
        node = engine.evaluate_node(
            trajectory_id=trajectory_id,
            node_id=node_id,
            score=score,
            rationale=rationale,
        )
        return {"success": True, "node": node.to_dict()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def reasoning_solve_goal(
    goal: str,
    hypotheses: list[str],
) -> dict[str, Any]:
    """Run full Tree-of-Thought search across hypotheses and return the optimal path."""
    engine = get_global_reasoning_engine()
    try:
        traj, report = engine.solve_goal_with_tree(goal=goal, hypotheses=hypotheses)
        return {
            "success": True,
            "trajectory": traj.to_dict(),
            "report": report,
            "best_answer": traj.final_answer,
            "confidence": traj.confidence,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def reasoning_get_best_path(trajectory_id: str) -> dict[str, Any]:
    """Retrieve the highest-scoring sequence of thought nodes."""
    engine = get_global_reasoning_engine()
    nodes = engine.get_best_trajectory_nodes(trajectory_id)
    return {"success": True, "path": [n.to_dict() for n in nodes]}


def reasoning_get_status() -> dict[str, Any]:
    """Get operational metrics on reasoning trajectories."""
    engine = get_global_reasoning_engine()
    return {"success": True, **engine.get_status()}


def reasoning_reset_all() -> dict[str, Any]:
    """Reset all reasoning trees and state."""
    engine = get_global_reasoning_engine()
    engine.reset()
    return {"success": True, "message": "\u062f\u0631\u062e\u062a\u200c\u0647\u0627\u06cc \u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f\u0646\u062f."}


def get_reasoning_tools() -> list[Any]:
    """Return reasoning tool functions for agent registration."""
    return [
        reasoning_create_thought_tree,
        reasoning_expand_node,
        reasoning_evaluate_node,
        reasoning_solve_goal,
        reasoning_get_best_path,
        reasoning_get_status,
        reasoning_reset_all,
    ]
