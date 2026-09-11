"""Comprehensive test suite for the Multi-Subagent Orchestration Subsystem."""

from __future__ import annotations

import json
from unittest.mock import patch

from dream.subagents.coordinator import BUILTIN_ROLES
from dream.subagents.slash import handle_subagent_command
from dream.subagents.tools import (
    get_subagent_manager,
    reset_subagent_manager,
    subagent_delegate_task,
    subagent_list,
    subagent_spawn,
    subagent_terminate,
    subagent_wait,
)
from dream.subagents.types import SubAgent
from dream.tools.toolsets import filter_tools, get_toolset


def test_builtin_subagent_roles():
    """Verify all 5 built-in subagent roles and their system prompts."""
    expected_roles = {"researcher", "coder", "data_analyst", "planner", "reviewer"}
    assert expected_roles.issubset(set(BUILTIN_ROLES.keys()))

    planner = BUILTIN_ROLES["planner"]
    assert "planner" in planner.name
    assert "calculate" in planner.tools

    reviewer = BUILTIN_ROLES["reviewer"]
    assert "reviewer" in reviewer.name
    assert "read_note" in reviewer.tools


def test_subagent_manager_and_tools_lifecycle():
    """Verify spawning, waiting, and listing subagents via tools."""
    reset_subagent_manager()
    _ = get_subagent_manager()

    # Tool: subagent_spawn
    spawn_json = subagent_spawn(
        task="Search for solar calendar specs",
        name="test_worker",
        role="researcher",
        max_turns=5,
    )
    spawn_data = json.loads(spawn_json)
    assert "subagent_id" in spawn_data
    aid = spawn_data["subagent_id"]

    # Tool: subagent_wait
    wait_res = subagent_wait("nonexistent_id", timeout_seconds=1)
    assert "error" in json.loads(wait_res)

    # Tool: subagent_list
    list_json = subagent_list()
    list_data = json.loads(list_json)
    assert list_data["count"] >= 1
    assert any(a["id"] == aid for a in list_data["subagents"])

    # Tool: subagent_terminate
    term_res = subagent_terminate(aid)
    assert "canceled" in term_res


def test_subagent_delegate_task_execution():
    """Verify synchronous task delegation tool with mock backend."""
    reset_subagent_manager()
    mgr = get_subagent_manager()

    # Mock manager.wait to return finished agent
    mock_agent = SubAgent(
        id="mock_done",
        name="delegate_worker",
        parent_session_id=None,
        model_provider="echo",
        model_name="echo",
        system_prompt="",
        tools=[],
        prompt="Calculate optimal allocation",
        context="",
        status="completed",
        turn_count=2,
        token_count=150,
        result="Mock calculation outcome: 42",
    )

    with patch.object(mgr, "wait", return_value=mock_agent):
        res_json = subagent_delegate_task(
            task="Calculate optimal allocation",
            role="data_analyst",
            name="allocator",
        )
        data = json.loads(res_json)
        assert data["status"] == "completed"
        assert "42" in data["result"]


def test_subagent_slash_commands():
    """Verify `/subagent` and `/subagents` slash command handlers."""
    reset_subagent_manager()
    _ = get_subagent_manager()

    outputs: list[str] = []

    # /subagents roles
    handle_subagent_command("roles", output=outputs.append)
    assert any("Built-in Subagent Roles" in out or "نقش‌های پیش‌فرض" in out for out in outputs)

    # /subagents spawn
    outputs.clear()
    handle_subagent_command("spawn coder Write quicksort in python", output=outputs.append)
    assert any("زیرایجنت جدید" in out for out in outputs)

    # /subagents list
    outputs.clear()
    handle_subagent_command("list", output=outputs.append)
    assert any("فهرست زیرایجنت‌های سیستم" in out for out in outputs)


def test_subagents_toolset_registration():
    """Verify subagents toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("subagents")
    assert ts is not None
    assert "subagent_spawn" in ts.tools
    assert "subagent_delegate_task" in ts.tools

    filtered = filter_tools(toolsets=["subagents"])
    assert "subagent_spawn" in filtered
    assert "subagent_delegate_task" in filtered
