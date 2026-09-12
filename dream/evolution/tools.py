"""LLM agent tools and singleton managers for Self-Evolution Subsystem."""

from __future__ import annotations

import logging
from typing import Any

from dream.evolution.engine import EvolutionEngine

logger = logging.getLogger(__name__)

_GLOBAL_EVOLUTION_ENGINE: EvolutionEngine | None = None


def get_global_evolution_engine() -> EvolutionEngine:
    """Retrieve or initialize singleton EvolutionEngine."""
    global _GLOBAL_EVOLUTION_ENGINE
    if _GLOBAL_EVOLUTION_ENGINE is None:
        _GLOBAL_EVOLUTION_ENGINE = EvolutionEngine()
    return _GLOBAL_EVOLUTION_ENGINE


def reset_global_evolution_engine() -> None:
    """Reset global EvolutionEngine instance."""
    global _GLOBAL_EVOLUTION_ENGINE
    if _GLOBAL_EVOLUTION_ENGINE is not None:
        _GLOBAL_EVOLUTION_ENGINE.reset()
    _GLOBAL_EVOLUTION_ENGINE = None


def evolution_distill_heuristics() -> dict[str, Any]:
    """Distill procedural heuristics and best practices from recorded experiences."""
    engine = get_global_evolution_engine()
    rules = engine.distill_all_heuristics()
    return {
        "success": True,
        "distilled_rules": rules,
        "total_rules": len(rules),
        "summary_fa": f"تعداد {len(rules)} قانون و هیوریستیک کاربردی استخراج شد.",
    }


def evolution_run_tournament(rounds: int = 3) -> dict[str, Any]:
    """Execute evolutionary tournament across agent strategies and update Elo ratings."""
    engine = get_global_evolution_engine()
    try:
        rep = engine.run_tournament(rounds=rounds)
        return {
            "success": True,
            "report": rep.to_dict(),
            "summary_fa": rep.summary_fa,
        }
    except Exception as exc:
        logger.error(f"Evolution tournament error: {exc}")
        return {"success": False, "error": str(exc)}


def evolution_get_leaderboard() -> dict[str, Any]:
    """Retrieve current Elo leaderboard of strategy genomes."""
    engine = get_global_evolution_engine()
    board = engine.arena.get_leaderboard()
    return {
        "success": True,
        "leaderboard": [g.to_dict() for g in board],
        "total_strategies": len(board),
    }


def evolution_export_policy() -> dict[str, Any]:
    """Export complete evolutionary policy and distilled heuristics as Markdown."""
    engine = get_global_evolution_engine()
    policy_md = engine.format_policy_markdown()
    return {"success": True, "policy_markdown": policy_md}


def evolution_get_status() -> dict[str, Any]:
    """Retrieve operational telemetry and metrics from EvolutionEngine."""
    engine = get_global_evolution_engine()
    return {"success": True, **engine.get_status()}


def evolution_reset() -> dict[str, Any]:
    """Reset evolution history and return to factory state."""
    reset_global_evolution_engine()
    return {"success": True, "message_fa": "موتور تکامل خودکار بازنشانی شد."}


def get_evolution_tools() -> list[dict[str, Any]]:
    """Return tool manifests for LLM registration."""
    return [
        {
            "name": "evolution_distill_heuristics",
            "description": "Distill operational heuristics from successful agent traces.",
            "parameters": {"type": "object", "properties": {}},
            "handler": evolution_distill_heuristics,
        },
        {
            "name": "evolution_run_tournament",
            "description": "Run evolutionary tournament updating strategy Elo ratings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "rounds": {"type": "integer", "default": 3},
                },
            },
            "handler": evolution_run_tournament,
        },
        {
            "name": "evolution_get_leaderboard",
            "description": "Get current Elo leaderboard of agent strategies.",
            "parameters": {"type": "object", "properties": {}},
            "handler": evolution_get_leaderboard,
        },
        {
            "name": "evolution_export_policy",
            "description": "Export the distilled operational policy in Markdown.",
            "parameters": {"type": "object", "properties": {}},
            "handler": evolution_export_policy,
        },
    ]
