"""Tests for extensible toolsets and dynamic tool filtering (Phase 1 / PR #3)."""

import json

from dream import tools
from dream.tools.toolsets import (
    filter_tools,
    get_toolset,
    list_toolsets,
    register_toolset,
    unregister_toolset,
)


def test_builtin_toolsets_present():
    """Verify built-in toolsets are registered and contain expected tools."""
    toolsets = list_toolsets()
    names = {ts.name for ts in toolsets}
    assert {"core", "workspace", "web", "skills", "reminders", "system"}.issubset(names)

    core = get_toolset("core")
    assert core is not None
    assert "calculate" in core.tools
    assert "get_datetime" in core.tools

    ws = get_toolset("workspace")
    assert ws is not None
    assert "read_note" in ws.tools
    assert "write_note" in ws.tools
    assert "list_notes" in ws.tools


def test_register_and_unregister_custom_toolset():
    """Verify registration, query, and unregistration of custom toolsets."""
    custom = register_toolset(
        "analysis",
        tools=["calculate", "read_note"],
        description="Data and math analysis toolset",
        metadata={"category": "analytics"},
    )
    assert custom.name == "analysis"
    assert "calculate" in custom.tools
    assert "read_note" in custom.tools

    queried = get_toolset("analysis")
    assert queried == custom

    assert unregister_toolset("analysis") is True
    assert get_toolset("analysis") is None
    assert unregister_toolset("non_existent") is False


def test_filter_tools_by_toolset():
    """Verify filtering registered tools by toolset names."""
    core_tools = filter_tools(toolsets=["core"])
    assert set(core_tools.keys()) == {"get_datetime", "calculate"}

    core_and_ws = filter_tools(toolsets=["core", "workspace"])
    assert "calculate" in core_and_ws
    assert "read_note" in core_and_ws
    assert "run_shell" not in core_and_ws


def test_filter_tools_with_include_and_exclude():
    """Verify fine-grained tool filtering with includes and excludes."""
    # Start with workspace toolset, include calculate, exclude write_note
    filtered = filter_tools(
        toolsets=["workspace"],
        include_tools=["calculate"],
        exclude_tools=["write_note"],
    )
    assert "calculate" in filtered
    assert "read_note" in filtered
    assert "list_notes" in filtered
    assert "write_note" not in filtered


def test_schemas_with_filtered_toolset():
    """Verify schema generators accept filtered tool registries."""
    filtered = filter_tools(toolsets=["core"])

    oa = tools.openai_schemas(registry=filtered)
    assert len(oa) == 2
    names = {t["function"]["name"] for t in oa}
    assert names == {"get_datetime", "calculate"}

    ant = tools.anthropic_schemas(registry=filtered)
    assert len(ant) == 2
    names_ant = {t["name"] for t in ant}
    assert names_ant == {"get_datetime", "calculate"}

    gem = tools.gemini_schemas(registry=filtered)
    assert len(gem) == 1
    assert len(gem[0]["function_declarations"]) == 2


def test_backward_compatible_exports():
    """Verify dream.tools re-exports all essential tools and metadata."""
    assert hasattr(tools, "Tool")
    assert hasattr(tools, "REGISTRY")
    assert hasattr(tools, "calculate")
    assert hasattr(tools, "get_datetime")
    assert hasattr(tools, "read_note")
    assert hasattr(tools, "write_note")
    assert hasattr(tools, "list_notes")
    assert hasattr(tools, "search_web")
    assert hasattr(tools, "read_page")
    assert hasattr(tools, "run_shell")
    assert hasattr(tools, "send_email")
    assert hasattr(tools, "execute")
    assert hasattr(tools, "openai_schemas")
    assert hasattr(tools, "anthropic_schemas")
    assert hasattr(tools, "gemini_schemas")
    assert hasattr(tools, "filter_tools")
    assert hasattr(tools, "list_toolsets")


def test_tool_execution_safe_and_dangerous():
    """Verify execution behavior for safe vs dangerous tools."""
    # Safe calculation
    res = json.loads(tools.execute("calculate", {"expression": "12 + 8"}))
    assert res["status"] == "ok"
    assert res["result"] == 20

    # Unknown tool
    res_unknown = json.loads(tools.execute("fake_tool", {}))
    assert res_unknown["status"] == "error"
    assert res_unknown["error"]["type"] == "unknown_tool"

    # Dangerous tool without approval
    res_danger = json.loads(tools.execute("run_shell", {"command": "echo test"}, approved=False))
    assert res_danger["status"] == "error"
    assert res_danger["error"]["type"] == "approval_required"
