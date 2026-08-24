"""Sensitive-path denylist and traversal defenses for writes (L4, G-09/G-10).

The workspace allowlist (``tools._safe_path``) confines every note to the
workspace; this module is the second layer: even inside an allowed root,
writes must never land on credentials, secret directories, Dream's own
stores, provenance, or system paths — on any platform. Checks run against
the symlink-resolved absolute path, so a planted link cannot smuggle a
write to ``~/.ssh``. 8.3 short names and UNC paths are refused outright.

Over-blocking a write is acceptable at this layer; letting a write reach a
credential store is not. An owner who needs such an edit does it by hand.
"""

from __future__ import annotations

import os
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["SensitiveHit", "check_write_path", "is_sensitive_path"]

_SYSTEM_DIRS_POSIX = (
    "/etc",
    "/boot",
    "/usr",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
    "/var",
    "/sys",
    "/proc",
    "/dev",
    "/root",
)

_SYSTEM_DIRS_WINDOWS = (
    "c:/windows",
    "c:/program files",
    "c:/program files (x86)",
    "c:/perflogs",
    "c:/boot",
    "c:/recovery",
)

#: Directory names that hold credentials wherever they appear.
_SECRET_DIR_MARKERS = (".ssh", ".aws", ".gnupg", ".kube", ".docker")

#: File names that are credentials or credential-adjacent, wherever they sit.
_SECRET_FILE_NAMES = frozenset(
    {
        ".netrc",
        ".npmrc",
        ".pypirc",
        ".git-credentials",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "id_dsa",
        "authorized_keys",
        "known_hosts",
        "credentials.json",
    }
)

#: Dream's own stores and registries — never writable through a tool.
_DREAM_STORE_FILES = frozenset(
    {
        "dream.db",
        "dream-bounded.db",
        "dream-session-index.db",
        "dream-skills.db",
        "dream-approvals.db",
        "gateway_tokens.json",
        "mcp_servers.json",
        "acp_agents.json",
        "bridge_disabled_skills.json",
        "bridge_projects.json",
    }
)

_WINDOWS_DRIVE_RE = re.compile(r"^[a-z]:/")
_SHORT_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,8}~\d(\.[A-Za-z0-9_]{1,3})?$")


@dataclass(frozen=True)
class SensitiveHit:
    """Why one path was refused, bilingually."""

    reason_en: str
    reason_fa: str
    pattern: str


def _refuse(pattern: str, what_en: str, what_fa: str) -> SensitiveHit:
    return SensitiveHit(
        reason_en=(
            f"write refused: {what_en} is a sensitive path ({pattern}). "
            "Dream never writes there."
        ),
        reason_fa=(
            "\u0646\u0648\u0634\u062a\u0646 \u0631\u062f \u0634\u062f: "
            f"{what_fa} \u06cc\u06a9 \u0645\u0633\u06cc\u0631 \u062d\u0633\u0627\u0633 "
            f"\u0627\u0633\u062a ({pattern}). \u062f\u0631\u06cc\u0645 \u0647\u0631\u06af\u0632 "
            "\u0622\u0646\u062c\u0627 \u0646\u0645\u06cc\u200c\u0646\u0648\u06cc\u0633\u062f."
        ),
        pattern=pattern,
    )


def _canon(text: str) -> str:
    return str(text).lower().replace("\\", "/")


