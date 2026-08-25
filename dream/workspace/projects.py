"""Projects 2.0 overlay: in-place import, session move, project settings.

Existing ``project.*`` RPCs stay untouched. This module stores extra fields
beside the workspace registry and optionally writes compatible rows into the
same projects index the sidecar already uses.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from dream.workspace.errors import WorkspaceError
from dream.workspace.paths import normalize_root

_DEFAULT_PROJECTS = "data/bridge_projects.json"


def _project_path() -> Path:
    return Path(os.environ.get("DREAM_PROJECTS_PATH", _DEFAULT_PROJECTS))


def _load_projects(path: Path) -> list[dict[str, Any]]:
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _save_projects(path: Path, rows: list[dict[str, Any]]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def _as_project(row: dict[str, Any]) -> dict[str, Any]:
    project_id = str(row.get("id") or row.get("project_id") or "")
    settings = row.get("settings") if isinstance(row.get("settings"), dict) else {}
    return {
        "project_id": project_id,
        "id": project_id,
        "name": str(row.get("name") or "Project"),
        "folder": row.get("folder") if isinstance(row.get("folder"), str) else None,
        "session_ids": [str(item) for item in row.get("session_ids", []) if isinstance(item, str)],
        "created_at": float(row.get("created_at") or 0),
        "updated_at": float(row.get("updated_at") or 0),
        "imported_in_place": bool(row.get("imported_in_place", True)),
        "copied": bool(row.get("copied", False)),
        "settings": {
            "default_mode": str(settings.get("default_mode") or "chat"),
            "language": str(settings.get("language") or "en"),
        },
    }


class ProjectOverlay:
    """Backward-compatible extra fields for Projects 2.0."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path else _project_path()

    def adopt(self, folder: str, *, name: str | None = None) -> dict[str, Any]:
        """Import an existing folder in place (explicitly never copied)."""
        root = normalize_root(folder)
        rows = _load_projects(self.path)
        for row in rows:
            if row.get("folder") == str(root):
                row["imported_in_place"] = True
                row["copied"] = False
                row["updated_at"] = time.time()
                _save_projects(self.path, rows)
                return _as_project(row)
        now = time.time()
        project = {
            "id": f"prj_{uuid.uuid4().hex[:20]}",
            "name": (name or root.name or "Project").strip() or "Project",
            "folder": str(root),
            "session_ids": [],
            "created_at": now,
            "updated_at": now,
            "imported_in_place": True,
            "copied": False,
            "settings": {"default_mode": "chat", "language": "en"},
        }
        rows.append(project)
        _save_projects(self.path, rows)
        return _as_project(project)

    def settings(self, project_id: str, updates: dict[str, Any] | None = None) -> dict[str, Any]:
        rows = _load_projects(self.path)
        for row in rows:
            if str(row.get("id") or row.get("project_id")) == project_id:
                current = row.get("settings") if isinstance(row.get("settings"), dict) else {}
                if updates:
                    if "default_mode" in updates:
                        mode = str(updates["default_mode"])
                        if mode not in {"chat", "plan", "goal"}:
                            raise WorkspaceError("default_mode must be chat, plan, or goal")
                        current["default_mode"] = mode
                    if "language" in updates:
                        language = str(updates["language"])
                        if not language or len(language) > 16:
                            raise WorkspaceError("language must be a short locale tag")
                        current["language"] = language
                    row["settings"] = current
                    row["updated_at"] = time.time()
                    _save_projects(self.path, rows)
                return _as_project(row)
        raise WorkspaceError(f"no project with id {project_id!r}")

    def move_session(self, project_id: str, session_id: str) -> dict[str, Any]:
        if not session_id or not isinstance(session_id, str):
            raise WorkspaceError("session_id must be a non-empty string")
        rows = _load_projects(self.path)
        target = None
        for row in rows:
            ids = [str(item) for item in row.get("session_ids", []) if isinstance(item, str)]
            if session_id in ids:
                ids.remove(session_id)
                row["session_ids"] = ids
                row["updated_at"] = time.time()
            if str(row.get("id") or row.get("project_id")) == project_id:
                target = row
        if target is None:
            raise WorkspaceError(f"no project with id {project_id!r}")
        ids = [str(item) for item in target.get("session_ids", []) if isinstance(item, str)]
        if session_id not in ids:
            ids.append(session_id)
        target["session_ids"] = ids
        target["updated_at"] = time.time()
        _save_projects(self.path, rows)
        return _as_project(target)
