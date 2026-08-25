"""Persist workspace roots as path pointers. Folders are never copied."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from dream.workspace.errors import WorkspaceError
from dream.workspace.paths import normalize_root

_DEFAULT_PATH = "data/workspace_registry.json"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


class WorkspaceRegistry:
    """On-disk index of in-place folder pointers (never copies)."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path or os.environ.get("DREAM_WORKSPACE_REGISTRY", _DEFAULT_PATH))
        self._lock = threading.RLock()
        self.roots: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        rows = raw.get("roots") if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            return
        for row in rows:
            if isinstance(row, dict) and row.get("root_id"):
                self.roots[str(row["root_id"])] = row

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            payload = {"roots": list(self.roots.values())}
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def register(
        self,
        folder: str,
        *,
        name: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Register *folder* in place. The directory is never copied."""
        root = normalize_root(folder)
        display = (name or root.name or "Workspace").strip() or "Workspace"
        now = time.time()
        record = {
            "root_id": _new_id("wsr"),
            "name": display,
            "path": str(root),
            "imported_in_place": True,
            "copied": False,
            "project_id": project_id,
            "session_id": session_id,
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self.roots[record["root_id"]] = record
            self._save()
        return dict(record)

    def unregister(self, root_id: str) -> dict[str, Any]:
        with self._lock:
            record = self.roots.pop(root_id, None)
            if record is None:
                raise WorkspaceError(f"no workspace root with id {root_id!r}")
            self._save()
        return {"deleted": True, "root_id": root_id}

    def get(self, root_id: str) -> dict[str, Any]:
        with self._lock:
            record = self.roots.get(root_id)
        if record is None:
            raise WorkspaceError(f"no workspace root with id {root_id!r}")
        return dict(record)

    def list(
        self, *, project_id: str | None = None, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = [dict(row) for row in self.roots.values()]
        if project_id:
            rows = [row for row in rows if row.get("project_id") == project_id]
        if session_id:
            rows = [row for row in rows if row.get("session_id") == session_id]
        rows.sort(key=lambda row: float(row.get("updated_at") or 0), reverse=True)
        return rows

    def bind(self, root_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            record = self.roots.get(root_id)
            if record is None:
                raise WorkspaceError(f"no workspace root with id {root_id!r}")
            for key in ("project_id", "session_id", "name"):
                if key in fields:
                    record[key] = fields[key]
            record["updated_at"] = time.time()
            self._save()
            return dict(record)
