"""Facade for /plan, /goal, /stop, live subagent status, and chat references."""

from __future__ import annotations

import threading
from typing import Any

from dream.agentmodes.errors import AgentModeError
from dream.agentmodes.goal import GoalMode
from dream.agentmodes.plan import PlanMode
from dream.agentmodes.refs import command_palette, parse_references
from dream.agentmodes.shell import ShellGate
from dream.agentmodes.status import SubagentStatusRegistry
from dream.workspace.service import get_service as workspace_service


class AgentModeService:
    def __init__(self) -> None:
        self.plans = PlanMode()
        self.goals = GoalMode()
        self.subagents = SubagentStatusRegistry()
        self.shell = ShellGate()
        self._lock = threading.RLock()

    def plan(self, prompt: str, language: str = "en") -> dict[str, Any]:
        record = self.plans.plan(prompt, language=language)
        self.subagents.upsert(
            name="planner",
            status="pending_approval",
            latest_action="drafted plan",
            progress=0.2,
            agent_id=record["plan_id"],
        )
        return record

    def continue_plan(self, plan_id: str, step_delay: float = 0.0) -> dict[str, Any]:
        record = self.plans.continue_plan(plan_id, step_delay=step_delay)
        self.subagents.upsert(
            name="planner",
            status=record["status"],
            latest_action="executed plan" if record["executed"] else record["status"],
            progress=1.0 if record["status"] == "complete" else 0.5,
            agent_id=plan_id,
        )
        return record

    def goal(
        self, objective: str, criteria: list[str], allow_network: bool = False
    ) -> dict[str, Any]:
        record = self.goals.start(objective, criteria, allow_network=allow_network)
        self.subagents.upsert(
            name="goal",
            status=record["status"],
            latest_action=record["report"],
            progress=1.0 if record["status"] == "complete" else 0.6,
            agent_id=record["goal_id"],
        )
        return record

    def report(self, goal_id: str) -> dict[str, Any]:
        return self.goals.evaluate(goal_id)

    def stop(
        self,
        *,
        plan_id: str | None = None,
        goal_id: str | None = None,
        subagent_id: str | None = None,
    ) -> dict[str, Any]:
        plans = self.plans.stop(plan_id)
        goals = self.goals.stop(goal_id)
        subs = self.subagents.cancel(subagent_id)
        return {
            "stopped": True,
            "live": True,
            "plans": plans.get("plans", []),
            "goals": goals.get("goals", []),
            "subagents": subs.get("subagents", []),
        }

    def status(self) -> dict[str, Any]:
        plans = list(self.plans.plans.values())
        goals = list(self.goals.goals.values())
        running = any(item["status"] in {"running", "pending_approval"} for item in plans + goals)
        cancelled = any(item["status"] == "cancelled" for item in plans + goals)
        return {
            "running": running,
            "cancelled": cancelled and not running,
            "live": True,
            "plans": plans[-10:],
            "goals": goals[-10:],
            "subagents": self.subagents.list()["subagents"],
        }

    def live_subagents(self) -> dict[str, Any]:
        return self.subagents.list()

    def refs_parse(self, text: str) -> dict[str, Any]:
        return parse_references(text)

    def refs_file(self, root_id: str, rel: str) -> dict[str, Any]:
        preview = workspace_service().files_preview(root_id, rel)
        summary = (preview.get("text") or "")[:1_200]
        if not summary and preview.get("table"):
            summary = f"table {preview['name']} ({preview['table'].get('row_count', 0)} rows)"
        return {
            "path": preview.get("path"),
            "type": preview.get("type"),
            "summary": summary,
            "chart": preview.get("chart"),
        }

    def refs_conversation(self, session_id: str) -> dict[str, Any]:
        if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 80:
            raise AgentModeError("session_id must be a non-empty string")
        return {
            "session_id": session_id.strip(),
            "reference": f"#{session_id.strip()}",
            "kind": "conversation",
        }

    def commands(self, query: str = "") -> dict[str, Any]:
        return command_palette(query)

    def shell_propose(self, command: str, cwd: str | None = None) -> dict[str, Any]:
        return self.shell.propose(command, cwd=cwd)

    def shell_execute(self, approval_id: str, approved: bool = False) -> dict[str, Any]:
        return self.shell.execute(approval_id, approved=approved)


_service: AgentModeService | None = None
_lock = threading.Lock()


def get_service() -> AgentModeService:
    global _service
    with _lock:
        if _service is None:
            _service = AgentModeService()
        return _service


def reset_service(service: AgentModeService | None = None) -> AgentModeService | None:
    global _service
    with _lock:
        _service = service
        return _service
