"""Legacy code-interpreter executor — permanently disabled (MASTER-P0).

**This module no longer executes anything.** Its previous implementation ran
whatever text it was handed through a host ``compile``/``eval``/``exec`` with a
seven-regex blocklist in front of it. That is not a sandbox: the blocklist is
trivially bypassed (``__import__('o'+'s').system(...)``, ``getattr``, string
concatenation, ``pickle``, an aliased import), and every executed program had
the full authority of the Dream sidecar — the user's files, the network, the
process table, and any credential in the environment.

The route was already unreachable through the product (``sandbox.run_code`` was
dropped by the bridge's collision rule in favour of the container handler), but
"unreachable by accident" is not a control. The execution logic is therefore
gone, and :func:`SandboxExecutor.execute_python` fails closed.

The real execution path is :mod:`dream.security.codeexec`, which runs code in a
container and refuses when it cannot. See ``docs/security/code-execution.md``.

What survives here is analysis only: :meth:`SandboxExecutor.classify_python`
still returns the pattern verdict for a payload, because the tests and the
dataset profiler use it, and it never evaluates the payload.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from dream.sandbox.types import (
    ExecutionArtifact,
    ExecutionLanguage,
    ExecutionResult,
    ExecutionStatus,
)

#: The refusal every caller gets. Bilingual, like the rest of Dream's refusals.
HOST_EXECUTION_REMOVED_EN = (
    "refused: this executor no longer runs code on the host; Dream executes "
    "code only in a container"
)
HOST_EXECUTION_REMOVED_FA = (
    "رد شد: این اجراکننده دیگر کد را روی میزبان اجرا نمی‌کند؛ دریم کد را فقط "
    "در کانتینر اجرا می‌کند"
)

#: Patterns kept for *classification only*. They are not a security boundary and
#: must never be described as one.
_FORBIDDEN_PATTERNS: tuple[str, ...] = (
    r"rm\s+-rf\s+/",
    r"/etc/passwd",
    r"/etc/shadow",
    r"C:\\Windows\\System32",
    r"os\.system\(",
    r"subprocess\.Popen\(",
    r"shutil\.rmtree\(['\"]\/",
)


def classify_python(code: str) -> tuple[bool, str]:
    """Pattern-classify *code* without running it.

    Returns ``(flagged, pattern)``. ``flagged`` is advisory telemetry for the
    UI and the tests — the container, not this list, is the boundary.
    """
    if not isinstance(code, str):
        return False, ""
    for pattern in _FORBIDDEN_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            return True, pattern
    return False, ""


class SandboxExecutor:
    """A disabled executor that keeps its inspection API.

    The workspace directory and the artifact discovery helpers are retained
    because the dataset profiler and the tests exercise them; nothing here
    evaluates a program.
    """

    def __init__(self, workspace_dir: str | Path | None = None) -> None:
        self.workspace_dir = Path(workspace_dir or "/tmp/dream_sandbox")
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self._forbidden_patterns = list(_FORBIDDEN_PATTERNS)
        #: Kept for status compatibility. There is no namespace any more: the
        #: container is stateless, so a stale dict would be a lie.
        self._namespace: dict[str, Any] = {}

    # -- inspection (no execution) ----------------------------------------- #

    def reset_namespace(self) -> None:
        """Clear the (unused) namespace mapping."""
        self._namespace = {}

    def classify(self, code: str) -> tuple[bool, str]:
        """Advisory pattern verdict for *code*. Does not execute it."""
        return classify_python(code)

    # -- execution: fail closed -------------------------------------------- #

    def execute_python(
        self,
        code: str,
        timeout_seconds: float = 15.0,
    ) -> ExecutionResult:
        """Refuse to run *code*.

        Always returns ``UNAVAILABLE``. The signature is unchanged so existing
        callers get a structured refusal instead of an ``AttributeError``, and
        no caller can be surprised into thinking a program ran.
        """
        del timeout_seconds  # nothing to bound: nothing runs
        flagged, pattern = classify_python(code)
        detail = f" (flagged pattern: {pattern})" if flagged else ""
        return ExecutionResult(
            code=code if isinstance(code, str) else "",
            language=ExecutionLanguage.PYTHON,
            status=ExecutionStatus.UNAVAILABLE,
            exit_code=-1,
            stdout="",
            stderr=f"{HOST_EXECUTION_REMOVED_EN}{detail}\n{HOST_EXECUTION_REMOVED_FA}",
            duration_ms=0.0,
            error_message=f"host_execution_removed{detail}",
            variables_updated=[],
        )

    # -- artifact discovery (read-only) ------------------------------------ #

    def discover_artifacts(self, known: set[Path] | None = None) -> list[ExecutionArtifact]:
        """List files that appeared in the workspace since *known*."""
        baseline = known or set()
        if not self.workspace_dir.exists():
            return []
        artifacts: list[ExecutionArtifact] = []
        for path in sorted(self.workspace_dir.glob("*")):
            if path in baseline or not path.is_file():
                continue
            artifacts.append(
                ExecutionArtifact(
                    name=path.name,
                    file_path=str(path),
                    mime_type="image/png" if path.suffix == ".png" else "text/plain",
                    size_bytes=path.stat().st_size,
                    description_fa=f"فایل موجود در پوشهٔ کاری: {path.name}",
                )
            )
        return artifacts


def elapsed_ms(start: float) -> float:
    """Milliseconds since *start* (``time.monotonic``)."""
    return (time.monotonic() - start) * 1000


__all__ = [
    "HOST_EXECUTION_REMOVED_EN",
    "HOST_EXECUTION_REMOVED_FA",
    "SandboxExecutor",
    "classify_python",
    "elapsed_ms",
]
