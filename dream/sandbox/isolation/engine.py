"""Isolated Execution Engine: Coordinates Seccomp filtering and WASM virtualization."""

from __future__ import annotations

import time
import uuid
from typing import Any

from dream.sandbox.isolation.seccomp_filter import SyscallFilterEngine
from dream.sandbox.isolation.types import (
    IsolationExecutionResult,
    IsolationLevel,
    SyscallPolicy,
)
from dream.sandbox.isolation.wasm_runtime import WasmMicroSandbox
from dream.sandbox.isolation.watchdog import ResourceWatchdog


class IsolatedExecutionEngine:
    """Unified coordinator for kernel syscall filtering, WASM sandbox, and resource watchdog."""

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
                exit_code=126,  # Command invoked cannot execute (policy denied)
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
            "## 🛡️ گزارش ایزولاسیون و امنیت سندباکس (Micro-Isolation & Seccomp)",
            f"- **تعداد کل اجراهای ایزوله:** {stats['total_executions']}",
            f"- **اجراهای موفق و امن:** {stats['successful_executions']}",
            f"- **تلاش‌های مسدودشده (Blocked Violations):** {stats['blocked_violations']}",
            f"- **میانگین زمان اجرا:** {stats['average_execution_ms']:.2f} ms",
            "",
            "### 🔑 وضعیت فیلتر Syscall:",
            "- سیس‌کال‌های ممنوع: `ptrace, mount, socket, execve, fork, clone, kill`",
            "- محیط مجازی: `WASM Memory-Confined Virtual Namespace`",
        ]
        return "\n".join(lines)

    def reset(self) -> None:
        """Reset execution history."""
        self._history.clear()
