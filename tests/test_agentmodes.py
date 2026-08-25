"""Plan-then-execute, honest goal reports, true /stop, and chat references."""

from __future__ import annotations

import threading
import time

import pytest

from dream.agentmodes.provider import AgentModePromptProvider
from dream.agentmodes.refs import parse_references
from dream.agentmodes.service import AgentModeService, reset_service
from dream.providers import ProviderManager


@pytest.fixture(autouse=True)
def _fresh_modes() -> None:
    reset_service(AgentModeService())
    yield
    reset_service(None)


def test_plan_waits_for_continue() -> None:
    modes = AgentModeService()
    planned = modes.plan("Draft the weekly summary")
    assert planned["status"] == "pending_approval"
    assert planned["executed"] is False
    continued = modes.continue_plan(planned["plan_id"])
    assert continued["status"] == "complete"
    assert continued["executed"] is True
    assert all(step["status"] == "done" for step in continued["steps"])


def test_goal_reports_honest_inability() -> None:
    modes = AgentModeService()
    result = modes.goal(
        "Keep the sales table honest",
        ["CSV preview has a chart", "must fetch live market prices"],
    )
    assert result["status"] == "unable"
    assert "could not meet" in result["report"]
    assert any("live market" in item.lower() for item in result["unmet"])


def test_goal_reports_honest_completion() -> None:
    modes = AgentModeService()
    result = modes.goal("Document the folder", ["README exists", "listing is bounded"])
    assert result["status"] == "complete"
    assert result["unmet"] == []
    assert "met" in result["report"].lower()


def test_stop_cancels_a_running_plan() -> None:
    modes = AgentModeService()
    planned = modes.plan("long running work")
    holder: dict[str, object] = {}

    def run() -> None:
        holder["result"] = modes.continue_plan(planned["plan_id"], step_delay=0.2)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    time.sleep(0.05)
    stopped = modes.stop(plan_id=planned["plan_id"])
    worker.join(timeout=2)
    assert worker.is_alive() is False
    assert stopped["stopped"] is True
    assert stopped["live"] is True
    result = holder.get("result") or modes.plans.get(planned["plan_id"])
    assert result["status"] == "cancelled"
    status = modes.status()
    assert status["live"] is True
    assert status["cancelled"] is True or any(
        item["status"] == "cancelled" for item in status["plans"]
    )


def test_chat_references_parse_file_conversation_command_and_shell() -> None:
    parsed = parse_references("see @sales.csv and #sess_abc /plan then !ls notes")
    assert "sales.csv" in parsed["files"]
    assert "sess_abc" in parsed["conversations"]
    assert "plan" in parsed["commands"]
    assert parsed["shell"]


def test_persian_slash_commands_are_recognised() -> None:
    parsed = parse_references("/\u0628\u0631\u0646\u0627\u0645\u0647 \u06a9\u0646")
    assert parsed["commands"]
    palette = AgentModeService().commands("\u0647\u062f\u0641")
    assert palette["count"] >= 1


def test_shell_is_approval_gated_and_network_off() -> None:
    modes = AgentModeService()
    proposal = modes.shell_propose("ls")
    assert proposal["network"] is False
    assert proposal["executed"] is False
    dangerous = modes.shell_propose("rm -rf /")
    assert dangerous["risk"] == "dangerous"
    assert dangerous["requires_approval"] is True


def test_contribute_prompt_hook_is_available_on_the_provider() -> None:
    provider = AgentModePromptProvider()
    manager = ProviderManager()
    manager.register(provider)
    block, items = manager.contribute_prompt("hello", 8_000)
    assert "agent modes" in block
    assert "agentmodes" in items
    assert manager.expose_tools() == []


def test_live_subagent_status_panel() -> None:
    modes = AgentModeService()
    modes.plan("x")
    live = modes.live_subagents()
    assert live["live"] is True
    assert live["count"] >= 1
    assert live["subagents"][0]["latest_action"]
