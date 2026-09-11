"""Singularity / Apptainer scientific and HPC container terminal backend."""

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


class SingularityTerminalBackend(BaseTerminalBackend):
    """Executes commands inside Singularity/Apptainer unprivileged secure containers."""

    def __init__(
        self,
        image_path: str = "dream_env.sif",
        apptainer_bin: str = "singularity",
        options: list[str] | None = None,
    ) -> None:
        super().__init__(TerminalBackendType.SINGULARITY)
        self.image_path = image_path
        self.apptainer_bin = apptainer_bin
        self.options = options or ["--contain", "--cleanenv"]

    def is_available(self) -> bool:
        """Check if singularity or apptainer CLI is installed."""
        return bool(shutil.which(self.apptainer_bin) or shutil.which("apptainer"))

    def health_check(self) -> BackendHealth:
        """Check Singularity daemon and CLI availability."""
        t0 = time.time()
        available = self.is_available()
        latency = (time.time() - t0) * 1000
        details = (
            f"Singularity/Apptainer runtime available (image: {self.image_path})"
            if available
            else "Singularity/Apptainer CLI not found on host PATH"
        )
        return BackendHealth(
            backend=self.backend_type,
            available=available,
            details=details,
            latency_ms=round(latency, 2),
            metadata={"image": self.image_path, "options": self.options},
        )

    def execute(self, request: CommandExecutionRequest) -> CommandExecutionResult:
        """Execute command inside Singularity container."""
        t0 = time.time()
        if not self.is_available():
            return CommandExecutionResult(
                command=request.command,
                returncode=-1,
                stdout="",
                stderr="Singularity runtime is not available on this host.",
                duration_ms=0.0,
                backend=self.backend_type,
                error_message="Runtime unavailable",
            )

        cmd = (
            [self.apptainer_bin, "exec"]
            + self.options
            + [self.image_path, "sh", "-c", request.command]
        )
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=request.timeout,
                cwd=request.cwd,
            )
            duration = (time.time() - t0) * 1000
            stdout_txt = proc.stdout
            is_trunc = False
            if len(stdout_txt) > request.max_output_bytes:
                stdout_txt = stdout_txt[: request.max_output_bytes]
                is_trunc = True

            return CommandExecutionResult(
                command=request.command,
                returncode=proc.returncode,
                stdout=stdout_txt,
                stderr=proc.stderr,
                duration_ms=round(duration, 2),
                backend=self.backend_type,
                is_truncated=is_trunc,
            )
        except subprocess.TimeoutExpired:
            return CommandExecutionResult(
                command=request.command,
                returncode=-1,
                stdout="",
                stderr=f"Command timed out after {request.timeout}s",
                duration_ms=request.timeout * 1000,
                backend=self.backend_type,
                timed_out=True,
                error_message="Execution timeout",
            )
        except Exception as exc:
            return CommandExecutionResult(
                command=request.command,
                returncode=-1,
                stdout="",
                stderr=str(exc),
                duration_ms=(time.time() - t0) * 1000,
                backend=self.backend_type,
                error_message=str(exc),
            )
