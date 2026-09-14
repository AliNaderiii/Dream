"""Reasoning Engine Coordinator for Tree-of-Thought search and metacognitive exploration."""

from __future__ import annotations

import time
import uuid
from typing import Any

from dream.reasoning.evaluator import MetacognitiveEvaluator
from dream.reasoning.tree import StrategyTree
from dream.reasoning.types import (
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

    def step_critique(
        self,
        trajectory_id: str,
        node_id: str,
    ) -> dict[str, Any]:
        """Perform metacognitive self-critique on a specific node."""
        traj = self._trajectories.get(trajectory_id)
        if not traj or node_id not in traj.nodes:
            raise KeyError(f"Node '{node_id}' in trajectory '{trajectory_id}' not found.")

        node = traj.nodes[node_id]
        history = [n.thought_content for n in traj.nodes.values() if n.node_id != node_id]

        critique = self.evaluator.evaluate_thought_step(
            thought_text=node.thought_content,
            depth=node.depth,
            context_history=history,
        )

        score = (critique.coherence_score + critique.depth_score) / 2.0
        self.evaluate_node(
            trajectory_id=trajectory_id,
            node_id=node_id,
            score=score,
            rationale=critique.critique_notes,
        )

        return {
            "node_id": node_id,
            "score": round(score, 3),
            "critique": critique.to_dict(),
        }

    def mcts_search_step(
        self,
        trajectory_id: str,
        candidate_thoughts: list[str] | None = None,
    ) -> dict[str, Any]:
        """Perform one iteration of MCTS: Selection, Expansion, Simulation, Backprop."""
        tree = self._trees.get(trajectory_id)
        traj = self._trajectories.get(trajectory_id)
        if not tree or not traj or not traj.root_node_id:
            raise KeyError(f"Trajectory '{trajectory_id}' not found or uninitialized.")

        # 1. Selection: follow UCT from root to frontier
        curr = tree.nodes.get(traj.root_node_id)
        selected_parent = curr
        while curr and curr.children_ids:
            best_child = tree.select_best_child(curr.node_id)
            if not best_child:
                break
            selected_parent = best_child
            curr = best_child

        if not selected_parent:
            selected_parent = tree.nodes[traj.root_node_id]

        # 2. Expansion: generate branch candidates if unexpanded or supplied
        if not candidate_thoughts:
            candidate_thoughts = [
                f"تحلیل ابعاد راهبردی مرحله {selected_parent.depth + 1}: ارزیابی متغیرها و ریسک‌ها",
                f"اجرای آزمون تجربی مرحله {selected_parent.depth + 1}: مقایسه گزینه‌های بهینه‌سازی",
            ]

        expanded = tree.expand_node(selected_parent.node_id, candidate_thoughts)
        for n in expanded:
            traj.nodes[n.node_id] = n

        # 3. Simulation & Evaluation
        evaluated_nodes = []
        for child in expanded:
            critique = self.evaluator.evaluate_thought_step(
                thought_text=child.thought_content,
                depth=child.depth,
            )
            score = (critique.coherence_score + critique.depth_score) / 2.0
            eval_node = tree.evaluate_node(
                node_id=child.node_id,
                score=score,
                rationale=critique.critique_notes,
            )
            traj.nodes[child.node_id] = eval_node
            evaluated_nodes.append(eval_node.to_dict())

        traj.updated_at = time.time()
        return {
            "trajectory_id": trajectory_id,
            "expanded_parent_id": selected_parent.node_id,
            "new_nodes_count": len(expanded),
            "evaluated_nodes": evaluated_nodes,
        }

    def backtrack_and_prune(
        self,
        trajectory_id: str,
        min_threshold: float = 0.35,
    ) -> dict[str, Any]:
        """Prune unviable branches and return current viable frontier."""
        tree = self._trees.get(trajectory_id)
        traj = self._trajectories.get(trajectory_id)
        if not tree or not traj:
            raise KeyError(f"Trajectory '{trajectory_id}' not found.")

        pruned = tree.prune_low_value_branches(min_score_threshold=min_threshold)
        for node_id, node in tree.nodes.items():
            if node.status == NodeStatus.PRUNED:
                traj.nodes[node_id].status = NodeStatus.PRUNED

        traj.updated_at = time.time()
        best_path = tree.extract_best_trajectory()
        traj.selected_path = [n.node_id for n in best_path]

        active_nodes = (
            len([n for n in traj.nodes.values() if n.status != NodeStatus.PRUNED])
            if traj
            else 0
        )
        return {
            "trajectory_id": trajectory_id,
            "pruned_nodes_count": pruned,
            "active_nodes_count": active_nodes,
            "best_path": traj.selected_path,
        }

    def synthesize_solution(self, trajectory_id: str) -> dict[str, Any]:
        """Synthesize final structured solution from winning trajectory path."""
        tree = self._trees.get(trajectory_id)
        traj = self._trajectories.get(trajectory_id)
        if not tree or not traj:
            raise KeyError(f"Trajectory '{trajectory_id}' not found.")

        best_nodes = tree.extract_best_trajectory()
        traj.selected_path = [n.node_id for n in best_nodes]

        avg_score = (
            sum(n.score for n in best_nodes) / max(1, len(best_nodes))
            if best_nodes
            else 0.5
        )
        traj.confidence = round(avg_score, 3)

        steps_summary = []
        for idx, n in enumerate(best_nodes):
            steps_summary.append(f"{idx + 1}. {n.thought_content} (امتیاز: {n.score:.2f})")

        traj.final_answer = "\n".join(steps_summary)
        traj.updated_at = time.time()

        return {
            "trajectory_id": trajectory_id,
            "goal": traj.goal,
            "confidence": traj.confidence,
            "selected_path": traj.selected_path,
            "final_answer": traj.final_answer,
            "steps": [n.to_dict() for n in best_nodes],
        }

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
        for _i, child in enumerate(children):
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

        path_str = " -> ".join(traj.selected_path)
        summary = (
            "🧠 درخت استدلال و حل مسئله (Tree-of-Thought Report):\n"
            f"- هدف: {goal}\n"
            f"- تعداد گره‌های بررسی‌شده: {len(traj.nodes)}\n"
            f"- مسیر برگزیده: {path_str}\n"
            f"- پاسخ بهینه: {traj.final_answer}\n"
            f"- ضریب اطمینان: {traj.confidence:.2f}"
        )

        return traj, summary

    def get_trajectory(self, trajectory_id: str | None = None) -> ReasoningTrajectory | None:
        """Get active or specific trajectory."""
        tid = trajectory_id or self._active_trajectory_id
        if not tid:
            return None
        return self._trajectories.get(tid)

    def get_best_trajectory_nodes(self, trajectory_id: str) -> list[ThoughtNode]:
        """Get nodes forming the best path for a trajectory."""
        tree = self._trees.get(trajectory_id)
        if not tree:
            return []
        return tree.extract_best_trajectory()

    def get_tree_stats(self, trajectory_id: str | None = None) -> dict[str, Any]:
        """Get comprehensive metrics on reasoning trees."""
        tid = trajectory_id or self._active_trajectory_id
        traj = self._trajectories.get(tid) if tid else None

        active_nodes = (
            len([n for n in traj.nodes.values() if n.status != NodeStatus.PRUNED])
            if traj
            else 0
        )
        pruned_nodes = (
            len([n for n in traj.nodes.values() if n.status == NodeStatus.PRUNED])
            if traj
            else 0
        )
        max_depth = max([n.depth for n in traj.nodes.values()], default=0) if traj else 0

        return {
            "status": "healthy",
            "total_trajectories": len(self._trajectories),
            "active_trajectory_id": self._active_trajectory_id,
            "active_nodes_count": active_nodes,
            "pruned_nodes_count": pruned_nodes,
            "max_tree_depth": max_depth,
            "confidence": traj.confidence if traj else 0.0,
            "trajectory": traj.to_tree_dict() if traj else None,
        }

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
