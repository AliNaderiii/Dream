"""Reasoning Engine Coordinator for Tree-of-Thought search and metacognitive exploration."""

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
