"""Comprehensive tests for Hierarchical Episodic Memory & Temporal KG Engine."""

from __future__ import annotations

import pytest

from dream.memory.hierarchical_episodic import (
    HierarchicalEpisodicEngine,
    get_episodic_engine,
    reset_global_episodic_engine,
)


@pytest.fixture(autouse=True)
def _clean_engine():
    """Reset episodic engine before and after each test."""
    reset_global_episodic_engine()
    yield
    reset_global_episodic_engine()


def test_working_memory_buffer_tier_0():
    """Verify Tier 0 working memory records turns and bounds history."""
    engine = HierarchicalEpisodicEngine()
    turn1 = engine.record_working_turn(
        session_id="session_arch",
        speaker="user",
        text="ما قصد داریم سیستم حافظه دریم را به سطح سازمانی ارتقا دهیم.",
        sentiment=0.8,
    )
    assert turn1.speaker == "user"
    assert turn1.sentiment == 0.8
    assert turn1.tokens > 0

    # Record 60 turns to verify buffer cap
    for i in range(60):
        engine.record_working_turn(
            session_id="session_arch",
            speaker="assistant" if i % 2 == 0 else "user",
            text=f"پیام شماره {i} برای اعتبارسنجی بافر",
        )

    stats = engine.get_hierarchy_stats()
    assert stats["tier_0_working_turns"] == 50


def test_session_compression_into_tier_1_episode():
    """Verify session compaction into a structured EpisodeRecord."""
    engine = HierarchicalEpisodicEngine()
    engine.record_working_turn("sess_01", "user", "بررسی پایپ‌لاین گراف دانش")
    engine.record_working_turn("sess_01", "assistant", "پایپ‌لاین با موفقیت بارگذاری شد.")

    ep = engine.compress_session(session_id="sess_01", domain="knowledge_graph")
    assert ep.session_id == "sess_01"
    assert "knowledge_graph" in ep.title_fa or "knowledge_graph" in ep.title_en
    assert ep.importance_score >= 3
    assert len(ep.milestones) >= 2
    assert ep.jalali_date != ""

    # Check stats
    stats = engine.get_hierarchy_stats()
    assert stats["tier_1_episodes_count"] == 1


def test_temporal_kg_entity_linking_tier_2():
    """Verify entity fact linking into MultimodalTemporalGraph."""
    engine = HierarchicalEpisodicEngine()
    ep = engine.compress_session(session_id="sess_kg", domain="ai_reasoning")

    fact = engine.link_entity_fact(
        episode_id=ep.episode_id,
        entity_name="دریم نسخه ۳.۲",
        entity_type="project",
        relation_type="references",
        target_entity="معماری شناختی",
    )
    assert fact.entity_name == "دریم نسخه ۳.۲"
    assert fact.target_name == "معماری شناختی"

    stats = engine.get_hierarchy_stats()
    assert stats["tier_2_temporal_facts_count"] == 1
    assert stats["total_knowledge_graph_nodes"] >= 2
    assert stats["total_knowledge_graph_edges"] >= 1


def test_jalali_temporal_timeline_queries():
    """Verify temporal horizon querying with Jalali filters."""
    engine = HierarchicalEpisodicEngine()
    engine.compress_session("s1", domain="agent_security")
    engine.compress_session("s2", domain="voice_duplex")

    # Query all
    all_episodes = engine.query_timeline()
    assert len(all_episodes) == 2

    # Query with keyword match
    sec_episodes = engine.query_timeline(query="agent_security")
    assert len(sec_episodes) == 1
    assert sec_episodes[0].session_id == "s1"


def test_tier_3_recursive_consolidation():
    """Verify persona distillation and logarithmic competency growth."""
    engine = HierarchicalEpisodicEngine()
    for i in range(5):
        engine.compress_session(f"sess_{i}", domain="autonomous_ai")

    persona = engine.consolidate(min_episodes=1)
    assert persona.total_episodes_synthesized == 5
    assert "autonomous_ai" in persona.primary_domains
    assert persona.skill_masteries.get("autonomous_ai", 0.0) > 0.7


def test_engine_reset_and_singleton():
    """Verify reset lifecycle and global singleton."""
    engine = get_episodic_engine()
    engine.record_working_turn("s_temp", "user", "تست موقت")
    assert engine.get_hierarchy_stats()["tier_0_working_turns"] == 1

    engine.reset()
    assert engine.get_hierarchy_stats()["tier_0_working_turns"] == 0
