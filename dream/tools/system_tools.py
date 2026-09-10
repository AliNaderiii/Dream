"""System tools requiring elevated or dangerous permissions (shell, email)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from dream.tools.base import WORKSPACE_ROOT, tool


def _workspace_root() -> Path:
    """Return the current workspace root, honoring any monkeypatches on dream.tools."""
    import dream.tools as _dt

    return getattr(_dt, "WORKSPACE_ROOT", WORKSPACE_ROOT)


@tool(risk="dangerous")
def run_shell(command: str, timeout: int = 30) -> dict[str, Any]:
    """Run a shell command after explicit human approval.

    :param command: Shell command to run.
    :param timeout: Maximum execution time in seconds.
    """
    # ``shell=True`` is the entire point of this tool (pipes, redirection and
    # compound commands). It is gated behind the ``dangerous`` risk tier, which
    # the approval policy refuses to execute without an interactive approver,
    # so the shell is only ever invoked with explicit human consent.
    completed = subprocess.run(  # nosec B602
        command,
        shell=True,
        cwd=_workspace_root(),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


@tool(risk="dangerous")
def send_email(to: str, subject: str, body: str) -> dict[str, str]:
    """Describe an email that would be sent; this stub never sends mail.

    :param to: Intended recipient address.
    :param subject: Intended email subject.
    :param body: Intended email body.
    """
    return {
        "status": "dry-run",
        "message": f"Would send email to {to!r} with subject {subject!r}",
        "body": body,
    }
