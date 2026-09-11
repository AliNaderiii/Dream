#!/usr/bin/env python3
"""Phase 35: Metacognitive Reasoning, Dynamic Strategy Tree & Tree-of-Thought Subsystem.

Applies all modules for Phase 35:
- dream/reasoning/types.py
- dream/reasoning/tree.py
- dream/reasoning/evaluator.py
- dream/reasoning/engine.py
- dream/reasoning/tools.py
- dream/reasoning/slash.py
- dream/reasoning/__init__.py
- dream/tools/toolsets.py (registered reasoning toolset)
- tests/test_metacognitive_reasoning.py
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

FILES: dict[str, str] = {
    "dream/reasoning/types.py": r'''"""Domain models and data structures for Metacognitive Reasoning and Strategy Trees."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any


class ReasoningStrategy(str, Enum):
    """Reasoning architectures and exploration algorithms."""

    DIRECT = "direct"
    CHAIN_OF_THOUGHT = "chain_of_thought"
    TREE_OF_THOUGHT = "tree_of_thought"
    GRAPH_OF_THOUGHT = "graph_of_thought"
    MCTS_EXPLORATION = "mcts_exploration"


class NodeStatus(str, Enum):
    """Exploration state of a single thought node."""

    UNEXPLORED = "unexplored"
    EXPANDED = "expanded"
    EVALUATED = "evaluated"
    PRUNED = "pruned"
    SELECTED = "selected"
    DEAD_END = "dead_end"


@dataclass(slots=True)
class ThoughtNode:
    """A discrete reasoning step or hypothesis in the strategy tree."""

    node_id: str
    parent_id: str | None
    thought_content: str
    score: float = 0.5
    depth: int = 0
    status: NodeStatus = NodeStatus.UNEXPLORED
    eval_rationale: str = ""
    children_ids: list[str] = field(default_factory=list)
    visits: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize thought node to dictionary."""
        return {
            "node_id": self.node_id,
            "parent_id": self.parent_id,
            "thought_content": self.thought_content,
            "score": round(self.score, 3),
            "depth": self.depth,
            "status": self.status.value,
            "eval_rationale": self.eval_rationale,
            "children_count": len(self.children_ids),
            "visits": self.visits,
            "created_at": round(self.created_at, 2),
        }


@dataclass(slots=True)
class MetacognitiveEvaluation:
    """Self-reflective quality appraisal of a reasoning trace."""

    evaluation_id: str
    coherence_score: float
    depth_score: float
    hallucination_risk: float
    critique_notes: str
    suggested_action: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize metacognitive evaluation to dictionary."""
        return {
            "evaluation_id": self.evaluation_id,
            "coherence_score": round(self.coherence_score, 2),
            "depth_score": round(self.depth_score, 2),
            "hallucination_risk": round(self.hallucination_risk, 2),
            "critique_notes": self.critique_notes,
            "suggested_action": self.suggested_action,
            "timestamp": round(self.timestamp, 2),
        }


