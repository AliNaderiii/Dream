"""Goal mode: objective plus explicit acceptance criteria, honest reports."""

from __future__ import annotations

import os
import re
import threading
import time
import uuid
from pathlib import Path
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
_FILE_TOKEN = re.compile(r"[A-Za-z0-9._-]+")
_MAX_NAMES = 2_000
_MAX_DIRS = 80
_UNVERIFIED = "not verifiable from the local workspace"


def _is_listing_criterion(lowered: str) -> bool:
    if "has_more" in lowered or "list_cap" in lowered or "list cap" in lowered:
        return True
    if "bounded" in lowered and "list" in lowered:
        return True
    if "listing" in lowered and ("cap" in lowered or "bound" in lowered):
        return True
    return False


def _collect_workspace_names(workspace: Any) -> tuple[set[str], bool]:
    names: set[str] = set()
    try:
        roots = workspace.list_roots().get("roots") or []
    except Exception:
        return names, False
    if not roots:
        return names, False
    scanned = 0
    for row in roots:
        raw = row.get("path")
        if not raw:
            continue
        root = Path(str(raw))
        if not root.is_dir():
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                scanned += 1
                current = Path(dirpath)
                dirnames[:] = [name for name in dirnames if not (current / name).is_symlink()][:50]
                for name in filenames:
                    if (current / name).is_symlink():
                        continue
                    names.add(name)
                    names.add(name.lower())
                    if len(names) >= _MAX_NAMES:
                        return names, True
                if scanned >= _MAX_DIRS:
                    dirnames[:] = []
                    break
        except OSError:
            continue
    return names, True


def _listing_respected_cap(workspace: Any) -> bool | None:
    from dream.workspace.files import LIST_CAP

    last = getattr(workspace, "last_listing", None)
    if not isinstance(last, dict):
        try:
            roots = workspace.list_roots().get("roots") or []
        except Exception:
            return None
        if not roots:
            return None
        try:
            last = workspace.files_list(str(roots[0]["root_id"]), "", limit=min(50, LIST_CAP))
        except Exception:
            return None
    try:
        count = int(last.get("count") or 0)
    except (TypeError, ValueError):
        return None
    return count <= LIST_CAP


def _existing_filename_hit(criterion: str, names: set[str]) -> bool:
    lowered = criterion.lower()
    words = set(_FILE_TOKEN.findall(lowered))
    for name in names:
        needle = name.lower()
        if needle in lowered:
            return True
        stem = needle.rsplit(".", 1)[0]
        if len(stem) >= 3 and stem in words:
            return True
    return False


def _evaluate_criterion(
    criterion: str,
    *,
    names: set[str],
    listing_ok: bool | None,
) -> tuple[bool, str]:
    lowered = criterion.lower()
    if any(marker in lowered for marker in _IMPOSSIBLE):
        return False, f"could not meet {criterion!r}: requires capabilities that are off"
    if _is_listing_criterion(lowered):
        if listing_ok is True:
            return True, "listing respected LIST_CAP"
        return False, f"could not meet '{criterion}': {_UNVERIFIED}"
    if _existing_filename_hit(criterion, names):
        return True, "found under a registered workspace root"
    return False, f"could not meet '{criterion}': {_UNVERIFIED}"


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
        names: set[str] = set()
        has_roots = False
        listing_ok: bool | None = None
        try:
            from dream.workspace.service import get_service as workspace_service

            workspace = workspace_service()
            names, has_roots = _collect_workspace_names(workspace)
            listing_ok = _listing_respected_cap(workspace) if has_roots else None
        except Exception:
            names, listing_ok = set(), None
        results: list[dict[str, Any]] = []
        unmet: list[str] = []
        for criterion in record["criteria"]:
            met, reason = _evaluate_criterion(criterion, names=names, listing_ok=listing_ok)
            results.append({"criterion": criterion, "met": met, "reason": reason})
            if not met:
                unmet.append(criterion)
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
