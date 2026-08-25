"""Live subagent status registry (progress + latest action)."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any


class SubagentStatusRegistry:
    """In-process live view of spawned workers. Never a stale UI-only copy."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.agents: dict[str, dict[str, Any]] = {}

    def upsert(
        self,
        *,
        name: str,
        status: str,
        latest_action: str = "",
        progress: float = 0.0,
        agent_id: str | None = None,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            existing = self.agents.get(agent_id) if agent_id else None
            record_id = (
                agent_id or (existing or {}).get("agent_id") or f"sub_{uuid.uuid4().hex[:12]}"
            )
            record = {
                "agent_id": record_id,
                "name": name,
                "status": status,
                "latest_action": latest_action,
                "progress": max(0.0, min(1.0, float(progress))),
                "parent_id": parent_id,
                "updated_at": now,
                "created_at": (existing or {}).get("created_at", now),
                "live": True,
            }
            self.agents[record_id] = record
            return dict(record)

    def list(self) -> dict[str, Any]:
        with self._lock:
            rows = sorted(self.agents.values(), key=lambda row: row["updated_at"], reverse=True)
        return {"subagents": [dict(row) for row in rows], "count": len(rows), "live": True}

    def cancel(self, agent_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            ids = [agent_id] if agent_id else list(self.agents)
            cancelled = []
            for item in ids:
                record = self.agents.get(item)
                if record is None:
                    continue
                if record["status"] in {"running", "paused", "queued"}:
                    record["status"] = "cancelled"
                    record["latest_action"] = "cancelled"
                    record["updated_at"] = time.time()
                cancelled.append(dict(record))
        return {"stopped": True, "subagents": cancelled, "live": True}