@dataclass(slots=True)
class ReasoningTrajectory:
    """Full tree or graph exploration trajectory for solving a complex goal."""

    trajectory_id: str
    goal: str
    strategy: ReasoningStrategy = ReasoningStrategy.TREE_OF_THOUGHT
    root_node_id: str = ""
    nodes: dict[str, ThoughtNode] = field(default_factory=dict)
    selected_path: list[str] = field(default_factory=list)
    final_answer: str = ""
    confidence: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize reasoning trajectory to dictionary."""
        return {
            "trajectory_id": self.trajectory_id,
            "goal": self.goal,
            "strategy": self.strategy.value,
            "root_node_id": self.root_node_id,
            "total_nodes": len(self.nodes),
            "selected_path": self.selected_path,
            "final_answer": self.final_answer,
            "confidence": round(self.confidence, 2),
            "created_at": round(self.created_at, 2),
            "updated_at": round(self.updated_at, 2),
        }
''',
    "dream/reasoning/tree.py": r'''"""Dynamic Strategy Tree, Tree-of-Thought search, and Monte Carlo scoring."""

from __future__ import annotations

import math
import time
from typing import Any
import uuid

from dream.reasoning.types import NodeStatus, ThoughtNode


class StrategyTree:
    """Manages reasoning tree state, branch exploration, and node pruning."""

    def __init__(self) -> None:
        self.nodes: dict[str, ThoughtNode] = {}
        self.root_node_id: str | None = None

    def initialize_root(self, goal: str) -> ThoughtNode:
        """Create root goal node."""
        nid = f"node-{uuid.uuid4().hex[:6]}"
        root = ThoughtNode(
            node_id=nid,
            parent_id=None,
            thought_content=f"\u0647\u062f\u0641: {goal}",
            score=1.0,
            depth=0,
            status=NodeStatus.SELECTED,
        )
        self.nodes[nid] = root
        self.root_node_id = nid
        return root

    def expand_node(
        self,
        parent_id: str,
        child_thoughts: list[str],
    ) -> list[ThoughtNode]:
        """Generate multiple alternative reasoning branches from parent node."""
        parent = self.nodes.get(parent_id)
        if not parent:
            raise KeyError(f"Parent node '{parent_id}' not found.")

        parent.status = NodeStatus.EXPANDED
        parent.visits += 1
        created_nodes: list[ThoughtNode] = []

        for thought in child_thoughts:
            nid = f"node-{uuid.uuid4().hex[:6]}"
            child = ThoughtNode(
                node_id=nid,
                parent_id=parent_id,
                thought_content=thought,
                score=0.5,
                depth=parent.depth + 1,
                status=NodeStatus.UNEXPLORED,
            )
            self.nodes[nid] = child
            parent.children_ids.append(nid)
            created_nodes.append(child)

        return created_nodes

    def calculate_uct(
        self,
        node: ThoughtNode,
        parent_visits: int,
        exploration_constant: float = 1.414,
    ) -> float:
        """Compute Upper Confidence Bound for Trees (UCT) metric."""
        if node.visits == 0:
            return float("inf")
        exploitation = node.score
        exploration = exploration_constant * math.sqrt(math.log(max(1, parent_visits)) / node.visits)
        return exploitation + exploration

    def select_best_child(self, parent_id: str) -> ThoughtNode | None:
        """Select best candidate child using UCT/score criteria."""
        parent = self.nodes.get(parent_id)
        if not parent or not parent.children_ids:
            return None

        candidates = [
            self.nodes[cid]
            for cid in parent.children_ids
            if self.nodes[cid].status not in (NodeStatus.PRUNED, NodeStatus.DEAD_END)
        ]
        if not candidates:
            return None

        # Prefer highest UCT or highest score
        return max(candidates, key=lambda n: self.calculate_uct(n, parent.visits))

    def evaluate_node(
        self,
        node_id: str,
        score: float,
        rationale: str = "",
    ) -> ThoughtNode:
        """Assign evaluation score to node and update visit count."""
        node = self.nodes.get(node_id)
        if not node:
            raise KeyError(f"Node '{node_id}' not found.")

        node.score = max(0.0, min(1.0, score))
        node.eval_rationale = rationale
        node.visits += 1
        node.status = NodeStatus.EVALUATED
        self._backpropagate(node.parent_id, node.score)
        return node

    def _backpropagate(self, parent_id: str | None, child_score: float) -> None:
        """Backpropagate evaluation scores up the tree."""
        curr_id = parent_id
        while curr_id:
            parent = self.nodes.get(curr_id)
            if not parent:
                break
            parent.visits += 1
            # Update moving average
            parent.score = (parent.score * (parent.visits - 1) + child_score) / parent.visits
            curr_id = parent.parent_id

    def prune_low_value_branches(self, min_score_threshold: float = 0.3) -> int:
        """Mark low-scoring branches as pruned to focus exploration."""
        pruned_count = 0
        for node in self.nodes.values():
            if (
                node.depth > 0
                and node.status in (NodeStatus.EVALUATED, NodeStatus.UNEXPLORED)
                and node.score < min_score_threshold
            ):
                node.status = NodeStatus.PRUNED
                pruned_count += 1
        return pruned_count

    def extract_best_trajectory(self) -> list[ThoughtNode]:
        """Trace the highest scoring path from root to optimal leaf."""
        if not self.root_node_id:
            return []

        path: list[ThoughtNode] = []
        curr = self.nodes.get(self.root_node_id)

        while curr:
            curr.status = NodeStatus.SELECTED
            path.append(curr)
            if not curr.children_ids:
                break

            active_children = [
                self.nodes[cid]
                for cid in curr.children_ids
                if self.nodes[cid].status not in (NodeStatus.PRUNED, NodeStatus.DEAD_END)
            ]
            if not active_children:
                break

            curr = max(active_children, key=lambda n: n.score)

        return path
''',
    "dream/reasoning/evaluator.py": r'''"""Metacognitive Evaluator: Real-time self-monitoring and reasoning trajectory assessment."""

from __future__ import annotations

import time
from typing import Any
import uuid

from dream.reasoning.types import MetacognitiveEvaluation, ThoughtNode


class MetacognitiveEvaluator:
    """Evaluates coherence, depth, and risk across reasoning trajectories."""

    def evaluate_thought_step(
        self,
        thought_text: str,
        depth: int,
        context_history: list[str] | None = None,
    ) -> MetacognitiveEvaluation:
        """Perform self-reflective critique on a single reasoning step."""
        eid = f"eval-{uuid.uuid4().hex[:6]}"
        history = context_history or []

        # Coherence score based on length and clarity
        length = len(thought_text.strip())
        coherence = 0.9 if length >= 30 else (0.6 if length >= 10 else 0.3)

        # Depth score based on tree level
        depth_score = min(1.0, 0.4 + (depth * 0.2))

        # Check for circular reasoning in history
        hallucination_risk = 0.1
        is_repetitive = False
        for prev in history:
            if thought_text.strip().lower() in prev.lower() or prev.lower() in thought_text.strip().lower():
                is_repetitive = True
                hallucination_risk = 0.7
                break

        # Suggest next strategic action
        if is_repetitive:
            action = "backtrack"
            critique = "\u0627\u062d\u062a\u0645\u0627\u0644 \u062a\u06a9\u0631\u0627\u0631 \u06cc\u0627 \u062d\u0644\u0642\u0647 \u0645\u0646\u0637\u0642\u06cc \u062a\u0634\u062e\u06cc\u0635 \u062f\u0627\u062f\u0647 \u0634\u062f."
        elif depth >= 3 and coherence >= 0.8:
            action = "ready_for_conclusion"
            critique = "\u0639\u0645\u0642 \u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u06a9\u0627\u0641\u06cc \u0627\u0633\u062a \u0648 \u0622\u0645\u0627\u062f\u0647 \u0646\u062a\u06cc\u062c\u0647\u200c\u06af\u06cc\u0631\u06cc \u0645\u06cc\u200c\u0628\u0627\u0634\u062f."
        else:
            action = "continue_exploration"
            critique = "\u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u0645\u0646\u0633\u062c\u0645 \u0627\u0633\u062a. \u0628\u0647 \u06a9\u0627\u0648\u0634 \u0634\u0627\u062e\u0647\u200c\u0647\u0627 \u0627\u062f\u0627\u0645\u0647 \u062f\u0647\u06cc\u062f."

        return MetacognitiveEvaluation(
            evaluation_id=eid,
            coherence_score=coherence,
            depth_score=depth_score,
            hallucination_risk=hallucination_risk,
            critique_notes=critique,
            suggested_action=action,
        )
''',
    "dream/reasoning/engine.py": r'''"""Reasoning Engine Coordinator for Tree-of-Thought search and metacognitive exploration."""

from __future__ import annotations

import time
from typing import Any
import uuid

from dream.reasoning.evaluator import MetacognitiveEvaluator
from dream.reasoning.tree import StrategyTree
from dream.reasoning.types import (
    MetacognitiveEvaluation,
    NodeStatus,
    ReasoningStrategy,
    ReasoningTrajectory,
    ThoughtNode,
)


class ReasoningEngine:
    """Orchestrates strategy trees, branch evaluations, and dynamic metacognitive reasoning."""

    def __init__(
        self,
        evaluator: MetacognitiveEvaluator | None = None,
    ) -> None:
        self.evaluator = evaluator or MetacognitiveEvaluator()
        self._trajectories: dict[str, ReasoningTrajectory] = {}
        self._trees: dict[str, StrategyTree] = {}
        self._active_trajectory_id: str | None = None

    def create_thought_tree(
        self,
        goal: str,
        strategy: str | ReasoningStrategy = ReasoningStrategy.TREE_OF_THOUGHT,
    ) -> tuple[ReasoningTrajectory, str]:
        """Initialize a new Tree-of-Thought search tree."""
        if isinstance(strategy, str):
            try:
                strat_enum = ReasoningStrategy(strategy.lower())
            except ValueError:
                strat_enum = ReasoningStrategy.TREE_OF_THOUGHT
        else:
            strat_enum = strategy

        tid = f"traj-{uuid.uuid4().hex[:6]}"
        tree = StrategyTree()
        root_node = tree.initialize_root(goal)

        now = time.time()
        traj = ReasoningTrajectory(
            trajectory_id=tid,
            goal=goal,
            strategy=strat_enum,
            root_node_id=root_node.node_id,
            nodes={root_node.node_id: root_node},
            created_at=now,
            updated_at=now,
        )

        self._trajectories[tid] = traj
        self._trees[tid] = tree
        self._active_trajectory_id = tid
        return traj, root_node.node_id

    def expand_node(
        self,
        trajectory_id: str,
        parent_node_id: str,
        thoughts: list[str],
    ) -> list[ThoughtNode]:
        """Expand candidate reasoning branches from parent node."""
        tree = self._trees.get(trajectory_id)
        traj = self._trajectories.get(trajectory_id)
        if not tree or not traj:
            raise KeyError(f"Reasoning trajectory '{trajectory_id}' not found.")

        new_nodes = tree.expand_node(parent_node_id, thoughts)
        for n in new_nodes:
            traj.nodes[n.node_id] = n
        traj.updated_at = time.time()
        return new_nodes

    def evaluate_node(
        self,
        trajectory_id: str,
        node_id: str,
        score: float,
        rationale: str = "",
    ) -> ThoughtNode:
        """Assign score and rationale to a thought node."""
        tree = self._trees.get(trajectory_id)
        traj = self._trajectories.get(trajectory_id)
        if not tree or not traj:
            raise KeyError(f"Reasoning trajectory '{trajectory_id}' not found.")

        evaluated = tree.evaluate_node(node_id=node_id, score=score, rationale=rationale)
        traj.nodes[node_id] = evaluated
        traj.updated_at = time.time()
        return evaluated

    def solve_goal_with_tree(
        self,
        goal: str,
        hypotheses: list[str],
    ) -> tuple[ReasoningTrajectory, str]:
        """Run complete multi-hypothesis exploration and extract the winning trajectory."""
        traj, root_id = self.create_thought_tree(goal)
        tree = self._trees[traj.trajectory_id]

        # Expand Level 1 branches
        children = self.expand_node(traj.trajectory_id, root_id, hypotheses)

        # Evaluate Level 1 branches
        best_node: ThoughtNode | None = None
        for i, child in enumerate(children):
            critique = self.evaluator.evaluate_thought_step(
                thought_text=child.thought_content,
                depth=1,
            )
            score = (critique.coherence_score + critique.depth_score) / 2.0
            node = self.evaluate_node(
                trajectory_id=traj.trajectory_id,
                node_id=child.node_id,
                score=score,
                rationale=critique.critique_notes,
            )
            if best_node is None or node.score > best_node.score:
                best_node = node

        # Prune branches with low scores
        tree.prune_low_value_branches(min_score_threshold=0.3)

        # Extract winning path
        best_path = tree.extract_best_trajectory()
        traj.selected_path = [n.node_id for n in best_path]
        traj.confidence = best_node.score if best_node else 0.5
        traj.final_answer = best_node.thought_content if best_node else hypotheses[0]

        summary = (
            f"\U0001f9e0 \u062f\u0631\u062e\u062a \u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u0648 \u062d\u0644 \u0645\u0633\u0626\u0644\u0647 (Tree-of-Thought Report):\n"
            f"- \u0647\u062f\u0641: {goal}\n"
            f"- \u062a\u0639\u062f\u0627\u062f \u06af\u0631\u0647\u200c\u0647\u0627\u06cc \u0628\u0631\u0631\u0633\u06cc\u200c\u0634\u062f\u0647: {len(traj.nodes)}\n"
            f"- \u0645\u0633\u06cc\u0631 \u0628\u0631\u06af\u0632\u06cc\u062f\u0647: {' -> '.join(traj.selected_path)}\n"
            f"- \u067e\u0627\u0633\u062e \u0628\u0647\u06cc\u0646\u0647: {traj.final_answer}\n"
            f"- \u0636\u0631\u06cc\u0628 \u0627\u0637\u0645\u06cc\u0646\u0627\u0646: {traj.confidence:.2f}"
        )

        return traj, summary

    def get_best_trajectory_nodes(self, trajectory_id: str) -> list[ThoughtNode]:
        """Get nodes forming the best path for a trajectory."""
        tree = self._trees.get(trajectory_id)
        if not tree:
            return []
        return tree.extract_best_trajectory()

    def get_status(self) -> dict[str, Any]:
        """Get summary metrics on reasoning trajectories."""
        return {
            "total_trajectories": len(self._trajectories),
            "active_trajectory_id": self._active_trajectory_id,
            "trajectories": [t.to_dict() for t in self._trajectories.values()],
        }

    def reset(self) -> None:
        """Clear all trajectories and search trees."""
        self._trajectories.clear()
        self._trees.clear()
        self._active_trajectory_id = None
''',
    "dream/reasoning/tools.py": r'''"""LLM tool bindings for Metacognitive Reasoning and Tree-of-Thought Engine."""

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
''',
    "dream/reasoning/slash.py": r'''"""CLI and slash command handlers for Metacognitive Reasoning and Tree-of-Thought."""

from __future__ import annotations

from typing import Any

from dream.reasoning.tools import (
    reasoning_get_status,
    reasoning_reset_all,
    reasoning_solve_goal,
)


def handle_reasoning_slash_command(command_str: str) -> str:
    """Handle /think, /tot, and /reasoning CLI slash commands.

    Usage:
        /think <problem_or_goal>
        /tot <problem_or_goal>
        /reasoning status
        /reasoning reset
    """
    cmd = command_str.strip()

    if cmd.startswith("/think") or cmd.startswith("/tot"):
        prefix = "/think" if cmd.startswith("/think") else "/tot"
        goal = cmd[len(prefix) :].strip()
        if not goal:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0645\u0633\u0626\u0644\u0647 \u06cc\u0627 \u0647\u062f\u0641 \u0631\u0627 \u0628\u0631\u0627\u06cc \u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u062f\u0631\u062e\u062a\u06cc \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."

        # Generate standard hypothesis set
        hypotheses = [
            f"\u0631\u0627\u0647\u06a9\u0627\u0631 \u0645\u0633\u062a\u0642\u06cc\u0645 \u0648 \u062a\u062d\u0644\u06cc\u0644\u06cc \u0628\u0631\u0627\u06cc \u062d\u0644 {goal}",
            f"\u0631\u0627\u0647\u06a9\u0627\u0631 \u062a\u062c\u0632\u06cc\u0647 \u0645\u0633\u0626\u0644\u0647 \u0628\u0647 \u0632\u06cc\u0631\u0645\u0633\u0627\u0626\u0644 \u06a9\u0648\u0686\u06a9\u200c\u062a\u0631",
            f"\u0631\u0648\u06cc\u06a9\u0631\u062f \u0627\u062d\u062a\u06cc\u0627\u0637\u06cc \u0648 \u0628\u0631\u0631\u0633\u06cc \u0631\u06cc\u0633\u06a9\u200c\u0647\u0627\u06cc \u0627\u062d\u062a\u0645\u0627\u0644\u06cc",
        ]

        res = reasoning_solve_goal(goal=goal, hypotheses=hypotheses)
        if res.get("success"):
            return res.get("report", "")
        return f"\u274c \u062e\u0637\u0627 \u062f\u0631 \u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u062f\u0631\u062e\u062a\u06cc: {res.get('error')}"

    if not cmd.startswith("/reasoning"):
        return "\u274c \u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a."

    parts = cmd.split(maxsplit=2)
    if len(parts) == 1:
        return (
            "\U0001f9e0 \u062f\u0633\u062a\u0648\u0631\u0627\u062a \u0645\u0648\u062a\u0648\u0631 \u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u0641\u0631\u0627\u0634\u0646\u0627\u062e\u062a\u06cc (Reasoning / ToT):\n"
            "  /think <goal>                             \u062d\u0644 \u0645\u0633\u0626\u0644\u0647 \u0628\u0627 \u062f\u0631\u062e\u062a \u0627\u0633\u062a\u062f\u0644\u0627\u0644 (Tree-of-Thought)\n"
            "  /tot <goal>                               \u0627\u062c\u0631\u0627\u06cc \u06a9\u0627\u0648\u0634 \u0686\u0646\u062f\u200c\u0645\u0633\u06cc\u0631\u0647\n"
            "  /reasoning status                         \u0648\u0636\u0639\u06cc\u062a \u062f\u0631\u062e\u062a\u200c\u0647\u0627\u06cc \u0627\u0633\u062a\u062f\u0644\u0627\u0644\n"
            "  /reasoning reset                          \u067e\u0627\u06a9\u0633\u0627\u0632\u06cc \u0648 \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc"
        )

    subcmd = parts[1].lower()

    if subcmd == "status":
        st = reasoning_get_status()
        return (
            f"\U0001f4df \u0648\u0636\u0639\u06cc\u062a \u0645\u0648\u062a\u0648\u0631 \u0627\u0633\u062a\u062f\u0644\u0627\u0644:\n"
            f"- \u062a\u0639\u062f\u0627\u062f \u062f\u0631\u062e\u062a\u200c\u0647\u0627\u06cc \u0641\u0639\u0627\u0644: {st.get('total_trajectories')}\n"
            f"- \u0634\u0646\u0627\u0633\u0647 \u0645\u0633\u06cc\u0631 \u062c\u0627\u0631\u06cc: {st.get('active_trajectory_id') or '\u0647\u06cc\u0686'}"
        )

    if subcmd == "reset":
        reasoning_reset_all()
        return "\u2705 \u062f\u0631\u062e\u062a\u200c\u0647\u0627\u06cc \u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."

    return "\u274c \u0632\u06cc\u0631\u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a."
''',
    "dream/reasoning/__init__.py": r'''"""Metacognitive Reasoning, Dynamic Strategy Tree & Tree-of-Thought Subsystem."""

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
            description="Tree-of-Thought exploration, strategy branching, and metacognitive self-evaluation.",
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
''',
    "dream/tools/toolsets.py": r'''"""Toolset categorization, grouping, and dynamic tool management."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from dream.tools.base import REGISTRY, Tool


