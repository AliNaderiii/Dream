"""Tests for Multi-Profile & Persona Isolation subsystem."""

import tempfile
from pathlib import Path

from dream.profiles import (
    ProfileManager,
    get_profile_tools,
    handle_profile_command,
    profile_create,
    profile_get_current,
    profile_list,
    profile_switch,
    reset_global_profile_manager,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


def test_profile_manager_defaults():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = ProfileManager(root_dir=tmpdir)
        active = mgr.get_active_profile()
        assert active.name == "default"
        assert "default" in [p.name for p in mgr.list_profiles()]


def test_profile_create_and_switch():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = ProfileManager(root_dir=tmpdir)
        prof = mgr.create_profile(
            name="coding_expert",
            display_name="Senior Architect",
            persona_prompt="Write high quality Python code",
            default_model="claude-3-5-sonnet",
        )
        assert prof.name == "coding_expert"
        assert prof.display_name == "Senior Architect"

        mgr.switch_profile("coding_expert")
        active = mgr.get_active_profile()
        assert active.name == "coding_expert"
        assert active.persona_prompt == "Write high quality Python code"


def test_profile_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr1 = ProfileManager(root_dir=tmpdir)
        mgr1.create_profile("researcher", display_name="AI Scientist")
        mgr1.switch_profile("researcher")

        mgr2 = ProfileManager(root_dir=tmpdir)
        active = mgr2.get_active_profile()
        assert active.name == "researcher"
        assert active.display_name == "AI Scientist"


def test_profile_deletion_safety():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = ProfileManager(root_dir=tmpdir)
        mgr.create_profile("temp_p")

        # Cannot delete default
        assert mgr.delete_profile("default") is False

        # Cannot delete currently active
        mgr.switch_profile("temp_p")
        assert mgr.delete_profile("temp_p") is False

        # Switch away and then delete
        mgr.switch_profile("default")
        assert mgr.delete_profile("temp_p") is True
        assert mgr.get_profile("temp_p") is None


def test_profile_export_and_import():
    with tempfile.TemporaryDirectory() as tmpdir:
        p_dir = Path(tmpdir) / "profiles"
        mgr = ProfileManager(root_dir=p_dir)
        mgr.create_profile(
            "finance_bot",
            display_name="Financial Analyst",
            persona_prompt="Analyze markets",
        )

        export_path = Path(tmpdir) / "finance.json"
        assert mgr.export_profile("finance_bot", export_path) is True
        assert export_path.exists()

        p_dir2 = Path(tmpdir) / "profiles2"
        mgr2 = ProfileManager(root_dir=p_dir2)
        imported = mgr2.import_profile(export_path)
        assert imported is not None
        assert imported.name == "finance_bot"
        assert imported.display_name == "Financial Analyst"


def test_profile_tools_and_slash():
    reset_global_profile_manager()
    tools = get_profile_tools()
    assert len(tools) == 4

    p_created = profile_create("test_persona", persona_prompt="Test Prompt")
    assert p_created["name"] == "test_persona"

    p_switched = profile_switch("test_persona")
    assert p_switched["name"] == "test_persona"
    assert p_switched["is_active"] is True

    curr = profile_get_current()
    assert curr["name"] == "test_persona"

    all_profs = profile_list()
    assert any(p["name"] == "test_persona" for p in all_profs)

    # Slash command tests
    lines = []
    handle_profile_command("/profile list", output=lines.append)
    assert any("test_persona" in line for line in lines)

    lines.clear()
    handle_profile_command("/profile info", output=lines.append)
    assert any("test_persona" in line for line in lines)

    reset_global_profile_manager()


def test_toolset_includes_profiles():
    assert "profiles" in BUILTIN_TOOLSETS
    toolset = get_toolset("profiles")
    assert toolset is not None
    assert len(toolset.tools) >= 4
    assert "profile_list" in toolset.tools
    assert "profile_switch" in toolset.tools
