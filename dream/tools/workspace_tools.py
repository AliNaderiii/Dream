"""Workspace file operations (notes) with path security and reserved device protection."""

from __future__ import annotations

from pathlib import Path

from dream.memory import normalize_fa
from dream.tools.base import WORKSPACE_ROOT, tool

# Windows reserved device names: case-insensitive, extension does not release.
# 22 base names; comparison uses the stem before the first dot after Persian
# folding (normalize_fa) so Persian digits folded to Latin are caught.
_RESERVED_DEVICE_NAMES: frozenset[str] = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *{f"com{i}" for i in range(1, 10)},
        *{f"lpt{i}" for i in range(1, 10)},
    }
)


def _workspace_root() -> Path:
    """Return the current workspace root, honoring any monkeypatches on dream.tools."""
    import dream.tools as _dt

    return getattr(_dt, "WORKSPACE_ROOT", WORKSPACE_ROOT)


def _reserved_stem(name: str) -> str:
    """Return the lower-cased stem before the first dot after folding."""
    folded = normalize_fa(name).lower().strip()
    # Strip trailing dots/spaces as Windows does before lookup.
    folded = folded.rstrip(" .")
    if not folded:
        return ""
    stem = folded.split(".")[0].strip()
    return stem


def _is_reserved_name(name: str) -> bool:
    """Whether *name* is a Windows reserved device name."""
    return _reserved_stem(name) in _RESERVED_DEVICE_NAMES


def _check_reserved_path(rel: str) -> None:
    """Raise ValueError if any path component is a reserved device name."""
    # Check trailing dot/space hazard (Windows collision).
    stripped = rel.strip()
    if stripped.endswith(".") or stripped.endswith(" "):
        raise ValueError(f"path must not end with a trailing dot or space: {rel!r}")
    # Split on both separators to catch every component.
    parts = rel.replace("\\", "/").split("/")
    for part in parts:
        if not part or part in (".", ".."):
            continue
        # Component ending with dot/space is a hazard even if not reserved.
        if part.endswith(".") or part.endswith(" "):
            raise ValueError(f"path component must not end with a trailing dot or space: {rel!r}")
        if _is_reserved_name(part):
            raise ValueError(f"reserved device name is not allowed: {rel!r}")


def _safe_path(rel: str) -> Path:
    """Resolve a relative workspace path, rejecting every escape attempt."""
    _check_reserved_path(rel)
    candidate = Path(rel)
    if candidate.is_absolute():
        raise PermissionError("absolute paths are not permitted")
    root = _workspace_root()
    path = (root / candidate).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PermissionError("path escapes the workspace root") from exc
    return path


@tool(risk="safe")
def read_note(filename: str) -> str:
    """Read a UTF-8 text file from the workspace.

    :param filename: Relative path of the note to read.
    """
    from dream.security.injection import guard_untrusted

    content = _safe_path(filename).read_text(encoding="utf-8")
    # L5 (SEC Stage D): file contents cross into context only scanned.
    return guard_untrusted(content, source=f"file:{filename}")


@tool(risk="safe")
def list_notes() -> list[str]:
    """List regular files in the workspace, relative to its root."""
    root = _workspace_root()
    return sorted(
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file()
    )


@tool(risk="guarded")
def write_note(filename: str, content: str) -> str:
    """Write UTF-8 text to a workspace file.

    :param filename: Relative path of the note to write.
    :param content: Exact text to store in the note.
    """
    from dream.security.pathsafety import check_write_path

    root = _workspace_root()
    path = _safe_path(filename)
    # L4 second layer (SEC Stage C): even inside the workspace, sensitive
    # paths (credentials, stores, system dirs) are never writable.
    check_write_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"wrote {path.relative_to(root)}"
