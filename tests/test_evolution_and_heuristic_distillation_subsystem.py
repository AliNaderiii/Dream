"""Unit and integration tests for Self-Evolution & Heuristic Distillation Subsystem."""

from __future__ import annotations

import pytest

from dream.evolution import (
    EvolutionEngine,
    EvolutionMutationType,
    ExperiencePlayback,
    HeuristicDistiller,
    StrategyEvolutionArena,
    evolution_distill_heuristics,
    evolution_export_policy,
    evolution_get_leaderboard,
    evolution_get_status,
    evolution_run_tournament,
    get_evolution_tools,
    handle_evolution_slash_command,
    reset_global_evolution_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_evolution_engine() -> None:
    reset_global_evolution_engine()
    yield
    reset_global_evolution_engine()


def test_toolset_includes_evolution() -> None:
    """Verify evolution toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("evolution")
    assert ts is not None
    assert "evolution_distill_heuristics" in ts.tools
    assert "evolution_run_tournament" in ts.tools
    assert "evolution" in BUILTIN_TOOLSETS


def test_heuristic_distiller() -> None:
    """Verify procedural rule extraction from execution playbacks."""
    distiller = HeuristicDistiller()

    pb_chain = ExperiencePlayback(
        playback_id="p1",
        user_prompt="محاسبه دقیق سود",
        tool_sequence=["get_datetime", "calculate"],
        final_response="سود محاسبه شد.",
        success=True,
        reward_score=0.92,
    )
    rule = distiller.distill_from_playback(pb_chain)
    assert "قانون زنجیره ابزار" in rule
    assert "get_datetime" in rule
    assert "calculate" in rule

    # Batch distill
    rules = distiller.batch_distill([pb_chain])
    assert len(rules) == 1


def test_strategy_evolution_arena() -> None:
    """Verify Elo matchmaking, rating updates, and genetic mutation."""
    arena = StrategyEvolutionArena()
    board = arena.get_leaderboard()
    assert len(board) >= 3

    g_a = board[0]
    g_b = board[1]
    initial_elo_a = g_a.elo_rating
    initial_elo_b = g_b.elo_rating

    new_elo_a, new_elo_b = arena.run_pairwise_match(g_a.gene_id, g_b.gene_id)
    assert g_a.matches_played == 1
    assert g_b.matches_played == 1
    assert new_elo_a != initial_elo_a or new_elo_b != initial_elo_b

    # Mutation
    mutated = arena.mutate_gene(
        parent_id=g_a.gene_id,
        mutation_type=EvolutionMutationType.PROMPT_REFINEMENT,
    )
    assert mutated.generation == g_a.generation + 1
    assert len(arena.get_leaderboard()) == len(board) + 1


def test_evolution_engine_tournament_and_policy() -> None:
    """Verify tournament orchestrator, mutation flow, and policy markdown."""
    engine = EvolutionEngine()
    rep = engine.run_tournament(rounds=1)
    assert rep.total_matches >= 1
    assert rep.top_strategy is not None
    assert "تورنمنت تکاملی پایان یافت" in rep.summary_fa

    # Check Markdown
    md_policy = engine.format_policy_markdown()
    assert "Evolutionary Policy" in md_policy
    assert "لیدربورد استراتژی‌های برتر" in md_policy


def test_evolution_tools_and_slash_commands() -> None:
    """Verify LLM tools and /evolution slash command handlers."""
    tools = get_evolution_tools()
    assert len(tools) >= 4

    # Tool: distill
    res_distill = evolution_distill_heuristics()
    assert res_distill["success"] is True
    assert res_distill["total_rules"] >= 1

    # Tool: tournament
    res_tour = evolution_run_tournament(rounds=1)
    assert res_tour["success"] is True
    assert "report" in res_tour

    # Tool: leaderboard
    res_board = evolution_get_leaderboard()
    assert res_board["success"] is True
    assert res_board["total_strategies"] >= 3

    # Tool: export policy
    res_pol = evolution_export_policy()
    assert res_pol["success"] is True
    assert "Evolutionary Policy" in res_pol["policy_markdown"]

    # Tool: status
    res_st = evolution_get_status()
    assert res_st["success"] is True
    assert res_st["total_playbacks"] >= 2

    # Slash: /evolution
    slash_help = handle_evolution_slash_command("/evolution")
    assert "راهنمای دستورات تکامل" in slash_help

    # Slash: /evolution distill
    slash_d = handle_evolution_slash_command("/evolution distill")
    assert "قانون" in slash_d or "هیوریستیک" in slash_d

    # Slash: /evolution arena
    slash_a = handle_evolution_slash_command("/evolution arena 1")
    assert "پایان تورنمنت تکاملی" in slash_a

    # Slash: /evolution leaderboard
    slash_l = handle_evolution_slash_command("/evolution leaderboard")
    assert "لیدربورد استراتژی‌های عامل" in slash_l

    # Slash: /evolution policy
    slash_p = handle_evolution_slash_command("/evolution policy")
    assert "Evolutionary Policy" in slash_p

    # Slash: /evolution status
    slash_s = handle_evolution_slash_command("/evolution status")
    assert "وضعیت سیستم تکامل خودکار" in slash_s

    # Slash: /evolution reset
    slash_reset = handle_evolution_slash_command("/evolution reset")
    assert "بازنشانی شد" in slash_reset