def is_sensitive_path(path: str | os.PathLike[str]) -> SensitiveHit | None:
    """The refusal for *path*, or ``None`` when no denylist rule fires."""
    raw = str(path)
    flat = _canon(raw)

    # UNC / network share paths: never writable through Dream.
    if raw.startswith("\\\\") or raw.startswith("//"):
        return _refuse(
            "UNC", "a network share", "\u0645\u0633\u06cc\u0631 "
            "\u0634\u0628\u06a9\u0647\u200c\u0627\u06cc"
        )

    components = [part for part in flat.split("/") if part not in ("", ".")]
    for component in components:
        if _SHORT_NAME_RE.match(component):
            return _refuse(
                component,
                "an 8.3 short name (traversal alias)",
                "\u0646\u0627\u0645 \u06a9\u0648\u062a\u0627\u0647 8.3 "
                "(\u0631\u0627\u0647 \u06af\u0631\u06cc\u0632 "
                "\u067e\u06cc\u0645\u0627\u06cc\u0634)",
            )

    # Windows system locations — string-checked so the rule also holds on a
    # POSIX test box examining a Windows-shaped path.
    for system_dir in _SYSTEM_DIRS_WINDOWS:
        if _WINDOWS_DRIVE_RE.match(flat) and (
            flat == system_dir or flat.startswith(system_dir + "/")
        ):
            return _refuse(
                system_dir,
                "a Windows system directory",
                "\u067e\u0648\u0634\u0647\u200c\u06cc \u0633\u06cc\u0633\u062a\u0645\u06cc "
                "\u0648\u06cc\u0646\u062f\u0648\u0632",
            )
    if "/appdata/" in f"/{flat}/" or "/appdata roaming/" in f"/{flat}/":
        return _refuse(
            "AppData",
            "the Windows AppData tree",
            "\u0634\u0627\u062e\u0647\u200c\u06cc AppData \u0648\u06cc\u0646\u062f\u0648\u0632",
        )

    # Resolve symlinks for the filesystem checks: a link that points at a
    # secret directory is the secret directory.
    try:
        resolved = Path(os.path.expanduser(raw)).resolve()
    except OSError:
        resolved = Path(os.path.abspath(raw))
    resolved_flat = _canon(resolved)
    resolved_norm = posixpath.normpath(resolved_flat)

    for system_dir in _SYSTEM_DIRS_POSIX:
        if resolved_norm == system_dir or resolved_norm.startswith(system_dir + "/"):
            return _refuse(
                system_dir,
                "a system directory",
                "\u067e\u0648\u0634\u0647\u200c\u06cc \u0633\u06cc\u0633\u062a\u0645\u06cc",
            )

    home = _canon(Path.home())
    for marker in _SECRET_DIR_MARKERS:
        secret_dir = f"{home}/{marker}"
        if resolved_norm == secret_dir or resolved_norm.startswith(secret_dir + "/"):
            return _refuse(
                secret_dir,
                "a credentials directory",
                "\u067e\u0648\u0634\u0647\u200c\u06cc "
                "\u06af\u0648\u0627\u0647\u06cc\u200c\u0646\u0627\u0645\u0647\u200c\u0647\u0627",
            )

    name = resolved.name.lower()
    if name in _SECRET_FILE_NAMES or name.startswith(".env"):
        return _refuse(
            name,
            "a credentials file",
            "\u067e\u0631\u0648\u0646\u062f\u0647\u200c\u06cc "
            "\u06af\u0648\u0627\u0647\u06cc\u200c\u0646\u0627\u0645\u0647",
        )
    if name in _DREAM_STORE_FILES:
        return _refuse(
            name,
            "one of Dream's own stores",
            "\u06cc\u06a9\u06cc \u0627\u0632 \u0645\u062e\u0627\u0632\u0646 "
            "\u062e\u0648\u062f \u062f\u0631\u06cc\u0645",
        )
    if ".dream" in resolved.parts or "provenance" in resolved.parts:
        return _refuse(
            resolved.name,
            "Dream's private data",
            "\u062f\u0627\u062f\u0647\u200c\u0647\u0627\u06cc \u062e\u0635\u0648\u0635\u06cc "
            "\u062f\u0631\u06cc\u0645",
        )
    return None


def check_write_path(path: str | os.PathLike[str]) -> None:
    """Raise ``PermissionError`` (bilingual) when *path* is sensitive."""
    hit = is_sensitive_path(path)
    if hit is not None:
        raise PermissionError(f"{hit.reason_en}\n{hit.reason_fa}")
