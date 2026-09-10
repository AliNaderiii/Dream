"""Tests for Tier-4 Context Files (SOUL/USER/MEMORY/AGENTS) and User Modeling."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dream.memory import (
    ContextCapacityError,
    ContextFileManager,
    DialecticalUserTracker,
)


def test_context_file_manager_auto_creates_four_files() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = ContextFileManager(root_dir=tmpdir, auto_create=True)
        report = manager.load_all()

        assert len(report.files) == 4
        assert "soul" in report.files
        assert "user" in report.files
        assert "memory" in report.files
        assert "agents" in report.files

        # Verify disk files exist
        assert (Path(tmpdir) / "SOUL.MD").exists() or (Path(tmpdir) / "SOUL.md").exists()
        assert (Path(tmpdir) / "USER.MD").exists() or (Path(tmpdir) / "USER.md").exists()
        assert (Path(tmpdir) / "MEMORY.MD").exists() or (Path(tmpdir) / "MEMORY.md").exists()
        assert (Path(tmpdir) / "AGENTS.MD").exists() or (Path(tmpdir) / "AGENTS.md").exists()


def test_capacity_headers_and_prompt_rendering() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = ContextFileManager(root_dir=tmpdir, auto_create=True)
        prompt_block = manager.render_prompt_block()

        assert "# PERSISTENT CONTEXT & MEMORY TIERS" in prompt_block
        assert "[SOUL:" in prompt_block
        assert "[USER:" in prompt_block
        assert "[MEMORY:" in prompt_block
        assert "[AGENTS:" in prompt_block
        assert "<soul>" in prompt_block
        assert "<user_profile>" in prompt_block
        assert "<curated_memory>" in prompt_block
        assert "<agent_rules>" in prompt_block


def test_capacity_overflow_enforcement() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = ContextFileManager(root_dir=tmpdir, auto_create=True)

        oversized_content = "یک متن تستی بسیار طولانی " * 300
        with pytest.raises(ContextCapacityError):
            manager.update("user", oversized_content, enforce_capacity=True)


def test_append_fact_and_compaction() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = ContextFileManager(root_dir=tmpdir, auto_create=True)
        manager.update("memory", "- Fact 1", enforce_capacity=False)
        manager.append_fact("memory", "Fact 2")
        manager.append_fact("memory", "Fact 1")  # duplicate

        cf = manager.get("memory")
        assert "Fact 2" in cf.content

        # Compact duplicate
        compacted = manager.compact("memory")
        assert compacted.content.count("Fact 1") == 1


def test_dialectical_user_tracker() -> None:
    tracker = DialecticalUserTracker(user_id="alice")

    # Persian coding turn
    turn1 = tracker.analyze_turn(
        "سلام! لطفاً همیشه برای پروژه‌های پایتون تست بنویس و جواب‌ها را خلاصه بگو."
    )
    assert turn1.language_preference == "fa"
    assert turn1.interaction_style in ("code_first & analytical", "concise")
    assert any("تست بنویس" in fact or "خلاصه" in fact for fact in turn1.known_facts)

    with tempfile.TemporaryDirectory() as tmpdir:
        manager = ContextFileManager(root_dir=tmpdir, auto_create=True)
        tracker.sync_to_context_manager(manager)

        user_file = manager.get("user")
        assert user_file is not None
        assert "Language Preference:" in user_file.content
