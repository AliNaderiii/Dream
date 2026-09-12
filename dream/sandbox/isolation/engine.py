"""Isolated Execution Engine: Coordinates Seccomp filtering, WASM virtualization, and watchdog."""

from __future__ import annotations

import time
from typing import Any
import uuid

from dream.sandbox.isolation.seccomp_filter import SyscallFilterEngine
from dream.sandbox.isolation.types import (
    IsolationExecutionResult,
    IsolationLevel,
    ResourceQuota,
    SyscallPolicy,
)
from dream.sandbox.isolation.wasm_runtime import WasmMicroSandbox
from dream.sandbox.isolation.watchdog import ResourceWatchdog


class IsolatedExecutionEngine:
    """Unified coordinator for kernel syscall filtering, WASM micro-sandbox, and resource watchdog."""

    def __init__(
        self,
        filter_engine: SyscallFilterEngine | None = None,
        wasm_sandbox: WasmMicroSandbox | None = None,
        watchdog: ResourceWatchdog | None = None,
    ) -> None:
        self.filter = filter_engine or SyscallFilterEngine()
        self.wasm = wasm_sandbox or WasmMicroSandbox()
        self.watchdog = watchdog or ResourceWatchdog()

        self._history: list[IsolationExecutionResult] = []

    def execute_isolated(
        self,
        code_str: str,
        isolation_level: IsolationLevel = IsolationLevel.WASM_SANDBOX,
        policy: SyscallPolicy = SyscallPolicy.STRICT_READONLY,
        initial_globals: dict[str, Any] | None = None,
    ) -> IsolationExecutionResult:
        """Run code through Seccomp audit and isolated WASM runtime."""
        start_time = time.time()
        exec_id = f"iso-{uuid.uuid4().hex[:6]}"

        # Step 1: Syscall Safety Audit
        is_safe, blocked_syscalls, violations = self.filter.audit_code_safety(code_str)

        if not is_safe:
            duration_ms = (time.time() - start_time) * 1000
            result = IsolationExecutionResult(
                execution_id=exec_id,
                isolation_level=isolation_level,
                policy=policy,
                exit_code=126,  # Command invoked cannot execute (permission/policy denied)
                stdout="",
                stderr="\n".join(violations),
                syscalls_blocked=blocked_syscalls,
                security_violations=violations,
                success=False,
                duration_ms=duration_ms,
            )
            self._history.append(result)
            return result

        # Step 2: Execute in WASM micro-runtime
        exit_code, stdout, stderr, exec_ms = self.wasm.execute_pure_computation(
            code_str,
            initial_globals=initial_globals,
        )

        # Step 3: Clamp Output via Watchdog
        clamped_stdout = self.watchdog.clamp_output(stdout)
        clamped_stderr = self.watchdog.clamp_output(stderr)
        total_duration_ms = (time.time() - start_time) * 1000

        result = IsolationExecutionResult(
            execution_id=exec_id,
            isolation_level=isolation_level,
            policy=policy,
            exit_code=exit_code,
            stdout=clamped_stdout,
            stderr=clamped_stderr,
            syscalls_blocked=[],
            cpu_time_ms=exec_ms,
            memory_used_mb=2.5,  # Estimated baseline micro-runtime memory footprint
            security_violations=[],
            success=(exit_code == 0),
            duration_ms=total_duration_ms,
        )
        self._history.append(result)
        return result

    def get_security_stats(self) -> dict[str, Any]:
        """Aggregate execution security metrics and violation stats."""
        total = len(self._history)
        if total == 0:
            return {
                "total_executions": 0,
                "successful_executions": 0,
                "blocked_violations": 0,
                "average_execution_ms": 0.0,
            }

        successful = sum(1 for r in self._history if r.success)
        violations = sum(1 for r in self._history if len(r.security_violations) > 0)
        avg_ms = sum(r.duration_ms for r in self._history) / total

        return {
            "total_executions": total,
            "successful_executions": successful,
            "blocked_violations": violations,
            "average_execution_ms": round(avg_ms, 2),
        }

    def format_security_report(self) -> str:
        """Format security audit log and sandbox status into Markdown."""
        stats = self.get_security_stats()
        lines = [
            "## \U0001f6e1\ufe0f \u06af\u0632\u0627\u0631\u0634 \u0627\u06cc\u0632\u0648\u0644\u0627\u0633\u06cc\u0648\u0646 \u0648 \u0627\u0645\u0646\u06cc\u062a \u0633\u0646\u062f\u0628\u0627\u06a9\u0633 (Micro-Isolation & Seccomp)",
            f"- **\u062a\u0639\u062f\u0627\u062f \u06a9\u0644 \u0627\u062c\u0631\u0627\u0647\u0627\u06cc \u0627\u06cc\u0632\u0648\u0644\u0647:** {stats['total_executions']}",
            f"- **\u0627\u062c\u0631\u0627\u0647\u0627\u06cc \u0645\u0648\u0641\u0642 \u0648 \u0627\u0645\u0646:** {stats['successful_executions']}",
            f"- **\u062a\u0644\u0627\u0634\u200c\u0647\u0627\u06cc \u0645\u0633\u062f\u0648\u062f\u0634\u062f\u0647 (Blocked Violations):** {stats['blocked_violations']}",
            f"- **\u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 \u0632\u0645\u0627\u0646 \u0627\u062c\u0631\u0627:** {stats['average_execution_ms']:.2f} ms",
            "",
            "### \U0001f510 \u0648\u0636\u0639\u06cc\u062a \u0641\u06cc\u0644\u062a\u0631 Syscall:",
            "- \u0633\u06cc\u0633\u200c\u06a9\u0627\u0644\u200c\u0647\u0627\u06cc \u0645\u0645\u0646\u0648\u0639: `ptrace, mount, socket, execve, fork, clone, kill`",
            "- \u0645\u062d\u06cc\u0637 \u0645\u062c\u0627\u0632\u06cc: `WASM Memory-Confined Virtual Namespace`",
        ]
        return "\n".join(lines)

    def reset(self) -> None:
        """Reset execution history."""
        self._history.clear()
