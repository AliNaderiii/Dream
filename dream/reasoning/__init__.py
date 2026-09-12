"""Metacognitive Reasoning, Strategy Tree & Tree-of-Thought Subsystem."""

from __future__ import annotations

from dream.reasoning.engine import ReasoningEngine
from dream.reasoning.evaluator import MetacognitiveEvaluator
from dream.reasoning.slash import handle_reasoning_slash_command
from dream.reasoning.tools import (
    get_global_reasoning_engine,
    get_reasoning_tools,
    reasoning_create_thought_tree,
    reasoning_evaluate_node,
    reasoning_expand_node,
    reasoning_get_best_path,
    reasoning_get_status,
    reasoning_reset_all,
    reasoning_solve_goal,
    reset_global_reasoning_engine,
)
from dream.reasoning.tree import StrategyTree
from dream.reasoning.types import (
    MetacognitiveEvaluation,
    NodeStatus,
    ReasoningStrategy,
    ReasoningTrajectory,
    ThoughtNode,
)

# Auto-register reasoning toolset
try:
    from dream.tools.toolsets import Toolset, register_toolset

    register_toolset(
        Toolset(
            name="reasoning",
            description=(
                "Tree-of-Thought exploration, strategy branching, and "
                "metacognitive self-evaluation."
            ),
            tools=[
                "reasoning_create_thought_tree",
                "reasoning_expand_node",
                "reasoning_evaluate_node",
                "reasoning_solve_goal",
                "reasoning_get_best_path",
                "reasoning_get_status",
                "reasoning_reset_all",
            ],
            metadata={"category": "reasoning", "builtin": True},
        )
    )
except Exception:
    pass

__all__ = [
    "MetacognitiveEvaluation",
    "MetacognitiveEvaluator",
    "NodeStatus",
    "ReasoningEngine",
    "ReasoningStrategy",
    "ReasoningTrajectory",
    "StrategyTree",
    "ThoughtNode",
    "get_global_reasoning_engine",
    "get_reasoning_tools",
    "handle_reasoning_slash_command",
    "reasoning_create_thought_tree",
    "reasoning_evaluate_node",
    "reasoning_expand_node",
    "reasoning_get_best_path",
    "reasoning_get_status",
    "reasoning_reset_all",
    "reasoning_solve_goal",
    "reset_global_reasoning_engine",
]
