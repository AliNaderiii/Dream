"""Unit and integration tests for Universal Migration Subsystem (Hermes & OpenClaw)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from dream.migration import (
    HermesMigrationAdapter,
    MigrationEngine,
    MigrationItemType,
    MigrationOptions,
    MigrationSanitizer,
    MigrationSourceType,
    MigrationStatus,
    OpenClawMigrationAdapter,
    get_migration_tools,
    handle_migration_slash_command,
    migration_analyze_source,
    migration_execute,
    migration_export_report,
    migration_get_status,
    reset_global_migration_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_migration_engine() -> None:
    reset_global_migration_engine()
    yield
    reset_global_migration_engine()


def test_toolset_includes_migration() -> None:
    """Verify migration toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("migration")
    assert ts is not None
    assert "migration_analyze_source" in ts.tools
    assert "migration_execute" in ts.tools
    assert "migration_get_status" in ts.tools
    assert "migration" in BUILTIN_TOOLSETS


def test_sanitizer_path_safety_and_persian_normalization() -> None:
    """Verify security path guards and typography normalization."""
    sanitizer = MigrationSanitizer()

    # 1. Path safety rejection
    assert sanitizer.is_safe_source_path("/etc/shadow") is False
    assert sanitizer.is_safe_source_path("../../passwords.txt") is False
    assert sanitizer.is_safe_source_path("safe/local/workspace") is True

    # 2. Persian normalizations (Arabic Yeh/Kaf to Persian, and half-space standardization)
    raw_persian = "كتاب آموزشي پايتون مي باشد و بسيار مفيد است."
    norm, changes = sanitizer.normalize_persian_text(raw_persian)
    assert "کتاب" in norm
    assert "آموزشی" in norm
    assert "پایتون" in norm
    assert "می‌باشد" in norm
    assert changes >= 4


def test_hermes_migration_adapter_inspection() -> None:
    """Verify discovery of 4 core context files and skills in Hermes structure."""
    adapter = HermesMigrationAdapter()

    with tempfile.TemporaryDirectory() as tmpdir:
        hermes_dir = Path(tmpdir)

        # Create Hermes context files
        (hermes_dir / "SOUL.md").write_text(
            "# Soul\nYou are Hermes Agent with Persian empathy.",
            encoding="utf-8",
        )
        (hermes_dir / "USER.md").write_text(
            "# User Profile\nName: Ali\nLanguage: Persian (فارسي)",
            encoding="utf-8",
        )
        (hermes_dir / "MEMORY.md").write_text(
            "- User loves high-performance agentic systems.",
            encoding="utf-8",
        )
        (hermes_dir / "AGENTS.md").write_text(
            "Instructions for workspace tools.",
            encoding="utf-8",
        )

        # Create a skill
        skill_dir = hermes_dir / "skills" / "weather_skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "# Weather Skill\nFetches Tehran temperature.",
            encoding="utf-8",
        )

        # Create config
        (hermes_dir / "config.json").write_text(
            json.dumps({"model": "hermes-3-70b", "temperature": 0.7}),
            encoding="utf-8",
        )

        items = adapter.inspect_workspace(hermes_dir)
        assert len(items) >= 5

        types_found = [it.item_type for it in items]
        assert MigrationItemType.SOUL in types_found
        assert MigrationItemType.USER_PROFILE in types_found
        assert MigrationItemType.MEMORY_NOTE in types_found
        assert MigrationItemType.SKILL in types_found
        assert MigrationItemType.CONFIG in types_found


