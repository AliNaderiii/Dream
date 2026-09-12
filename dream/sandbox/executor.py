"""Isolated code execution sandbox with output redirection and stateful namespace."""

from __future__ import annotations

import contextlib
import io
import math
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


class SandboxExecutor:
    """Safely runs code in a stateful isolated environment and captures artifacts."""

    def __init__(self, workspace_dir: str | Path | None = None) -> None:
        self.workspace_dir = Path(workspace_dir or "/tmp/dream_sandbox")
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self._namespace: dict[str, Any] = self._create_initial_namespace()
        self._forbidden_patterns = [
            r"rm\s+-rf\s+/",
            r"/etc/passwd",
            r"/etc/shadow",
            r"C:\\Windows\\System32",
            r"os\.system\(",
            r"subprocess\.Popen\(",
            r"shutil\.rmtree\(['\"]\/",
        ]

    def _create_initial_namespace(self) -> dict[str, Any]:
        """Set up standard math and utility namespace."""
        ns: dict[str, Any] = {
            "math": math,
            "__builtins__": __builtins__,
            "Path": Path,
            "json": __import__("json"),
            "re": re,
            "workspace_dir": str(self.workspace_dir),
        }
        return ns

    def reset_namespace(self) -> None:
        """Reset execution namespace to initial state."""
        self._namespace = self._create_initial_namespace()

    def execute_python(
        self,
        code: str,
        timeout_seconds: float = 15.0,
    ) -> ExecutionResult:
        """Execute Python code within the stateful session namespace."""
        start_time = time.monotonic()

        # Security check for destructive commands
        for pat in self._forbidden_patterns:
            if re.search(pat, code, re.IGNORECASE):
                return ExecutionResult(
                    code=code,
                    language=ExecutionLanguage.PYTHON,
                    status=ExecutionStatus.BLOCKED,
                    exit_code=1,
                    stdout="",
                    stderr="دستور به دلیل ملاحظات امنیتی مسدود شد.",
                    duration_ms=(time.monotonic() - start_time) * 1000,
                    error_message="Security Policy Refusal: Destructive pattern detected.",
                )

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        initial_keys = set(self._namespace.keys())
        initial_files = set(self.workspace_dir.glob("*")) if self.workspace_dir.exists() else set()

        status = ExecutionStatus.SUCCESS
        exit_code = 0
        err_msg = ""

        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            try:
                # If code is a single expression, evaluate and print
                try:
                    expr_ast = compile(code, "<sandbox>", "eval")
                    res = eval(expr_ast, self._namespace)
                    if res is not None:
                        print(repr(res))
                except SyntaxError:
                    exec_ast = compile(code, "<sandbox>", "exec")
                    exec(exec_ast, self._namespace)
            except Exception as exc:
                status = ExecutionStatus.ERROR
                exit_code = 1
                err_msg = f"{type(exc).__name__}: {str(exc)}"
                stderr_buf.write(f"\nTraceback: {err_msg}")

        duration = (time.monotonic() - start_time) * 1000
        new_keys = [
            k for k in self._namespace.keys() if k not in initial_keys and not k.startswith("_")
        ]

        # Discover new generated artifacts in workspace
        current_files = set(self.workspace_dir.glob("*")) if self.workspace_dir.exists() else set()
        new_files = current_files - initial_files
        artifacts: list[ExecutionArtifact] = []

        for f in new_files:
            if f.is_file():
                mime = "image/png" if f.suffix == ".png" else "text/plain"
                artifacts.append(
                    ExecutionArtifact(
                        name=f.name,
                        file_path=str(f),
                        mime_type=mime,
                        size_bytes=f.stat().st_size,
                        description_fa=f"فایل تولیدشده: {f.name}",
                    )
                )

        return ExecutionResult(
            code=code,
            language=ExecutionLanguage.PYTHON,
            status=status,
            exit_code=exit_code,
            stdout=stdout_buf.getvalue(),
            stderr=stderr_buf.getvalue(),
            duration_ms=duration,
            artifacts=artifacts,
            error_message=err_msg,
            variables_updated=new_keys,
        )
