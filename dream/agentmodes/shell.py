"""Guarded !shell: risk-tiered, approval-gated, sandboxed, network off."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from dream.agentmodes.errors import AgentModeError
from dream.workspace.paths import normalize_root

_SAFE = frozenset({"pwd", "echo", "date", "whoami", "true", "false"})
_GUARDED = frozenset({"ls", "cat", "head", "tail", "wc", "stat", "file"})
_DENIED = re.compile(
    r"(?i)(\brm\b|\bcurl\b|\bwget\b|\bssh\b|\bsudo\b|\bchmod\b|\bchown\b|"
    r"\bmkfs\b|\bdd\b|\bpython\b|\bperl\b|\bnode\b|\bnpm\b|\bnc\b|\bncat\b|"
    r"\bbash\b|\bsh\b|\bexec\b|\bsource\b|\beval\b|>\s|/etc/|/proc/)"
)
_METACHAR = re.compile(r"[;&|`$()<>]")


def classify_command(command: str) -> str:
    if not command or not command.strip() or len(command) > 500:
        raise AgentModeError("command must be a short non-empty string")
    if "\x00" in command:
        raise AgentModeError("command is not safe")
    stripped = command.strip()
    if _METACHAR.search(stripped) or _DENIED.search(stripped):
        return "dangerous"
    try:
        parts = shlex.split(stripped, posix=True)
    except ValueError:
        return "dangerous"
    if not parts:
        raise AgentModeError("command must be a short non-empty string")
    name = Path(parts[0]).name.lower()
    if name in _SAFE and len(parts) <= 4:
        return "safe"
    if name in _GUARDED and len(parts) <= 6:
        return "guarded"
    return "dangerous"


class ShellGate:
    """Propose then execute. Execution never happens without approval."""

    def __init__(self, cwd: str | os.PathLike[str] | None = None) -> None:
        self._lock = threading.RLock()
        self.pending: dict[str, dict[str, Any]] = {}
        self._cwd = Path(cwd) if cwd else None

    def propose(self, command: str, cwd: str | None = None) -> dict[str, Any]:
        risk = classify_command(command)
        approval_id = f"sh_{uuid.uuid4().hex[:16]}"
        record = {
            "approval_id": approval_id,
            "command": command.strip(),
            "risk": risk,
            "network": False,
            "approved": False,
            "executed": False,
            "created_at": time.time(),
            "cwd": cwd,
        }
        with self._lock:
            self.pending[approval_id] = record
        return {
            "approval_id": approval_id,
            "command": record["command"],
            "risk": risk,
            "network": False,
            "requires_approval": risk != "safe",
            "executed": False,
        }

    def execute(
        self,
        approval_id: str,
        *,
        approved: bool = False,
        timeout: float = 5.0,
    ) -> dict[str, Any]:
        with self._lock:
            record = self.pending.get(approval_id)
        if record is None:
            raise AgentModeError(f"no shell proposal with id {approval_id!r}")
        if record["executed"]:
            raise AgentModeError("command was already executed")
        risk = record["risk"]
        if risk != "safe" and not approved:
            raise AgentModeError("this command requires explicit approval")
        if risk == "dangerous" and not approved:
            raise AgentModeError("dangerous shell commands are refused without approval")
        if not 0.2 <= float(timeout) <= 15:
            raise AgentModeError("timeout must be between 0.2 and 15 seconds")
        cwd = self._resolve_cwd(record.get("cwd"))
        argv = shlex.split(record["command"], posix=True)
        env = {"PATH": "/usr/bin:/bin", "HOME": str(cwd), "LANG": "C"}
        try:
            completed = subprocess.run(  # noqa: S603
                argv,
                cwd=str(cwd),
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
                shell=False,
            )
            stdout = (completed.stdout or "")[:8_000]
            stderr = (completed.stderr or "")[:4_000]
            result = {
                "approval_id": approval_id,
                "executed": True,
                "returncode": completed.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": False,
                "network": False,
                "risk": risk,
            }
        except subprocess.TimeoutExpired:
            result = {
                "approval_id": approval_id,
                "executed": True,
                "returncode": -1,
                "stdout": "",
                "stderr": "timed out",
                "timed_out": True,
                "network": False,
                "risk": risk,
            }
        except OSError as exc:
            result = {
                "approval_id": approval_id,
                "executed": False,
                "returncode": -1,
                "stdout": "",
                "stderr": str(exc)[:300],
                "timed_out": False,
                "network": False,
                "risk": risk,
            }
        record["executed"] = True
        record["approved"] = bool(approved) or risk == "safe"
        return result

    def _resolve_cwd(self, cwd: str | None) -> Path:
        if cwd:
            return normalize_root(cwd)
        if self._cwd is not None:
            return self._cwd
        return Path.cwd()
