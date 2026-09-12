"""Unit tests for Kernel Micro-Isolation, Syscall Filtering & WASM Virtualization."""

from __future__ import annotations

import pytest

from dream.sandbox.isolation import (
    IsolatedExecutionEngine,
    ResourceQuota,
    ResourceWatchdog,
    SyscallFilterEngine,
    WasmMicroSandbox,
    get_isolation_tools,
    handle_isolation_slash_command,
    reset_global_isolation_engine,
    sandbox_export_security_report,
    sandbox_get_isolation_status,
    sandbox_isolate_execute,
    sandbox_wasm_execute,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_isolation_engine() -> None:
    reset_global_isolation_engine()
    yield
    reset_global_isolation_engine()


def test_toolset_includes_isolation() -> None:
    """Verify isolation toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("isolation")
    assert ts is not None
    assert "sandbox_isolate_execute" in ts.tools
    assert "sandbox_wasm_execute" in ts.tools
    assert "sandbox_get_isolation_status" in ts.tools
    assert "isolation" in BUILTIN_TOOLSETS


def test_syscall_filter_detects_prohibited_syscalls() -> None:
    """Verify static analysis catches raw socket, subprocess, os.system, and ctypes."""
    engine = SyscallFilterEngine()

    # 1. Unsafe: os.system
    is_safe, blocked, violations = engine.audit_code_safety(
        "import os\nos.system('rm -rf /')"
    )
    assert is_safe is False
    assert "execve" in blocked
    assert len(violations) > 0

    # 2. Unsafe: ctypes memory access
    is_safe_ctypes, _, _ = engine.audit_code_safety("import ctypes\nctypes.c_char_p()")
    assert is_safe_ctypes is False

    # 3. Safe computational code
    code_safe = "x = sum([i**2 for i in range(10)])\nprint(x)"
    is_safe_clean, blocked_clean, violations_clean = engine.audit_code_safety(code_safe)
    assert is_safe_clean is True
    assert len(blocked_clean) == 0
    assert len(violations_clean) == 0


def test_wasm_micro_sandbox_pure_computation() -> None:
    """Verify WASM virtual runtime executes deterministic mathematical code."""
    wasm = WasmMicroSandbox()

    code = """
import math
vals = [math.sqrt(i) for i in range(5)]
print(f"Computed: {len(vals)}")
"""
    exit_code, stdout, stderr, exec_ms = wasm.execute_pure_computation(code)
    assert exit_code == 0
    assert "Computed: 5" in stdout
    assert stderr == ""
    assert exec_ms >= 0.0


def test_resource_watchdog_output_clamping() -> None:
    """Verify watchdog truncates oversized output buffers."""
    quota = ResourceQuota(max_output_bytes=50)
    watchdog = ResourceWatchdog(quota=quota)

    huge_output = "A" * 500
    clamped = watchdog.clamp_output(huge_output)
    assert len(clamped.encode("utf-8")) < 500
    assert "Output Truncated by Resource Watchdog" in clamped


def test_isolated_execution_engine_full_flow() -> None:
    """Verify end-to-end execution rejection of hostile payloads and success of benign scripts."""
    engine = IsolatedExecutionEngine()

    # Rejected execution
    res_bad = engine.execute_isolated("import subprocess\nsubprocess.run(['ls'])")
    assert res_bad.success is False
    assert res_bad.exit_code == 126
    assert len(res_bad.security_violations) > 0

    # Successful execution
    res_good = engine.execute_isolated("total = sum(range(100))\nprint(f'Total: {total}')")
    assert res_good.success is True
    assert res_good.exit_code == 0
    assert "Total: 4950" in res_good.stdout

    stats = engine.get_security_stats()
    assert stats["total_executions"] == 2
    assert stats["successful_executions"] == 1
    assert stats["blocked_violations"] == 1


def test_isolation_tools_and_slash_commands() -> None:
    """Verify LLM tools and /isolate, /wasm, /sandbox_security slash commands."""
    tools = get_isolation_tools()
    assert len(tools) >= 4

    # Tool: isolate execute
    res_iso = sandbox_isolate_execute("print('Sandboxed Hello')")
    assert res_iso["success"] is True
    assert "Sandboxed Hello" in res_iso["result"]["stdout"]

    # Tool: wasm execute
    res_wasm = sandbox_wasm_execute("print(math.factorial(5))")
    assert res_wasm["success"] is True
    assert "120" in res_wasm["result"]["stdout"]

    # Tool: stats & report
    res_stats = sandbox_get_isolation_status()
    assert res_stats["success"] is True

    res_rep = sandbox_export_security_report()
    assert res_rep["success"] is True
    assert "Micro-Isolation & Seccomp" in res_rep["markdown_report"]

    # Slash: /isolate
    slash_iso = handle_isolation_slash_command("/isolate print(42)")
    assert "اجرای ایزوله موفق" in slash_iso

    # Slash: /isolate blocked
    slash_block = handle_isolation_slash_command("/isolate import socket")
    assert "نقض سیاست امنیتی" in slash_block

    # Slash: /wasm
    slash_w = handle_isolation_slash_command("/wasm print(math.pi)")
    assert "WASM" in slash_w

    # Slash: /sandbox_security
    slash_sec = handle_isolation_slash_command("/sandbox_security")
    assert "Micro-Isolation & Seccomp" in slash_sec

    # Slash: /sandbox_security reset
    slash_reset = handle_isolation_slash_command("/sandbox_security reset")
    assert "بازنشانی شد" in slash_reset