def test_openclaw_migration_adapter_inspection() -> None:
    """Verify extraction of OpenClaw agent manifests and memories."""
    adapter = OpenClawMigrationAdapter()

    with tempfile.TemporaryDirectory() as tmpdir:
        claw_dir = Path(tmpdir)

        # Create claw.json
        (claw_dir / "claw.json").write_text(
            json.dumps({"name": "OpenClaw Worker", "persona": "Helpful AI Assistant"}),
            encoding="utf-8",
        )

        # Create memory_store.json
        mem_payload = {
            "memories": [
                {"content": "Fact 1: Python is great"},
                {"content": "Fact 2: Dream is fast"},
            ]
        }
        (claw_dir / "memory_store.json").write_text(
            json.dumps(mem_payload),
            encoding="utf-8",
        )

        items = adapter.inspect_workspace(claw_dir)
        assert len(items) >= 3
        titles = [it.title for it in items]
        assert any("OpenClaw" in t for t in titles)


def test_migration_engine_end_to_end() -> None:
    """Verify complete migration workflow, dry run preview, and target output."""
    engine = MigrationEngine()

    with tempfile.TemporaryDirectory() as src_dir, tempfile.TemporaryDirectory() as dest_dir:
        src = Path(src_dir)
        (src / "SOUL.md").write_text("# Core Identity\nAgent Soul.", encoding="utf-8")
        (src / "MEMORY.md").write_text("- Fast response required.", encoding="utf-8")

        # 1. Analyze Source Plan
        plan = engine.analyze_source(str(src), source_type=MigrationSourceType.HERMES)
        assert plan.total_discovered_items == 2
        assert plan.source_type == MigrationSourceType.HERMES

        # 2. Dry Run Execution
        opts_dry = MigrationOptions(dry_run=True, target_dir=dest_dir)
        rep_dry = engine.execute_migration(str(src), options=opts_dry)
        assert rep_dry.status == MigrationStatus.COMPLETED
        assert rep_dry.total_imported == 2
        assert not (Path(dest_dir) / "context" / "SOUL.md").exists()

        # 3. Real Run Execution
        opts_real = MigrationOptions(dry_run=False, target_dir=dest_dir)
        rep_real = engine.execute_migration(str(src), options=opts_real)
        assert rep_real.total_imported == 2
        assert (Path(dest_dir) / "context" / "SOUL.md").exists()
        assert "Dream" in engine.format_migration_report()


def test_migration_tools_and_slash_commands() -> None:
    """Verify LLM tool declarations and CLI /migrate commands."""
    tools = get_migration_tools()
    assert len(tools) >= 4

    with tempfile.TemporaryDirectory() as src_dir, tempfile.TemporaryDirectory() as dest_dir:
        src = Path(src_dir)
        (src / "SOUL.md").write_text("# Identity\nEmpathic Dreamer.", encoding="utf-8")
        (src / "USER.md").write_text("# User\nAli Naderi.", encoding="utf-8")

        # Tool: analyze
        res_an = migration_analyze_source(str(src))
        assert res_an["success"] is True
        assert res_an["plan"]["total_discovered_items"] == 2

        # Tool: execute
        res_ex = migration_execute(str(src), target_dir=dest_dir)
        assert res_ex["success"] is True
        assert res_ex["report"]["total_imported"] == 2

        # Tool: status & report
        st = migration_get_status()
        assert st["success"] is True
        assert st["total_migrations_executed"] >= 1

        rep = migration_export_report()
        assert rep["success"] is True
        assert "Universal Migration Report" in rep["markdown_report"]

        # Slash: /migrate
        slash_help = handle_migration_slash_command("/migrate")
        assert "راهنمای دستورات مهاجرت" in slash_help

        # Slash: /migrate analyze
        slash_an = handle_migration_slash_command(f"/migrate analyze {src}")
        assert "طرح مهاجرت آماده شد" in slash_an

        # Slash: /migrate hermes
        slash_run = handle_migration_slash_command(f"/migrate hermes {src} --dry")
        assert "عملیات مهاجرت با موفقیت پایان یافت" in slash_run

        # Slash: /migrate status
        slash_st = handle_migration_slash_command("/migrate status")
        assert "وضعیت سیستم مهاجرت" in slash_st

        # Slash: /migrate reset
        slash_rst = handle_migration_slash_command("/migrate reset")
        assert "بازنشانی شد" in slash_rst
