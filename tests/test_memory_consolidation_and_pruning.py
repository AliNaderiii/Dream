"""Unit and integration tests for Memory Consolidation, Entropy Pruning & Distillation."""

from __future__ import annotations

import pytest

from dream.consolidation import (
    ConsolidationEngine,
    EntropyPruner,
    EpistemicDistiller,
    MemoryItem,
    MemoryNodeType,
    consolidation_add_memory,
    consolidation_distill_session,
    consolidation_export_report,
    consolidation_get_stats,
    consolidation_run_cycle,
    get_consolidation_tools,
    handle_consolidation_slash_command,
    reset_global_consolidation_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_consolidation_engine() -> None:
    reset_global_consolidation_engine()
    yield
    reset_global_consolidation_engine()


def test_toolset_includes_consolidation() -> None:
    """Verify consolidation toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("consolidation")
    assert ts is not None
    assert "consolidation_run_cycle" in ts.tools
    assert "consolidation_add_memory" in ts.tools
    assert "consolidation_distill_session" in ts.tools
    assert "consolidation" in BUILTIN_TOOLSETS


def test_ebbinghaus_decay_calculation() -> None:
    """Verify exponential retrievability decay over simulated time intervals."""
    item = MemoryItem(
        memory_id="test-1",
        node_type=MemoryNodeType.EPISODIC,
        content="Temporary log entry",
        importance=0.2,
        access_count=1,
        last_accessed_at=1000.0,
    )

    # Initial decay at t = 1000.0 is 1.0
    decay_0 = item.calculate_decay(current_time=1000.0, decay_constant=100.0)
    assert decay_0 == 1.0

    # Decayed after elapsed time
    decay_future = item.calculate_decay(current_time=1500.0, decay_constant=100.0)
    assert 0.0 < decay_future < 1.0


def test_entropy_pruning_and_protection() -> None:
    """Verify low decay items are pruned while core beliefs and high importance are protected."""
    pruner = EntropyPruner(retention_threshold=0.30)

    # Core belief with low decay -> Retained
    core = MemoryItem(
        memory_id="core-1",
        node_type=MemoryNodeType.CORE_BELIEF,
        content="Dream always protects user privacy.",
        importance=0.9,
        decay_score=0.1,
    )

    # Ephemeral scratchpad with low decay -> Pruned
    scratch = MemoryItem(
        memory_id="scratch-1",
        node_type=MemoryNodeType.EPHEMERAL_SCRATCHPAD,
        content="Thought: search parameter parsed.",
        importance=0.1,
        decay_score=0.2,
    )

    # Normal decayed item -> Pruned
    decayed = MemoryItem(
        memory_id="decay-1",
        node_type=MemoryNodeType.EPISODIC,
        content="User said hello at morning.",
        importance=0.3,
        decay_score=0.15,
    )

    retained, pruned = pruner.prune_low_entropy_nodes([core, scratch, decayed])
    assert core in retained
    assert scratch in pruned
    assert decayed in pruned


def test_deduplication_and_contradiction_resolution() -> None:
    """Verify merging of near-duplicates and resolution of conflicting facts."""
    pruner = EntropyPruner()
    distiller = EpistemicDistiller()

    # 1. Deduplication
    mem1 = MemoryItem(
        "m1",
        MemoryNodeType.SEMANTIC_FACT,
        "User prefers dark mode in VS Code",
        importance=0.7,
    )
    mem2 = MemoryItem(
        "m2",
        MemoryNodeType.SEMANTIC_FACT,
        "User prefers dark mode in VS Code editor",
        importance=0.8,
    )
    deduped, count = pruner.deduplicate([mem1, mem2], similarity_threshold=0.6)
    assert len(deduped) == 1
    assert count == 1
    assert deduped[0].importance == 0.8

    # 2. Contradiction Resolution
    old_fact = MemoryItem(
        "f_old",
        MemoryNodeType.USER_TRAIT,
        "User prefers Python 3.10",
        last_accessed_at=100.0,
    )
    new_fact = MemoryItem(
        "f_new",
        MemoryNodeType.USER_TRAIT,
        "User prefers Python 3.14 exclusively",
        last_accessed_at=200.0,
    )
    reconciled, resolved = distiller.reconcile_contradictions([old_fact, new_fact])
    assert len(reconciled) == 1
    assert resolved == 1
    assert reconciled[0].content == "User prefers Python 3.14 exclusively"


def test_consolidation_engine_full_cycle() -> None:
    """Verify autonomous sleep cycle compresses memory repository and computes health score."""
    engine = ConsolidationEngine()

    engine.add_memory(
        "User likes green tea",
        node_type=MemoryNodeType.USER_TRAIT,
        importance=0.8,
    )
    engine.add_memory(
        "System booted successfully",
        node_type=MemoryNodeType.EPHEMERAL_SCRATCHPAD,
        importance=0.1,
    )
    engine.add_memory(
        "Dream adheres strictly to ethics",
        node_type=MemoryNodeType.CORE_BELIEF,
        importance=1.0,
    )

    # Run consolidation cycle
    report = engine.run_consolidation_cycle(decay_constant=10.0, dry_run=False)
    assert report.initial_memory_count == 3
    assert report.final_memory_count >= 1
    assert report.compression_ratio <= 1.0

    stats = engine.get_health_stats()
    assert stats.total_cycles_executed == 1
    assert stats.memory_health_score > 0.0


def test_synthetic_dream_simulation() -> None:
    """Verify synthetic dream generates reflective scenarios for core memories."""
    distiller = EpistemicDistiller()
    core = MemoryItem(
        "c1",
        MemoryNodeType.CORE_BELIEF,
        "Ensure all calculations are mathematically verified.",
    )
    sims = distiller.run_synthetic_dream_simulation([core], num_scenarios=1)

    assert len(sims) == 1
    assert "Ensure all calculations" in sims[0]["focus_memory"]
    assert "تثبیت خودکار" in sims[0]["synthesized_reinforcement_fa"]


def test_consolidation_tools_and_slash_commands() -> None:
    """Verify LLM agent tools and /consolidate, /distill_memory slash commands."""
    tools = get_consolidation_tools()
    assert len(tools) >= 5

    # Tool: add memory
    res_add = consolidation_add_memory(
        content="کاربر به مباحث هوش مصنوعی علاقه‌مند است.",
        node_type="user_trait",
    )
    assert res_add["success"] is True

    # Tool: distill session
    transcript = """
    1. کاربر گفت که در اصفهان زندگی می‌کند و به معماری سنتی علاقه‌مند است.
    2. دستیار پاسخ داد که اصفهان مهد هنر و معماری است.
    """
    res_distill = consolidation_distill_session(transcript)
    assert res_distill["success"] is True
    assert res_distill["distilled_facts_count"] >= 1

    # Tool: run cycle
    res_cycle = consolidation_run_cycle(dry_run=False)
    assert res_cycle["success"] is True
    assert res_cycle["report"]["initial_memory_count"] >= 1

    # Tool: stats
    res_stats = consolidation_get_stats()
    assert res_stats["success"] is True

    # Tool: export report
    res_rep = consolidation_export_report()
    assert res_rep["success"] is True
    assert "Memory Consolidation & Health" in res_rep["markdown_report"]

    # Slash: /consolidate
    slash_c = handle_consolidation_slash_command("/consolidate dry")
    assert "نتیجه چرخه تثبیت حافظه" in slash_c

    # Slash: /distill_memory
    slash_d = handle_consolidation_slash_command(
        "/distill_memory کاربر ترجیح می‌دهد خروجی‌ها کوتاه باشند."
    )
    assert "تقطیر با موفقیت انجام شد" in slash_d

    # Slash: /memory_health
    slash_h = handle_consolidation_slash_command("/memory_health")
    assert "Memory Consolidation & Health" in slash_h

    # Slash: /memory_health reset
    slash_reset = handle_consolidation_slash_command("/memory_health reset")
    assert "بازنشانی شد" in slash_reset
