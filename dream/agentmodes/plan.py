"""Plan-then-execute: produce a plan first, run only after continue."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from dream.agentmodes.cancel import CancellationToken
from dream.agentmodes.errors import AgentModeError

_STEPS_HINTS = (
    "Gather the relevant workspace files and conversations",
    "Draft the change or analysis without applying it",
    "Apply the approved steps and record provenance",
)


class PlanMode:
    """Offline-deterministic planner. Execution waits for continue."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.plans: dict[str, dict[str, Any]] = {}
        self.tokens: dict[str, CancellationToken] = {}

    def plan(self, prompt: str, *, language: str = "en") -> dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8_000:
            raise AgentModeError("prompt must be a non-empty string of at most 8000 characters")
        plan_id = f"plan_{uuid.uuid4().hex[:16]}"
        now = time.time()
        persian = language == "fa" or any("\u0600" <= ch <= "\u06ff" for ch in prompt)
        steps = [
            {"index": index, "title": title, "status": "pending"}
            for index, title in enumerate(_STEPS_HINTS, start=1)
        ]
        record = {
            "plan_id": plan_id,
            "prompt": prompt.strip(),
            "status": "pending_approval",
            "steps": steps,
            "summary": prompt.strip()[:240],
            "language": "fa" if persian else "en",
            "created_at": now,
            "updated_at": now,
            "executed": False,
            "error": "",
        }
        with self._lock:
            self.plans[plan_id] = record
            self.tokens[plan_id] = CancellationToken()
        return dict(record)

    def get(self, plan_id: str) -> dict[str, Any]:
        with self._lock:
            record = self.plans.get(plan_id)
        if record is None:
            raise AgentModeError(f"no plan with id {plan_id!r}")
        return dict(record)

    def continue_plan(self, plan_id: str, *, step_delay: float = 0.0) -> dict[str, Any]:
        with self._lock:
            record = self.plans.get(plan_id)
            token = self.tokens.get(plan_id)
        if record is None or token is None:
            raise AgentModeError(f"no plan with id {plan_id!r}")
        if record["status"] not in {"pending_approval", "running", "cancelled"}:
            raise AgentModeError(f"plan cannot continue from {record['status']}")
        if record["status"] == "cancelled" or token.is_cancelled():
            record["status"] = "cancelled"
            record["updated_at"] = time.time()
            return dict(record)
        record["status"] = "running"
        record["updated_at"] = time.time()
        try:
            delay = float(step_delay)
        except (TypeError, ValueError):
            delay = 0.0
        if delay < 0.0:
            delay = 0.0
        elif delay > 2.0:
            delay = 2.0
        for step in record["steps"]:
            if token.is_cancelled():
                record["status"] = "cancelled"
                record["updated_at"] = time.time()
                return dict(record)
            if delay:
                token.wait(delay)
            if token.is_cancelled():
                record["status"] = "cancelled"
                record["updated_at"] = time.time()
                return dict(record)
            step["status"] = "done"
        record["status"] = "complete"
        record["executed"] = True
        record["updated_at"] = time.time()
        return dict(record)

    def stop(self, plan_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            ids = [plan_id] if plan_id else list(self.plans)
            snapshots = []
            for item in ids:
                token = self.tokens.get(item)
                record = self.plans.get(item)
                if token is None or record is None:
                    continue
                token.cancel()
                if record["status"] in {"pending_approval", "running"}:
                    record["status"] = "cancelled"
                    record["updated_at"] = time.time()
                snapshots.append(dict(record))
        if plan_id and not snapshots:
            raise AgentModeError(f"no plan with id {plan_id!r}")
        return {"stopped": True, "plans": snapshots, "live": True}
