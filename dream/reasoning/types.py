"""Domain models and data structures for Metacognitive Reasoning and Strategy Trees."""

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
