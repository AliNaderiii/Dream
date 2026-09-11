"""Central Terminal Execution Manager and multi-backend orchestrator."""

from __future__ import annotations

import logging
import threading
from typing import Any

from dream.security.blocklist import scan as floor_scan
from dream.terminal.backends.base import BaseTerminalBackend
from dream.terminal.backends.daytona import DaytonaTerminalBackend
from dream.terminal.backends.docker import DockerTerminalBackend
from dream.terminal.backends.local import LocalTerminalBackend
from dream.terminal.backends.modal import ModalTerminalBackend
from dream.terminal.backends.singularity import SingularityTerminalBackend
from dream.terminal.backends.ssh import SSHTerminalBackend
from dream.terminal.backends.vercel import VercelTerminalBackend
from dream.terminal.types import (
    CommandExecutionRequest,
    CommandExecutionResult,
    TerminalBackendType,
)

logger = logging.getLogger(__name__)


class SecurityBlocklistViolation(Exception):
    """Raised when a command violates Layer-3 security floor policies."""
    pass


class TerminalManager:
    """Manages backend registry, security scanning, and command dispatch."""

    def __init__(
        self,
        default_backend: TerminalBackendType = TerminalBackendType.LOCAL,
        enable_security_scan: bool = True,
        auto_bootstrap_all: bool = True,
    ) -> None:
        self.active_backend_type = default_backend
        self.enable_security_scan = enable_security_scan
        self._lock = threading.RLock()
        self._backends: dict[TerminalBackendType, BaseTerminalBackend] = {}

        # Register default local backend
        self.register_backend(LocalTerminalBackend())

        if auto_bootstrap_all:
            self.register_backend(DockerTerminalBackend())
            self.register_backend(SSHTerminalBackend())
            self.register_backend(SingularityTerminalBackend())
            self.register_backend(ModalTerminalBackend())
            self.register_backend(DaytonaTerminalBackend())
            self.register_backend(VercelTerminalBackend())

    def register_backend(self, backend: BaseTerminalBackend) -> None:
        """Register a terminal backend in the pool."""
        with self._lock:
            self._backends[backend.backend_type] = backend
            logger.info(f"Registered terminal backend: {backend.backend_type.value}")

    def get_backend(
        self,
        backend_type: TerminalBackendType | None = None,
    ) -> BaseTerminalBackend | None:
        """Retrieve a registered backend by type or active default."""
        with self._lock:
            target = backend_type or self.active_backend_type
            return self._backends.get(target)

    def set_active_backend(self, backend_type: TerminalBackendType | str) -> bool:
        """Switch the default terminal backend."""
        with self._lock:
            if isinstance(backend_type, str):
                try:
                    backend_type = TerminalBackendType(backend_type.lower())
                except ValueError:
                    logger.error(f"Unknown terminal backend type: {backend_type}")
                    return False

            if backend_type not in self._backends:
                logger.warning(f"Backend {backend_type.value} is not registered.")
                return False

            self.active_backend_type = backend_type
            logger.info(f"Active terminal backend switched to: {backend_type.value}")
            return True

    def execute(
        self,
        command: str,
        backend_type: TerminalBackendType | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> CommandExecutionResult:
        """Execute command through security filter and active backend."""
        # 1. Layer-3 Security Blocklist Verification
        if self.enable_security_scan:
            finding = floor_scan(command)
            if finding:
                rule_id = finding.rule.rule_id if hasattr(finding, "rule") else "L3-BLOCK"
                name_en = (
                    finding.rule.name_en if hasattr(finding, "rule") else "destructive command"
                )
                err_msg = (
                    f"\u26d4 \u0627\u062c\u0631\u0627\u06cc "
                    f"\u062f\u0633\u062a\u0648\u0631 "
                    f"\u0628\u0647 \u062f\u0644\u06cc\u0644 "
                    f"\u0646\u0642\u0636 \u0642\u0648\u0627\u0646\u06cc\u0646 "
                    f"\u0627\u0645\u0646\u06cc\u062a\u06cc "
                    f"\u0645\u0633\u062f\u0648\u062f "
                    f"\u0634\u062f: {rule_id}\n"
                    f"Command blocked by security rule: {name_en}"
                )
                logger.warning(f"Terminal command blocked: {command} -> {rule_id}")
                return CommandExecutionResult(
                    command=command,
                    returncode=126,
                    stdout="",
                    stderr=err_msg,
                    duration_ms=0.0,
                    backend=backend_type or self.active_backend_type,
                    error_message=err_msg,
                )

        # 2. Select backend
        backend = self.get_backend(backend_type)
        if not backend:
            target_name = (backend_type or self.active_backend_type).value
            err_msg = f"Terminal backend '{target_name}' is not registered."
            return CommandExecutionResult(
                command=command,
                returncode=-1,
                stdout="",
                stderr=err_msg,
                duration_ms=0.0,
                backend=backend_type or self.active_backend_type,
                error_message=err_msg,
            )

        # 3. Dispatch execution
        req = CommandExecutionRequest(
            command=command,
            cwd=cwd,
            env=env or {},
            timeout=timeout,
            backend_type=backend.backend_type,
        )
        return backend.execute(req)

    def list_backends(self) -> list[dict[str, Any]]:
        """Return status and diagnostics for all registered backends."""
        with self._lock:
            results = []
            for b_type, backend in self._backends.items():
                health = backend.health_check()
                results.append({
                    "type": b_type.value,
                    "is_active": b_type == self.active_backend_type,
                    "available": health.available,
                    "details": health.details,
                    "latency_ms": health.latency_ms,
                    "metadata": health.metadata,
                })
            return results