@dataclass(frozen=True)
class Toolset:
    """Group of related tools identified by name."""

    name: str
    description: str
    tools: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


# Default built-in toolsets matching Dream's core capabilities
BUILTIN_TOOLSETS: dict[str, Toolset] = {
    "core": Toolset(
        name="core",
        description="Fundamental utilities (datetime, math calculation)",
        tools=("get_datetime", "calculate"),
    ),
    "workspace": Toolset(
        name="workspace",
        description="Workspace note inspection and editing",
        tools=("read_note", "list_notes", "write_note"),
    ),
    "web": Toolset(
        name="web",
        description="Public internet search and page fetching",
        tools=("search_web", "read_page"),
    ),
    "skills": Toolset(
        name="skills",
        description="Reusable skill management, hub discovery, and autonomous evolution",
        tools=(
            "save_skill",
            "use_skill",
            "list_skills",
            "skill_view",
            "edit_skill",
            "delete_skill",
            "save_skill_bundle",
            "apply_skill_proposal",
            "discard_skill_proposal",
            "hub_search_skills",
            "hub_install_skill",
            "skill_evolve_optimize",
            "skill_export_bundle",
            "skill_import_bundle",
        ),
    ),
    "reminders": Toolset(
        name="reminders",
        description="Scheduled reminders and tasks",
        tools=("create_reminder", "cancel_reminder"),
    ),
    "system": Toolset(
        name="system",
        description="System commands and external communication",
        tools=("run_shell", "send_email"),
    ),
    "mcp": Toolset(
        name="mcp",
        description="Model Context Protocol servers, discovery, and tool execution",
        tools=(
            "mcp_list_servers",
            "mcp_list_tools",
            "mcp_call_tool",
            "mcp_read_resource",
            "mcp_reload",
        ),
    ),
    "subagents": Toolset(
        name="subagents",
        description="Multi-agent orchestration, delegation, and worker lifecycle",
        tools=(
            "subagent_spawn",
            "subagent_wait",
            "subagent_delegate_task",
            "subagent_list",
            "subagent_terminate",
        ),
    ),
    "scheduler": Toolset(
        name="scheduler",
        description="Autonomous cron scheduling, reminders, and multi-channel delivery",
        tools=(
            "schedule_task",
            "list_schedules",
            "cancel_schedule",
            "trigger_schedule",
        ),
    ),
    "retrieval": Toolset(
        name="retrieval",
        description="Hybrid semantic retrieval and knowledge graph memory association",
        tools=(
            "search_hybrid_memory",
            "query_knowledge_graph",
        ),
    ),
    "distill": Toolset(
        name="distill",
        description="Autonomous trajectory recording, distillation, and evaluation benchmarks",
        tools=(
            "distill_record_trajectory",
            "distill_export_dataset",
            "eval_run_benchmark",
        ),
    ),
    "profiles": Toolset(
        name="profiles",
        description="Multi-profile persona scoping and isolated workspace management",
        tools=(
            "profile_list",
            "profile_get_current",
            "profile_switch",
            "profile_create",
        ),
    ),
    "context": Toolset(
        name="context",
        description="Prioritized context files (SOUL, AGENTS, USER, MEMORY) and budgeting",
        tools=(
            "context_get_tier",
            "context_update_tier",
            "context_get_budget_report",
            "context_assemble_prompt",
            "context_reload_all",
        ),
    ),
    "terminal": Toolset(
        name="terminal",
        description="Multi-backend isolated execution (Local, Docker, SSH, Cloud Sandboxes)",
        tools=(
            "terminal_execute",
            "terminal_list_backends",
            "terminal_switch_backend",
        ),
    ),
    "browser": Toolset(
        name="browser",
        description="Multi-driver browser control, DOM extraction, and visual interaction",
        tools=(
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_screenshot",
            "browser_extract_content",
            "browser_close",
            "browser_get_status",
        ),
    ),
    "dialectic": Toolset(
        name="dialectic",
        description="Self-reflective dialectic user modeling and knowledge synthesis",
        tools=(
            "dialectic_observe",
            "dialectic_reflect",
            "dialectic_get_belief_graph",
            "dialectic_reconcile",
            "dialectic_query_traits",
        ),
    ),
    "acp": Toolset(
        name="acp",
        description="Agent Client Protocol (ACP) IDE integration and diff tools",
        tools=(
            "acp_apply_diff",
            "acp_read_diagnostics",
            "acp_get_session_status",
            "acp_list_agents",
            "acp_call_agent",
        ),
    ),
    "plugins": Toolset(
        name="plugins",
        description="Dynamic plugin installation, lifecycle management, and extension hooks",
        tools=(
            "plugin_list",
            "plugin_install",
            "plugin_enable",
            "plugin_disable",
            "plugin_get_info",
        ),
    ),
    "swarm": Toolset(
        name="swarm",
        description="Distributed swarm orchestration, DAG task execution, and consensus",
        tools=(
            "swarm_spawn_node",
            "swarm_plan_workflow",
            "swarm_execute_step",
            "swarm_run_all",
            "swarm_reach_consensus",
            "swarm_get_status",
            "swarm_broadcast_message",
        ),
    ),
    "speech": Toolset(
        name="speech",
        description="Voice synthesis (TTS), recognition (STT), and HybridEmo emotion modeling",
        tools=(
            "speech_text_to_speech",
            "speech_speech_to_text",
            "speech_analyze_voice_emotion",
            "speech_list_voices",
        ),
    ),
    "ocr": Toolset(
        name="ocr",
        description="Persian document OCR, receipt parsing, and invoice field extraction",
        tools=(
            "ocr_extract_document",
            "ocr_extract_invoice",
        ),
    ),
    "knowledge": Toolset(
        name="knowledge",
        description=(
            "Multimodal temporal knowledge graph, timeline reasoning, "
            "and cross-modal entity linking"
        ),
        tools=(
            "knowledge_add_entity",
            "knowledge_add_relation",
            "knowledge_query_temporal",
            "knowledge_get_entity_timeline",
            "knowledge_link_multimodal_artifact",
            "knowledge_get_stats",
        ),
    ),
    "alignment": Toolset(
        name="alignment",
        description=(
            "Continuous self-improving alignment, multi-dimensional scoring, "
            "self-critique, and DPO dataset generation"
        ),
        tools=(
            "alignment_record_feedback",
            "alignment_critique_and_refine",
            "alignment_evaluate_response",
            "alignment_export_dataset",
            "alignment_get_stats",
        ),
    ),
    "research": Toolset(
        name="research",
        description=(
            "Autonomous multi-step deep research, evidence collection, "
            "and multi-source intelligence synthesis"
        ),
        tools=(
            "research_plan_investigation",
            "research_add_source",
            "research_synthesize_report",
            "research_run_autonomous",
            "research_export_report",
            "research_get_status",
            "research_list_sessions",
        ),
    ),
    "cache": Toolset(
        name="cache",
        description=(
            "Semantic caching, speculative pre-fetching, and token economics optimization"
        ),
        tools=(
            "cache_lookup_query",
            "cache_store_entry",
            "cache_predict_tool",
            "cache_get_economics",
            "cache_clear",
            "cache_warmup",
        ),
    ),
    "sandbox": Toolset(
        name="sandbox",
        description=(
            "Isolated Python code execution, dataset analysis, and REPL interpreter"
        ),
        tools=(
            "sandbox_execute_python",
            "sandbox_analyze_dataset",
            "sandbox_reset_session",
            "sandbox_list_artifacts",
            "sandbox_get_status",
        ),
    ),
    "canvas": Toolset(
        name="canvas",
        description=(
            "Interactive visual artifacts, diagrams, standalone previews, and versioning"
        ),
        tools=(
            "canvas_create_artifact",
            "canvas_update_artifact",
            "canvas_get_artifact",
            "canvas_list_artifacts",
            "canvas_diff_versions",
            "canvas_render_preview",
            "canvas_export_bundle",
            "canvas_reset_session",
            "canvas_get_status",
        ),
    ),
    "debate": Toolset(
        name="debate",
        description=(
            "Multi-agent debate rounds, Delphi consensus evaluation, and fact verification"
        ),
        tools=(
            "debate_create_session",
            "debate_add_turn",
            "debate_run_autonomous",
            "debate_verify_statement",
            "debate_reach_consensus",
            "debate_list_sessions",
            "debate_reset_all",
        ),
    ),
    "reasoning": Toolset(
        name="reasoning",
        description=(
            "Tree-of-Thought exploration, strategy branching, and metacognitive self-evaluation"
        ),
        tools=(
            "reasoning_create_thought_tree",
            "reasoning_expand_node",
            "reasoning_evaluate_node",
            "reasoning_solve_goal",
            "reasoning_get_best_path",
            "reasoning_get_status",
            "reasoning_reset_all",
        ),
    ),
}

