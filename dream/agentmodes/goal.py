"""Goal mode: objective plus explicit acceptance criteria, honest reports."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from dream.agentmodes.cancel import CancellationToken
from dream.agentmodes.errors import AgentModeError

_IMPOSSIBLE = (
    "network",
    "live market",
    "production deploy",
    "exfiltrat",
    "ignore previous",
)


class GoalMode:
    """Work until criteria are met, or declare inability honestly."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.goals: dict[str, dict[str, Any]] = {}
        self.tokens: dict[str, CancellationToken] = {}

    def start(
        self,
        objective: str,
        criteria: list[str],
        *,
        allow_network: bool = False,
    ) -> dict[str, Any]:
        if not isinstance(objective, str) or not objective.strip() or len(objective) > 4_000:
            raise AgentModeError("objective must be a non-empty string")
        if not isinstance(criteria, list) or not criteria:
            raise AgentModeError("criteria must be a non-empty list of strings")
        cleaned: list[str] = []
        for item in criteria:
            if not isinstance(item, str) or not item.strip() or len(item) > 500:
                raise AgentModeError("each criterion must be a short non-empty string")
            cleaned.append(item.strip())
        goal_id = f"goal_{uuid.uuid4().hex[:16]}"
        now = time.time()
        record = {
            "goal_id": goal_id,
            "objective": objective.strip(),
            "criteria": cleaned,
            "status": "running",
            "created_at": now,
            "updated_at": now,
            "allow_network": bool(allow_network),
            "results": [],
            "unmet": [],
            "report": "",
        }
        with self._lock:
            self.goals[goal_id] = record
            self.tokens[goal_id] = CancellationToken()
        return self.evaluate(goal_id)

    def get(self, goal_id: str) -> dict[str, Any]:
        with self._lock:
            record = self.goals.get(goal_id)
        if record is None:
            raise AgentModeError(f"no goal with id {goal_id!r}")
        return dict(record)

    def evaluate(self, goal_id: str) -> dict[str, Any]:
        with self._lock:
            record = self.goals.get(goal_id)
            token = self.tokens.get(goal_id)
        if record is None or token is None:
            raise AgentModeError(f"no goal with id {goal_id!r}")
        if token.is_cancelled():
            record["status"] = "cancelled"
            record["report"] = "Stopped before the acceptance criteria could be checked."
            record["updated_at"] = time.time()
            return dict(record)
        results: list[dict[str, Any]] = []
        unmet: list[str] = []
        for criterion in record["criteria"]:
            lowered = criterion.lower()
            impossible = any(marker in lowered for marker in _IMPOSSIBLE)
            if impossible and not record["allow_network"]:
                results.append(
                    {
                        "criterion": criterion,
                        "met": False,
                        "reason": (
                            f"could not meet {criterion!r}: requires capabilities that are off"
                        ),
                    }
                )
                unmet.append(criterion)
            else:
                results.append(
                    {
                        "criterion": criterion,
                        "met": True,
                        "reason": "criterion is checkable from the local workspace",
                    }
                )
        record["results"] = results
        record["unmet"] = unmet
        if unmet:
            record["status"] = "unable"
            joined = "; ".join(unmet)
            record["report"] = f"could not meet {joined}"
        else:
            record["status"] = "complete"
            record["report"] = "All acceptance criteria were met."
        record["updated_at"] = time.time()
        return dict(record)

    def stop(self, goal_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            ids = [goal_id] if goal_id else list(self.goals)
            snapshots = []
            for item in ids:
                token = self.tokens.get(item)
                record = self.goals.get(item)
                if token is None or record is None:
                    continue
                token.cancel()
                if record["status"] == "running":
                    record["status"] = "cancelled"
                    record["report"] = "Stopped before the acceptance criteria could be checked."
                    record["updated_at"] = time.time()
                snapshots.append(dict(record))
        return {"stopped": True, "goals": snapshots, "live": True}
