"""Remote SSH Execution backend."""

from __future__ import annotations

import shutil
import subprocess
import time

from dream.terminal.backends.base import BaseTerminalBackend
from dream.terminal.types import (
    BackendHealth,
    CommandExecutionRequest,
    CommandExecutionResult,
    TerminalBackendType,
)


class SSHRemoteBackend(BaseTerminalBackend):
    """Executes commands on a remote host via secure SSH tunnel."""

    def __init__(
        self,
        host: str,
        port: int = 22,
        user: str | None = None,
        key_path: str | None = None,
        remote_cwd: str | None = None,
    ) -> None:
        super().__init__(TerminalBackendType.SSH)
        self.host = host
        self.port = port
        self.user = user
        self.key_path = key_path
        self.remote_cwd = remote_cwd

    def is_available(self) -> bool:
        """Check if ssh executable is present on local host."""
        return shutil.which("ssh") is not None

    def health_check(self) -> BackendHealth:
        """Verify SSH connection to remote host."""
        start = time.perf_counter()
        if not self.is_available():
            return BackendHealth(
                backend=self.backend_type,
                available=False,
                details="SSH client is not installed on local host.",
                latency_ms=0.0,
            )

        cmd = self._build_ssh_cmd("echo ssh_ok", timeout=5.0)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=6.0)
            duration_ms = (time.perf_counter() - start) * 1000
            ok = res.returncode == 0 and "ssh_ok" in res.stdout
            detail_msg = (
                f"SSH remote ready ({self.host}:{self.port})"
                if ok
                else f"SSH failed: {res.stderr.strip()}"
            )
            return BackendHealth(
                backend=self.backend_type,
                available=ok,
                details=detail_msg,
                latency_ms=duration_ms,
                metadata={"host": self.host, "port": self.port, "user": self.user},
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            return BackendHealth(
                backend=self.backend_type,
                available=False,
                details=f"SSH connection error: {exc}",
                latency_ms=duration_ms,
            )

    def execute(self, request: CommandExecutionRequest) -> CommandExecutionResult:
        """Execute command remotely over SSH."""
        start_time = time.perf_counter()

        # Format remote command string with env and directory
        remote_cmd_parts = []
        target_dir = request.cwd or self.remote_cwd
        if target_dir:
            remote_cmd_parts.append(f"cd {target_dir}")

        for k, v in request.env.items():
            remote_cmd_parts.append(f"export {k}='{v}'")

        remote_cmd_parts.append(request.command)
        remote_command = " && ".join(remote_cmd_parts)

        ssh_args = self._build_ssh_cmd(remote_command, timeout=request.timeout)

        try:
            proc = subprocess.Popen(
                ssh_args,
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
            max_bytes = request.max_output_bytes
            is_truncated = False
            if len(stdout_raw) > max_bytes:
                stdout_raw = stdout_raw[:max_bytes] + "\n... [Output Truncated]"
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
                error_message="SSH command timed out" if timed_out else None,
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
                error_message=str(exc),
            )

    def _build_ssh_cmd(self, command: str, timeout: float = 30.0) -> list[str]:
        """Construct SSH invocation argument list."""
        args = [
            "ssh",
            "-p", str(self.port),
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={int(min(timeout, 10))}",
        ]
        if self.key_path:
            args.extend(["-i", self.key_path])

        target = f"{self.user}@{self.host}" if self.user else self.host
        args.extend([target, command])
        return args
