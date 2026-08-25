"""Facade for the local-first workspace: roots, files, preview, projects 2.0."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from dream.workspace.errors import WorkspaceError, WorkspaceSecurityError
from dream.workspace.files import LIST_CAP, list_entries, stat_entry
from dream.workspace.paths import normalize_root
from dream.workspace.preview import preview_file
from dream.workspace.projects import ProjectOverlay
from dream.workspace.registry import WorkspaceRegistry

_DEFAULT_OPS = "data/workspace_ops.jsonl"


class WorkspaceService:
    """Process-wide workspace runtime. Listings are bounded; imports never copy."""

    def __init__(
        self,
        *,
        registry_path: str | os.PathLike[str] | None = None,
        projects_path: str | os.PathLike[str] | None = None,
    ) -> None:
        self.registry = WorkspaceRegistry(registry_path)
        self.projects = ProjectOverlay(projects_path)
        self._lock = threading.RLock()
        self.ops_path = Path(os.environ.get("DREAM_WORKSPACE_OPS", _DEFAULT_OPS))
        self.last_listing: dict[str, Any] | None = None

    def _log(self, action: str, **fields: Any) -> None:
        try:
            self.ops_path.parent.mkdir(parents=True, exist_ok=True)
            line = {"action": action, **fields}
            with self.ops_path.open("a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")
        except OSError:
            pass

    def _root_path(self, root_id: str) -> Path:
        record = self.registry.get(root_id)
        return normalize_root(str(record["path"]))

    def import_folder(
        self,
        folder: str,
        *,
        name: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        adopt_project: bool = True,
    ) -> dict[str, Any]:
        """Register *folder* in place. The directory is never copied."""
        root = self.registry.register(
            folder, name=name, project_id=project_id, session_id=session_id
        )
        project = None
        if adopt_project:
            project = self.projects.adopt(folder, name=name)
            self.registry.bind(root["root_id"], project_id=project["project_id"])
            root["project_id"] = project["project_id"]
        listing = list_entries(Path(root["path"]), "", cursor=0, limit=min(50, LIST_CAP))
        self.last_listing = listing
        self._log("import_folder", root_id=root["root_id"], copied=False, path=root["path"])
        return {
            "root": root,
            "project": project,
            "copied": False,
            "imported_in_place": True,
            "listing": listing,
        }

    def list_roots(
        self, *, project_id: str | None = None, session_id: str | None = None
    ) -> dict[str, Any]:
        roots = self.registry.list(project_id=project_id, session_id=session_id)
        return {"roots": roots, "count": len(roots)}

    def unregister(self, root_id: str) -> dict[str, Any]:
        return self.registry.unregister(root_id)

    def registered_root(self, cwd: str | os.PathLike[str]) -> Path:
        """Return *cwd* only when it is an existing registered workspace root."""
        try:
            resolved = normalize_root(cwd)
        except (WorkspaceError, WorkspaceSecurityError) as exc:
            raise WorkspaceError("cwd must be a registered workspace root") from exc
        for row in self.registry.list():
            try:
                if Path(str(row.get("path", ""))).resolve() == resolved:
                    return resolved
            except OSError:
                continue
        raise WorkspaceError("cwd must be a registered workspace root")

    def files_list(
        self,
        root_id: str,
        rel: str | None = None,
        *,
        cursor: int = 0,
        limit: int = 100,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        listing = list_entries(
            self._root_path(root_id),
            rel,
            cursor=cursor,
            limit=limit,
            include_hidden=include_hidden,
        )
        listing["root_id"] = root_id
        return listing

    def files_stat(self, root_id: str, rel: str) -> dict[str, Any]:
        record = stat_entry(self._root_path(root_id), rel)
        record["root_id"] = root_id
        return record

    def files_preview(self, root_id: str, rel: str) -> dict[str, Any]:
        preview = preview_file(self._root_path(root_id), rel)
        preview["root_id"] = root_id
        self._log("preview", root_id=root_id, path=rel, executed=False)
        return preview

    def files_read(self, root_id: str, rel: str) -> dict[str, Any]:
        preview = self.files_preview(root_id, rel)
        return {
            "root_id": root_id,
            "path": preview["path"],
            "type": preview["type"],
            "text": preview.get("text") or "",
            "truncated": preview.get("truncated", False),
        }

    def project_adopt(self, folder: str, name: str | None = None) -> dict[str, Any]:
        imported = self.import_folder(folder, name=name, adopt_project=True)
        return imported

    def project_settings(
        self, project_id: str, updates: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not project_id:
            raise WorkspaceError("project_id must be a non-empty string")
        return self.projects.settings(project_id, updates)

    def project_move_session(self, project_id: str, session_id: str) -> dict[str, Any]:
        moved = self.projects.move_session(project_id, session_id)
        self._log("move_session", project_id=project_id, session_id=session_id)
        return moved


_service: WorkspaceService | None = None
_lock = threading.Lock()


def get_service() -> WorkspaceService:
    global _service
    with _lock:
        if _service is None:
            _service = WorkspaceService()
        return _service


def reset_service(service: WorkspaceService | None = None) -> WorkspaceService | None:
    global _service
    with _lock:
        _service = service
        return _service
