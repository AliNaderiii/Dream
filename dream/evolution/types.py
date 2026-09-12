"""Data types and models for Autonomous Self-Evolution & Policy Distillation Subsystem."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvolutionMutationType(str, Enum):
    """Types of adaptive mutations applied to agent strategies."""

    PROMPT_REFINEMENT = "prompt_refinement"
    TOOL_CHAIN_OPTIMIZATION = "tool_chain_optimization"
    HEURISTIC_RULE_ADDITION = "heuristic_rule_addition"
    ERROR_RECOVERY_TACTIC = "error_recovery_tactic"


@dataclass(slots=True)
class StrategyGene:
    """Individual agent strategy genome in evolutionary arena."""

    gene_id: str
    name: str
    description_fa: str
    prompt_template: str
    heuristics: list[str] = field(default_factory=list)
    preferred_tools: list[str] = field(default_factory=list)
    fitness_score: float = 0.50
    elo_rating: float = 1200.0
    generation: int = 1
    wins: int = 0
    losses: int = 0
    matches_played: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize strategy gene to dictionary."""
        return {
            "gene_id": self.gene_id,
            "name": self.name,
            "description_fa": self.description_fa,
            "prompt_template": self.prompt_template,
            "heuristics": self.heuristics,
            "preferred_tools": self.preferred_tools,
            "fitness_score": round(self.fitness_score, 3),
            "elo_rating": round(self.elo_rating, 1),
            "generation": self.generation,
            "wins": self.wins,
            "losses": self.losses,
            "matches_played": self.matches_played,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class ExperiencePlayback:
    """Recorded trajectory used for policy distillation and counterfactual replay."""

    playback_id: str
    user_prompt: str
    tool_sequence: list[str]
    final_response: str
    success: bool
    reward_score: float
    distilled_heuristic: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize playback record to dictionary."""
        return {
            "playback_id": self.playback_id,
            "user_prompt": self.user_prompt,
            "tool_sequence": self.tool_sequence,
            "final_response": self.final_response,
            "success": self.success,
            "reward_score": round(self.reward_score, 3),
            "distilled_heuristic": self.distilled_heuristic,
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class EvolutionReport:
    """Telemetry report of evolutionary tournament and policy refinement."""

    run_id: str
    generation: int
    total_matches: int
    top_strategy: StrategyGene
    leaderboard: list[StrategyGene]
    mutations_applied: int
    distilled_rules: list[str]
    summary_fa: str
    duration_ms: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize report to dictionary."""
        return {
            "run_id": self.run_id,
            "generation": self.generation,
            "total_matches": self.total_matches,
            "top_strategy": self.top_strategy.to_dict(),
            "leaderboard": [g.to_dict() for g in self.leaderboard],
            "mutations_applied": self.mutations_applied,
            "distilled_rules": self.distilled_rules,
            "summary_fa": self.summary_fa,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": self.timestamp,
        }
