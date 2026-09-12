"""Autonomous Continuous Learning, Heuristic Distillation & Self-Evolution Subsystem."""

from __future__ import annotations

from dream.evolution.arena import StrategyEvolutionArena
from dream.evolution.distiller import HeuristicDistiller
from dream.evolution.engine import EvolutionEngine
from dream.evolution.slash import handle_evolution_slash_command
from dream.evolution.tools import (
    evolution_distill_heuristics,
    evolution_export_policy,
    evolution_get_leaderboard,
    evolution_get_status,
    evolution_reset,
    evolution_run_tournament,
    get_evolution_tools,
    get_global_evolution_engine,
    reset_global_evolution_engine,
)
from dream.evolution.types import (
    EvolutionMutationType,
    EvolutionReport,
    ExperiencePlayback,
    StrategyGene,
)

__all__ = [
    "EvolutionEngine",
    "EvolutionMutationType",
    "EvolutionReport",
    "ExperiencePlayback",
    "HeuristicDistiller",
    "StrategyEvolutionArena",
    "StrategyGene",
    "evolution_distill_heuristics",
    "evolution_export_policy",
    "evolution_get_leaderboard",
    "evolution_get_status",
    "evolution_reset",
    "evolution_run_tournament",
    "get_evolution_tools",
    "get_global_evolution_engine",
    "handle_evolution_slash_command",
    "reset_global_evolution_engine",
]
