"""Path safety for workspace roots: no traversal, no dangerous links.

Every file operation resolves against an allowlisted root. Symlinks and
``..`` segments that would leave the root are refused. The preview path
never executes anything.
"""

from __future__ import annotations

import os
from pathlib import Path

from dream.workspace.errors import WorkspaceSecurityError

_NULL = "\x00"
_MAX_PATH = 4_096


def _refuse(message: str) -> None:
    raise WorkspaceSecurityError(message)


def normalize_root(path: str | os.PathLike[str]) -> Path:
    """Return a real directory that is safe to register as a workspace root.

    In-place import never copies and never follows a symlink root.
    """
    if not isinstance(path, (str, os.PathLike)):
        _refuse("path must be a string")
    raw = os.fspath(path)
    if not raw or not raw.strip() or _NULL in raw or len(raw) > _MAX_PATH:
        _refuse("path must be a non-empty safe string")
    candidate = Path(raw).expanduser()
    if candidate.is_symlink():
        _refuse("workspace root must not be a symbolic link")
    if not candidate.exists() or not candidate.is_dir():
        _refuse("workspace root must be an existing directory")
    resolved = candidate.resolve()
    if resolved.is_symlink():
        _refuse("workspace root must not be a symbolic link")
    return resolved


def relative_key(rel: str | None) -> str:
    """Normalise a caller-supplied relative path (empty = root)."""
    if rel is None:
        return ""
    if not isinstance(rel, str) or _NULL in rel or len(rel) > _MAX_PATH:
        _refuse("relative path is not safe")
    text = rel.replace("\\", "/").strip()
    if text in {"", "."}:
        return ""
    if text.startswith("/") or (len(text) >= 2 and text[1] == ":"):
        _refuse("absolute paths are not permitted")
    parts = [part for part in text.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        _refuse("parent-directory traversal is refused")
    return "/".join(parts)


def resolve_inside(root: Path, rel: str | None) -> Path:
    """Resolve *rel* under *root*, refusing every escape attempt."""
    key = relative_key(rel)
    root = root.resolve()
    target = (root / key).resolve() if key else root
    try:
        target.relative_to(root)
    except ValueError:
        _refuse("path escapes the workspace root")
    _refuse_symlink_escape(root, target)
    return target


def _refuse_symlink_escape(root: Path, target: Path) -> None:
    """Walk from *root* to *target* and refuse any link that leaves *root*."""
    try:
        relative = target.relative_to(root)
    except ValueError:
        _refuse("path escapes the workspace root")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            linked = current.resolve()
            try:
                linked.relative_to(root)
            except ValueError:
                _refuse("symbolic link points outside the workspace root")


def is_within(root: Path, candidate: Path) -> bool:
    """True when *candidate* resolves inside *root* without following escapes."""
    try:
        resolve_inside(root, str(candidate.relative_to(root)))
        return True
    except (WorkspaceSecurityError, ValueError):
        return False
