"""Local hardened subprocess execution backend."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from dream.terminal.backends.base import BaseTerminalBackend
from dream.terminal.types import (
    BackendHealth,
    CommandExecutionRequest,
    CommandExecutionResult,
    TerminalBackendType,
)


class LocalTerminalBackend(BaseTerminalBackend):
    """Executes commands directly on the host in a hardened, bounded subprocess."""

    def __init__(self, default_cwd: str | None = None) -> None:
        super().__init__(TerminalBackendType.LOCAL)
        self.default_cwd = default_cwd or str(Path.cwd())

    def is_available(self) -> bool:
        """Local backend is always available on any Python host."""
        return True

    def health_check(self) -> BackendHealth:
        """Verify local shell execution."""
        start = time.perf_counter()
        try:
            cmd = ["echo", "health_ok"] if sys.platform != "win32" else "cmd /c echo health_ok"
            res = subprocess.run(
                cmd,
                shell=(sys.platform == "win32"),
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            duration_ms = (time.perf_counter() - start) * 1000
            ok = res.returncode == 0 and "health_ok" in res.stdout
            return BackendHealth(
                backend=self.backend_type,
                available=ok,
                details="Local host shell ready" if ok else "Local shell check failed",
                latency_ms=duration_ms,
                metadata={"platform": sys.platform, "default_cwd": self.default_cwd},
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            return BackendHealth(
                backend=self.backend_type,
                available=False,
                details=f"Local execution error: {exc}",
                latency_ms=duration_ms,
            )

    def execute(self, request: CommandExecutionRequest) -> CommandExecutionResult:
        """Execute command locally with timeout, output truncation, and environment isolation."""
        start_time = time.perf_counter()
        cwd = request.cwd or self.default_cwd

        # Build scrubbed child environment
        child_env = self._build_safe_env(request.env)

        # Determine shell invocation
        use_shell = True
        shell_cmd: Any = request.command

        try:
            proc = subprocess.Popen(
                shell_cmd,
                shell=use_shell,
                cwd=cwd,
                env=child_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
            )
            try:
                stdout_raw, stderr_raw = proc.communicate(timeout=request.timeout)
                timed_out = False
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_raw, stderr_raw = proc.communicate()
                timed_out = True

            duration_ms = (time.perf_counter() - start_time) * 1000

            # Truncate output if exceeding max bytes
            max_bytes = request.max_output_bytes
            is_truncated = False

            if len(stdout_raw) > max_bytes:
                stdout_raw = stdout_raw[:max_bytes] + "\n... [Output Truncated / خروجی کوتاه شد]"
                is_truncated = True

            if len(stderr_raw) > max_bytes:
                stderr_raw = stderr_raw[:max_bytes] + "\n... [Error Output Truncated]"
                is_truncated = True

            return CommandExecutionResult(
                command=request.command,
                returncode=proc.returncode if not timed_out else -1,
                stdout=stdout_raw,
                stderr=stderr_raw,
                duration_ms=duration_ms,
                backend=self.backend_type,
                is_truncated=is_truncated,
                timed_out=timed_out,
                error_message="Command execution timed out" if timed_out else None,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return CommandExecutionResult(
                command=request.command,
                returncode=-1,
                stdout="",
                stderr=str(exc),
                duration_ms=duration_ms,
                backend=self.backend_type,
                timed_out=False,
                error_message=str(exc),
            )

    def _build_safe_env(self, custom_env: dict[str, str]) -> dict[str, str]:
        """Scrub sensitive parent variables and merge allowed custom environment."""
        # Baseline minimal safe environment
        safe_keys = {
            "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
            "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL",
            "PYTHONPATH", "VIRTUAL_ENV",
        }
        env = {k: v for k, v in os.environ.items() if k.upper() in safe_keys}

        # Filter out obvious secret shapes from inherited env
        for key in list(env.keys()):
            k_upper = key.upper()
            if any(secret in k_upper for secret in ("KEY", "SECRET", "TOKEN", "PASSWORD", "AUTH")):
                env.pop(key, None)

        env.update(custom_env)
        return env
