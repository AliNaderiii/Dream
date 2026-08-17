"""Credential-leak scan (Security audit, P-11).

Scans every git-tracked text file for high-entropy API-key and private-key
shapes. Nothing resembling a real secret may be committed, exported, or
recorded in the repository.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Deliberately broad shapes: any hit is triaged by a human, never silently kept.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI-style keys
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),  # GitHub personal access tokens
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access-key IDs
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),  # Slack tokens
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),  # private keys
]

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _tracked_files() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [_REPO_ROOT / p for p in out.split("\0") if p]


def _is_text(path: Path) -> bool:
    try:
        path.read_text(encoding="utf-8")
        return True
    except (UnicodeDecodeError, OSError):
        return False


def test_no_secrets_in_tracked_files() -> None:
    files = _tracked_files()
    assert files, "git ls-files returned nothing; running outside the repo?"
    hits: list[str] = []
    for path in files:
        if not _is_text(path):
            continue
        for pattern in _SECRET_PATTERNS:
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{path.relative_to(_REPO_ROOT)}:{line_no}")
    assert not hits, f"possible credentials found in tracked files: {hits}"