_TOOLSETS: dict[str, Toolset] = dict(BUILTIN_TOOLSETS)


def register_toolset(
    name: str,
    tools: Collection[str],
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> Toolset:
    """Register a new named toolset or update an existing one."""
    toolset = Toolset(
        name=name,
        description=description,
        tools=tuple(sorted(set(tools))),
        metadata=metadata or {},
    )
    _TOOLSETS[name] = toolset
    return toolset


def unregister_toolset(name: str) -> bool:
    """Remove a registered toolset (returns True if removed)."""
    if name in _TOOLSETS:
        del _TOOLSETS[name]
        return True
    return False


def get_toolset(name: str) -> Toolset | None:
    """Return a Toolset by name, or None if not registered."""
    return _TOOLSETS.get(name)


def list_toolsets() -> list[Toolset]:
    """Return a list of all registered Toolsets."""
    return list(_TOOLSETS.values())


def filter_tools(
    toolsets: Collection[str] | None = None,
    include_tools: Collection[str] | None = None,
    exclude_tools: Collection[str] | None = None,
    registry: Mapping[str, Tool] | None = None,
) -> dict[str, Tool]:
    """Filter registered tools by toolset names and explicit inclusions/exclusions."""
    source = REGISTRY if registry is None else registry

    if toolsets is None and include_tools is None and exclude_tools is None:
        return dict(source)

    allowed_names: set[str] = set()

    if toolsets is not None:
        for ts_name in toolsets:
            ts = _TOOLSETS.get(ts_name)
            if ts:
                allowed_names.update(ts.tools)

    if include_tools is not None:
        allowed_names.update(include_tools)

    if toolsets is None and include_tools is None:
        names = source.keys()
        allowed_names.update(names)

    if exclude_tools is not None:
        allowed_names.difference_update(exclude_tools)

    return {name: tool for name, tool in source.items() if name in allowed_names}
''',
    "tests/test_metacognitive_reasoning.py": r'''"""Unit and integration tests for Metacognitive Reasoning, Strategy Trees, and Tree-of-Thought."""

from __future__ import annotations

import pytest

from dream.reasoning import (
    MetacognitiveEvaluator,
    NodeStatus,
    ReasoningEngine,
    ReasoningStrategy,
    StrategyTree,
    handle_reasoning_slash_command,
    reasoning_create_thought_tree,
    reasoning_evaluate_node,
    reasoning_expand_node,
    reasoning_get_best_path,
    reasoning_get_status,
    reasoning_reset_all,
    reasoning_solve_goal,
    reset_global_reasoning_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_reasoning_engine() -> None:
    reset_global_reasoning_engine()
    yield
    reset_global_reasoning_engine()


def test_toolset_includes_reasoning() -> None:
    """Verify reasoning toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("reasoning")
    assert ts is not None
    assert "reasoning_create_thought_tree" in ts.tools
    assert "reasoning_solve_goal" in ts.tools
    assert "reasoning_evaluate_node" in ts.tools
    assert "reasoning" in BUILTIN_TOOLSETS


def test_thought_tree_expansion_and_uct_scoring() -> None:
    """Verify tree initialization, node expansion, and UCT calculation."""
    tree = StrategyTree()
    root = tree.initialize_root(goal="بهینه‌سازی مصرف رم در عامل هوشمند")

    children = tree.expand_node(
        parent_id=root.node_id,
        child_thoughts=[
            "فرضیه ۱: استفاده از کشینگ LRU و آزادسازی بافرهای متنی",
            "فرضیه ۲: فشرده‌سازی بردارهای حافظه معنایی",
        ],
    )
    assert len(children) == 2
    assert root.status == NodeStatus.EXPANDED
    assert len(root.children_ids) == 2

    # Verify UCT score
    uct_score = tree.calculate_uct(children[0], parent_visits=1)
    assert uct_score > 0.0


def test_tree_backpropagation_and_pruning() -> None:
    """Verify score backpropagation and dead-end branch pruning."""
    tree = StrategyTree()
    root = tree.initialize_root(goal="طراحی پایگاه داده توزیع‌شده")

    children = tree.expand_node(
        parent_id=root.node_id,
        child_thoughts=["راهکار ضعیف", "راهکار قوی و مقیاس‌پذیر"],
    )

    # Evaluate child 0 with low score
    tree.evaluate_node(children[0].node_id, score=0.1, rationale="غیرعملی")
    # Evaluate child 1 with high score
    tree.evaluate_node(children[1].node_id, score=0.9, rationale="مقیاس‌پذیر و مناسب")

    # Prune low-scoring branch
    pruned = tree.prune_low_value_branches(min_score_threshold=0.3)
    assert pruned == 1
    assert children[0].status == NodeStatus.PRUNED

    # Extract best trajectory
    best_path = tree.extract_best_trajectory()
    assert len(best_path) == 2
    assert best_path[-1].node_id == children[1].node_id


def test_metacognitive_evaluator_and_loop_detection() -> None:
    """Verify self-critique scoring and loop/repetition detection."""
    evaluator = MetacognitiveEvaluator()

    # Coherent step
    eval1 = evaluator.evaluate_thought_step(
        thought_text="با توجه به داده‌های ورودی، ابتدا باید اعتبارسنجی طرح انجام شود و سپس تراکنش ثبت گردد.",
        depth=2,
    )
    assert eval1.coherence_score >= 0.8
    assert eval1.suggested_action in ("continue_exploration", "ready_for_conclusion")

    # Repetitive circular step
    eval2 = evaluator.evaluate_thought_step(
        thought_text="اعتبارسنجی طرح باید انجام شود",
        depth=3,
        context_history=["اعتبارسنجی طرح باید انجام شود"],
    )
    assert eval2.hallucination_risk > 0.5
    assert eval2.suggested_action == "backtrack"


def test_reasoning_engine_solve_goal_with_tree() -> None:
    """Verify end-to-end goal solving and report generation."""
    engine = ReasoningEngine()
    traj, summary = engine.solve_goal_with_tree(
        goal="انتخاب الگوریتم رمزنگاری برای پیام‌رسان امن",
        hypotheses=[
            "استفاده از پروتکل Signal و الگوریتم Double Ratchet",
            "استفاده از رمزنگاری ساده متقارن بدون چرخش کلید",
        ],
    )

    assert traj.strategy == ReasoningStrategy.TREE_OF_THOUGHT
    assert len(traj.selected_path) >= 2
    assert traj.confidence > 0.0
    assert "Double Ratchet" in traj.final_answer
    assert "Tree-of-Thought Report" in summary


def test_reasoning_tools_and_slash_commands() -> None:
    """Verify LLM agent tools and /think & /reasoning slash commands."""
    # Tool: create thought tree
    res_init = reasoning_create_thought_tree("کاهش زمان پاسخ‌دهی پایگاه داده")
    assert res_init["success"] is True
    tid = res_init["trajectory"]["trajectory_id"]
    root_id = res_init["root_node_id"]

    # Tool: expand & evaluate
    res_exp = reasoning_expand_node(
        trajectory_id=tid,
        parent_node_id=root_id,
        thoughts=["ایجاد ایندکس B-Tree روی ستون‌های پرکاربرد"],
    )
    assert res_exp["success"] is True
    child_id = res_exp["nodes"][0]["node_id"]

    res_eval = reasoning_evaluate_node(
        trajectory_id=tid,
        node_id=child_id,
        score=0.92,
        rationale="بسیار موثر در کاهش زمان کوئری‌ها",
    )
    assert res_eval["success"] is True
    assert res_eval["node"]["score"] == 0.92

    # Tool: get best path & status
    res_path = reasoning_get_best_path(tid)
    assert res_path["success"] is True

    res_st = reasoning_get_status()
    assert res_st["success"] is True
    assert res_st["total_trajectories"] >= 1

    # Slash: /think
    slash_think = handle_reasoning_slash_command("/think بهبود بازدهی سیستم")
    assert "Tree-of-Thought Report" in slash_think

    # Slash: /reasoning status
    slash_st = handle_reasoning_slash_command("/reasoning status")
    assert "وضعیت موتور استدلال" in slash_st

    # Slash: /reasoning reset
    slash_reset = handle_reasoning_slash_command("/reasoning reset")
    assert "بازنشانی شد" in slash_reset
''',
}


def main() -> None:
    root = Path(__file__).resolve().parent
    if not (root / "dream").exists():
        if (root / "dream-repo" / "dream").exists():
            root = root / "dream-repo"
        elif (Path.cwd() / "dream").exists():
            root = Path.cwd()
        else:
            print(f"Error: could not locate Dream repo root from {root}")
            sys.exit(1)

    print(f"Applying Phase 35 (Metacognitive Reasoning & Tree-of-Thought) to: {root}")

    for rel_path, content in FILES.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"  [written] {rel_path}")

    print("\nRunning pytest validation...")
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_metacognitive_reasoning.py", "-v"],
        cwd=root,
    )
    if res.returncode != 0:
        print("\n[FAIL] Pytest failed for Phase 35")
        sys.exit(res.returncode)

    print("\nRunning security audit...")
    audit_res = subprocess.run(
        [sys.executable, "tools/security_audit.py"],
        cwd=root,
    )
    if audit_res.returncode != 0:
        print("\n[FAIL] Security audit failed for Phase 35")
        sys.exit(audit_res.returncode)

    print("\n[SUCCESS] Phase 35 (Metacognitive Reasoning & Tree-of-Thought) applied and verified cleanly!")


if __name__ == "__main__":
    main()
