"""Isolation *policy helpers* — analysis and reporting, not execution.

MASTER-P0 removed the host ``exec`` from this subsystem: it was a restricted
interpreter, not a sandbox, and it is not described as one any more. The static
:class:`~dream.sandbox.isolation.seccomp_filter.SyscallFilterEngine` audit and
the :class:`~dream.sandbox.isolation.watchdog.ResourceWatchdog` output clamp
remain, because they inspect and bound values without running them.

Execution is available only through :mod:`dream.security.codeexec`, which uses a
container. See ``docs/security/code-execution.md``.
"""

from __future__ import annotations

from dream.sandbox.isolation.engine import IsolatedExecutionEngine
from dream.sandbox.isolation.seccomp_filter import SyscallFilterEngine
from dream.sandbox.isolation.slash import handle_isolation_slash_command
from dream.sandbox.isolation.tools import (
    get_global_isolation_engine,
    get_isolation_tools,
    reset_global_isolation_engine,
    sandbox_export_security_report,
    sandbox_get_isolation_status,
    sandbox_isolate_execute,
    sandbox_reset_isolation,
    sandbox_wasm_execute,
)
from dream.sandbox.isolation.types import (
    IsolationExecutionResult,
    IsolationLevel,
    IsolationProfile,
    ResourceQuota,
    SyscallPolicy,
)
from dream.sandbox.isolation.wasm_runtime import WasmMicroSandbox
from dream.sandbox.isolation.watchdog import ResourceWatchdog

# Auto-register isolation toolset
try:
    from dream.tools.toolsets import Toolset, register_toolset

    register_toolset(
        Toolset(
            name="isolation",
            description=(
                "Kernel-level micro-isolation, Seccomp syscall filtering, "
                "and WASM virtualization."
            ),
            tools=[
                "sandbox_isolate_execute",
                "sandbox_wasm_execute",
                "sandbox_get_isolation_status",
                "sandbox_export_security_report",
                "sandbox_reset_isolation",
            ],
            metadata={"category": "isolation", "builtin": True},
        )
    )
except Exception:
    pass

__all__ = [
    "IsolatedExecutionEngine",
    "IsolationExecutionResult",
    "IsolationLevel",
    "IsolationProfile",
    "ResourceQuota",
    "ResourceWatchdog",
    "SyscallFilterEngine",
    "SyscallPolicy",
    "WasmMicroSandbox",
    "get_global_isolation_engine",
    "get_isolation_tools",
    "handle_isolation_slash_command",
    "reset_global_isolation_engine",
    "sandbox_export_security_report",
    "sandbox_get_isolation_status",
    "sandbox_isolate_execute",
    "sandbox_reset_isolation",
    "sandbox_wasm_execute",
]
