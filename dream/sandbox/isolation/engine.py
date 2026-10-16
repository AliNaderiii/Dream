"""Isolation policy coordinator — static audit plus a fail-closed execution refusal.

MASTER-P0: the execution step is gone. This engine used to ``exec`` the payload
on the host behind a hand-written builtins dictionary and then report
"WASM micro-runtime" telemetry (including a hard-coded ``memory_used_mb = 2.5``)
that described a boundary it did not have. It now runs the static audit — which
is real, and is *only* a hint — and then reports ``unavailable``. Nothing here
executes code. Real isolation: :mod:`dream.security.codeexec`.
"""

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

        # Step 2: refuse to execute. No host interpreter, no fabricated
        # telemetry: an unavailable result is the honest answer, and the static
        # audit above is a hint rather than a sandbox.
        del initial_globals, isolation_level, policy
        exit_code, stdout, stderr, _exec_ms = self.wasm.execute_pure_computation(code_str)
        clamped_stdout = self.watchdog.clamp_output(stdout)
        clamped_stderr = self.watchdog.clamp_output(stderr)
        total_duration_ms = (time.time() - start_time) * 1000

        result = IsolationExecutionResult(
            execution_id=exec_id,
            isolation_level=IsolationLevel.PROCESS_SECCOMP,
            policy=SyscallPolicy.STRICT_READONLY,
            exit_code=exit_code,
            stdout=clamped_stdout,
            stderr=clamped_stderr,
            syscalls_blocked=[],
            cpu_time_ms=0.0,
            memory_used_mb=0.0,
            security_violations=[],
            success=False,
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
            # Honesty fields: the caller must not read "0 successful" as an
            # error rate on a working sandbox.
            "execution_available": False,
            "static_audit_only": True,
        }

    def format_security_report(self) -> str:
        """Format security audit log and sandbox status into Markdown."""
        stats = self.get_security_stats()
        lines = [
            "## 🛡️ گزارش ایزولاسیون و امنیت سندباکس (Micro-Isolation & Seccomp)",
            f"- **تعداد کل بازرسی‌های ایزوله:** {stats['total_executions']}",
            f"- **اجراهای موفق و امن:** {stats['successful_executions']}",
            f"- **تلاش‌های مسدودشده (Blocked Violations):** {stats['blocked_violations']}",
            f"- **میانگین زمان بازرسی:** {stats['average_execution_ms']:.2f} ms",
            "",
            "- **اجرای کد در این زیرسیستم:** غیرفعال (fail-closed)",
            "- **دامنهٔ واقعی این ماژول:** فقط بازرسی ایستا و کران‌گذاری خروجی — یک",
            "  مرز امنیتی نیست و به‌عنوان سندباکس جا زده نمی‌شود.",
            "- **مسیر واقعی اجرا:** `dream.security.codeexec` → `DockerSandbox` (بدون شبکه،",
            "  `--cap-drop=ALL`، `--read-only`، ماونت فقط‌خواندنی/پوشهٔ اجرا).",
        ]
        return "\n".join(lines)

    def reset(self) -> None:
        """Reset execution history."""
        self._history.clear()
