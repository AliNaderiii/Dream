"""Tests for Layered Context Hierarchy subsystem (SOUL, AGENTS, USER, MEMORY)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from dream.context import (
    ContextEngine,
    ContextLoader,
    ContextTier,
    TokenBudgetManager,
    context_assemble_prompt,
    context_get_budget_report,
    context_get_tier,
    context_reload_all,
    context_update_tier,
    get_context_tools,
    handle_context_command,
    reset_global_context_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


def test_context_loader_defaults():
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ContextLoader(root_dir=tmpdir)
        files = loader.load_all()

        assert len(files) == 4
        assert ContextTier.SOUL in files
        assert ContextTier.AGENTS in files
        assert ContextTier.USER in files
        assert ContextTier.MEMORY in files

        soul_file = files[ContextTier.SOUL]
        assert "SOUL.md" in soul_file.filename
        assert len(soul_file.content) > 20
        assert (Path(tmpdir) / "SOUL.md").exists()


def test_context_loader_update_and_caching():
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ContextLoader(root_dir=tmpdir)

        # Update USER.md
        success = loader.save_tier(ContextTier.USER, "# USER Preferences\nTheme: Dark")
        assert success is True

        # Load back
        user_file = loader.load_tier(ContextTier.USER)
        assert "Theme: Dark" in user_file.content

        # Direct file check
        disk_content = (Path(tmpdir) / "USER.md").read_text(encoding="utf-8")
        assert "Theme: Dark" in disk_content


def test_waterfall_token_budget_allocation():
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ContextLoader(root_dir=tmpdir)
        files = loader.load_all()

        budget_mgr = TokenBudgetManager(total_max_chars=8000)
        allocated = budget_mgr.allocate_budgets(files)

        assert len(allocated) == 4
        report = budget_mgr.get_budget_report(files)

        assert report["total_max_chars"] == 8000
        assert "soul" in report["tiers"]
        assert "memory" in report["tiers"]
        assert report["estimated_tokens"] > 0


def test_context_engine_assembly():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ContextEngine(root_dir=tmpdir)
        assembly = engine.assemble_context()

        assert "BEGIN CONTEXT TIER: SOUL.md" in assembly.rendered_text
        assert "BEGIN CONTEXT TIER: AGENTS.md" in assembly.rendered_text
        assert "BEGIN CONTEXT TIER: USER.md" in assembly.rendered_text
        assert "BEGIN CONTEXT TIER: MEMORY.md" in assembly.rendered_text

        assert assembly.total_chars > 50
        assert assembly.estimated_tokens > 10
        assert len(assembly.tier_lengths) == 4


def test_context_tools_and_slash():
    reset_global_context_engine()
    tools = get_context_tools()
    assert len(tools) == 5

    soul_data = context_get_tier("soul")
    assert soul_data["tier"] == "soul"

    up_res = context_update_tier("user", "# Custom Preferences")
    assert up_res["success"] is True

    budget_data = context_get_budget_report()
    assert "tiers" in budget_data

    prompt_data = context_assemble_prompt()
    assert "BEGIN CONTEXT TIER: SOUL.md" in prompt_data["rendered_text"]

    reloaded = context_reload_all()
    assert "soul" in reloaded

    # Slash command tests
    lines = []
    handle_context_command("/context status", output=lines.append)
    assert any("SOUL.md" in line for line in lines)

    lines.clear()
    handle_context_command("/context view soul", output=lines.append)
    assert any("SOUL.md" in line for line in lines)

    lines.clear()
    handle_context_command("/context reload", output=lines.append)
    assert any("4" in line for line in lines)

    reset_global_context_engine()


def test_toolset_includes_context():
    assert "context" in BUILTIN_TOOLSETS
    toolset = get_toolset("context")
    assert toolset is not None
    assert len(toolset.tools) >= 5
    assert "context_get_tier" in toolset.tools
    assert "context_assemble_prompt" in toolset.tools
