"""Dynamic Strategy Tree, Tree-of-Thought search, and Monte Carlo scoring."""

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
