"""Docker Container Sandboxed execution backend."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from dream.terminal.backends.base import BaseTerminalBackend
from dream.terminal.types import (
    BackendHealth,
    CommandExecutionRequest,
    CommandExecutionResult,
    TerminalBackendType,
)


class DockerSandboxBackend(BaseTerminalBackend):
    """Executes commands inside a hardened, isolated Docker container."""

    def __init__(
        self,
        image: str = "python:3.11-slim",
        network_mode: str = "none",
        memory_limit: str = "512m",
        cpu_limit: str = "1.0",
        pids_limit: int = 64,
        read_only_rootfs: bool = True,
        workspace_mount: str | None = None,
    ) -> None:
        super().__init__(TerminalBackendType.DOCKER)
        self.image = image
        self.network_mode = network_mode
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.pids_limit = pids_limit
        self.read_only_rootfs = read_only_rootfs
        self.workspace_mount = workspace_mount or str(Path.cwd())

    def is_available(self) -> bool:
        """Check if docker binary is on PATH and daemon responds."""
        docker_bin = shutil.which("docker")
        if not docker_bin:
            return False
        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=3.0,
            )
            return res.returncode == 0
        except Exception:
            return False

    def health_check(self) -> BackendHealth:
        """Verify Docker sandbox readiness and image availability."""
        start = time.perf_counter()
        if not shutil.which("docker"):
            return BackendHealth(
                backend=self.backend_type,
                available=False,
                details="Docker CLI is not installed on host / ابزار داکر نصب نیست.",
                latency_ms=0.0,
            )

        try:
            res = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=5.0)
            duration_ms = (time.perf_counter() - start) * 1000
            if res.returncode == 0:
                return BackendHealth(
                    backend=self.backend_type,
                    available=True,
                    details=f"Docker sandbox ready (Image: {self.image})",
                    latency_ms=duration_ms,
                    metadata={"image": self.image, "network": self.network_mode},
                )
            return BackendHealth(
                backend=self.backend_type,
                available=False,
                details="Docker daemon is not running / سرویس داکر در حال اجرا نیست.",
                latency_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            return BackendHealth(
                backend=self.backend_type,
                available=False,
                details=f"Docker health check failed: {exc}",
                latency_ms=duration_ms,
            )

    def execute(self, request: CommandExecutionRequest) -> CommandExecutionResult:
        """Execute command in an ephemeral, resource-bounded Docker sandbox."""
        start_time = time.perf_counter()

        if not self.is_available():
            duration_ms = (time.perf_counter() - start_time) * 1000
            err = (
                "داکر در دسترس نیست؛ اجرای ایزوله امکان‌پذیر نمی‌باشد. / "
                "Docker sandbox is unavailable."
            )
            return CommandExecutionResult(
                command=request.command,
                returncode=-1,
                stdout="",
                stderr=err,
                duration_ms=duration_ms,
                backend=self.backend_type,
                error_message=err,
            )

        # Construct Docker CLI arguments
        docker_args = [
            "docker", "run", "--rm", "-i",
            f"--network={self.network_mode}",
            f"--memory={self.memory_limit}",
            f"--cpus={self.cpu_limit}",
            f"--pids-limit={self.pids_limit}",
        ]

        if self.read_only_rootfs:
            docker_args.extend(["--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m"])

        # Mount workspace volume
        mount_path = request.cwd or self.workspace_mount
        docker_args.extend(["-v", f"{mount_path}:/workspace:rw", "-w", "/workspace"])

        # Inject environment variables
        for k, v in request.env.items():
            docker_args.extend(["-e", f"{k}={v}"])

        docker_args.extend([self.image, "sh", "-c", request.command])

        try:
            proc = subprocess.Popen(
                docker_args,
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
                error_message="Sandbox execution timed out" if timed_out else None,
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
