"""File model and bounded, lazy listings for workspace roots."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any

from dream.workspace.errors import WorkspaceError, WorkspaceSecurityError
from dream.workspace.paths import resolve_inside

LIST_CAP = 200

_KIND_BY_SUFFIX: dict[str, str] = {
    ".md": "markdown",
    ".txt": "text",
    ".csv": "csv",
    ".tsv": "tsv",
    ".json": "json",
    ".jsonl": "json",
    ".py": "code",
    ".ts": "code",
    ".tsx": "code",
    ".js": "code",
    ".rs": "code",
    ".go": "code",
    ".html": "html",
    ".htm": "html",
    ".css": "code",
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".webp": "image",
    ".svg": "image",
    ".mp4": "video",
    ".webm": "video",
    ".mov": "video",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".pptx": "pptx",
    ".ipynb": "jupyter",
    ".yaml": "text",
    ".yml": "text",
}


def classify(path: Path, is_dir: bool) -> str:
    if is_dir:
        return "directory"
    return _KIND_BY_SUFFIX.get(path.suffix.lower(), "file")


def _stat_entry(path: Path, root: Path) -> dict[str, Any]:
    is_dir = path.is_dir()
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise WorkspaceError(f"cannot stat {path.name}") from exc
    relative = str(path.relative_to(root)).replace("\\", "/")
    mime, _ = mimetypes.guess_type(path.name)
    return {
        "path": relative,
        "name": path.name,
        "size": 0 if is_dir else int(info.st_size),
        "type": classify(path, is_dir),
        "mime": mime or ("inode/directory" if is_dir else "application/octet-stream"),
        "mtime": float(info.st_mtime),
        "is_dir": is_dir,
        "symlink": path.is_symlink(),
    }


def list_entries(
    root: Path,
    rel: str | None = None,
    *,
    cursor: int = 0,
    limit: int = 100,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """Bounded listing. Symlinks are skipped, never followed."""
    if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0:
        raise WorkspaceError("cursor must be a non-negative integer")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= LIST_CAP:
        raise WorkspaceError(f"limit must be an integer from 1 to {LIST_CAP}")
    directory = resolve_inside(root, rel)
    if not directory.is_dir() or directory.is_symlink():
        raise WorkspaceSecurityError("listing target must be a real directory inside the root")
    names: list[str] = []
    try:
        with os.scandir(directory) as iterator:
            for entry in iterator:
                if len(names) >= LIST_CAP + cursor:
                    break
                if not include_hidden and entry.name.startswith("."):
                    continue
                names.append(entry.name)
    except OSError as exc:
        raise WorkspaceError("directory could not be listed") from exc
    names.sort(key=str.lower)
    page = names[cursor : cursor + limit]
    entries: list[dict[str, Any]] = []
    for name in page:
        path = directory / name
        if path.is_symlink():
            continue
        try:
            entries.append(_stat_entry(path, root))
        except (WorkspaceError, OSError):
            continue
    next_cursor = cursor + len(page)
    has_more = next_cursor < len(names)
    relative = "" if directory == root else str(directory.relative_to(root)).replace("\\", "/")
    return {
        "path": relative,
        "entries": entries,
        "count": len(entries),
        "cursor": cursor,
        "next_cursor": next_cursor if has_more else None,
        "has_more": has_more,
        "truncated": len(names) >= LIST_CAP + cursor,
    }


def stat_entry(root: Path, rel: str) -> dict[str, Any]:
    path = resolve_inside(root, rel)
    if path.is_symlink():
        raise WorkspaceSecurityError("symbolic links are not readable")
    if not path.exists():
        raise WorkspaceError("path not found")
    return _stat_entry(path, root)
