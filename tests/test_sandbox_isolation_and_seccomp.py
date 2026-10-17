"""Tests for the isolation *policy helpers* — audit and clamping, no execution.

MASTER-P0 rewrote this file. The previous version asserted that
``WasmMicroSandbox`` ran code (``"Computed: 5" in stdout``) and that
``IsolatedExecutionEngine`` reported ``success=True`` for a benign program. Both
described a host ``exec`` behind a hand-written ``__builtins__`` dictionary,
which is escapable and is not a sandbox. Those assertions are gone.

What survives is what is actually true and useful:

* :class:`SyscallFilterEngine` is a real static classifier;
* :class:`ResourceWatchdog` really clamps output;
* the execution surface fails closed and says it is unavailable;
* nothing in the subsystem has a host ``eval``/``exec``/``compile`` call site.
"""

from __future__ import annotations

import ast
from pathlib import Path

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

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def cleanup_isolation_engine() -> None:
    reset_global_isolation_engine()
    yield
    reset_global_isolation_engine()


def test_toolset_includes_isolation() -> None:
    ts = get_toolset("isolation")
    assert ts is not None
    assert "sandbox_isolate_execute" in ts.tools
    assert "sandbox_wasm_execute" in ts.tools
    assert "isolation" in BUILTIN_TOOLSETS


def test_isolation_tools_are_not_in_the_model_registry() -> None:
    """The toolset names a tool the model cannot reach: ``filter_tools``
    intersects with ``REGISTRY``, and none of these are registered there."""
    from dream.tools.base import REGISTRY

    for name in (
        "sandbox_isolate_execute",
        "sandbox_wasm_execute",
        "sandbox_get_isolation_status",
        "sandbox_export_security_report",
        "sandbox_reset_isolation",
    ):
        assert name not in REGISTRY


# --------------------------------------------------------------------------- #
# The static audit: real, and honestly labelled as static
# --------------------------------------------------------------------------- #


def test_syscall_filter_detects_prohibited_patterns() -> None:
    engine = SyscallFilterEngine()

    is_safe, blocked, violations = engine.audit_code_safety(
        "import os\nos.system('rm -rf /')"
    )
    assert is_safe is False
    assert "execve" in blocked
    assert violations

    is_safe_ctypes, _, _ = engine.audit_code_safety("import ctypes\nctypes.c_char_p()")
    assert is_safe_ctypes is False

    is_safe_clean, blocked_clean, violations_clean = engine.audit_code_safety(
        "x = sum([i**2 for i in range(10)])\nprint(x)"
    )
    assert is_safe_clean is True
    assert blocked_clean == []
    assert violations_clean == []


def test_the_audit_is_an_allowlist_shape_not_a_sandbox() -> None:
    """The classifier is a hint: it has no false-negative guarantee, and the
    engine must not report execution success just because it passed."""
    engine = IsolatedExecutionEngine()
    result = engine.execute_isolated("print(getattr(__builtins__, 'eval')('1+1'))")
    # Whatever the classifier decided, nothing ran and nothing is a success.
    assert result.success is False
    assert result.stdout == ""
    assert result.exit_code == 126


# --------------------------------------------------------------------------- #
# The watchdog: real boundary on output size
# --------------------------------------------------------------------------- #


def test_resource_watchdog_clamps_output() -> None:
    watchdog = ResourceWatchdog(quota=ResourceQuota(max_output_bytes=50))
    clamped = watchdog.clamp_output("A" * 500)
    assert len(clamped.encode("utf-8")) < 500
    assert "Output Truncated by Resource Watchdog" in clamped


def test_resource_watchdog_reports_the_duration_quota() -> None:
    watchdog = ResourceWatchdog(quota=ResourceQuota(max_cpu_time_sec=1.0))
    assert watchdog.check_duration_quota(500) is True
    assert watchdog.check_duration_quota(2_000) is False


# --------------------------------------------------------------------------- #
# Execution is gone and says so
# --------------------------------------------------------------------------- #


def test_wasm_micro_sandbox_is_unavailable_by_construction() -> None:
    sandbox = WasmMicroSandbox()
    assert sandbox.available is False

    exit_code, stdout, stderr, exec_ms = sandbox.execute_pure_computation(
        "import math\nprint(math.factorial(5))"
    )
    assert exit_code == 126
    assert stdout == ""
    assert "does not execute code" in stderr
    assert exec_ms == 0.0


def test_isolated_execution_engine_refuses_both_payloads() -> None:
    engine = IsolatedExecutionEngine()

    hostile = engine.execute_isolated("import subprocess\nsubprocess.run(['ls'])")
    assert hostile.success is False
    assert hostile.exit_code == 126
    assert hostile.security_violations  # the static audit flagged it

    benign = engine.execute_isolated("total = sum(range(100))\nprint(f'Total: {total}')")
    assert benign.success is False
    assert benign.exit_code == 126
    assert benign.security_violations == []
    assert "does not execute code" in benign.stderr
    assert "4950" not in benign.stdout

    stats = engine.get_security_stats()
    assert stats["total_executions"] == 2
    assert stats["successful_executions"] == 0
    assert stats["blocked_violations"] == 1
    assert stats["execution_available"] is False
    assert stats["static_audit_only"] is True


def test_no_fabricated_telemetry() -> None:
    """The old engine hard-coded ``memory_used_mb = 2.5``. It no longer claims
    a memory footprint it never measured."""
    engine = IsolatedExecutionEngine()
    result = engine.execute_isolated("print(1)")
    assert result.memory_used_mb == 0.0
    assert result.cpu_time_ms == 0.0


def test_report_states_that_execution_is_disabled() -> None:
    engine = IsolatedExecutionEngine()
    engine.execute_isolated("print(1)")
    report = engine.format_security_report()
    assert "Micro-Isolation & Seccomp" in report
    assert "غیرفعال" in report
    assert "codeexec" in report


# --------------------------------------------------------------------------- #
# Tools and slash commands report the truth
# --------------------------------------------------------------------------- #


def test_isolation_tools_fail_closed() -> None:
    tools = get_isolation_tools()
    assert len(tools) >= 4

    res_iso = sandbox_isolate_execute("print('Sandboxed Hello')")
    assert res_iso["success"] is False
    assert res_iso["available"] is False
    assert "Sandboxed Hello" not in res_iso["result"]["stdout"]

    res_wasm = sandbox_wasm_execute("print(math.factorial(5))")
    assert res_wasm["success"] is False
    assert res_wasm["available"] is False
    assert "120" not in res_wasm["result"]["stdout"]

    res_stats = sandbox_get_isolation_status()
    assert res_stats["success"] is True
    assert res_stats["stats"]["execution_available"] is False

    res_rep = sandbox_export_security_report()
    assert res_rep["success"] is True
    assert "Micro-Isolation & Seccomp" in res_rep["markdown_report"]


def test_slash_commands_do_not_claim_a_successful_run() -> None:
    slash_iso = handle_isolation_slash_command("/isolate print(42)")
    assert "42" not in slash_iso
    assert "fail-closed" in slash_iso

    slash_block = handle_isolation_slash_command("/isolate import socket")
    assert "نقض سیاست امنیتی" in slash_block

    slash_w = handle_isolation_slash_command("/wasm print(math.pi)")
    assert "WASM" in slash_w
    assert "fail-closed" in slash_w

    slash_sec = handle_isolation_slash_command("/sandbox_security")
    assert "Micro-Isolation & Seccomp" in slash_sec

    slash_reset = handle_isolation_slash_command("/sandbox_security reset")
    assert "بازنشانی شد" in slash_reset


# --------------------------------------------------------------------------- #
# Structural proof: no interpreter left in the package
# --------------------------------------------------------------------------- #


def test_no_eval_exec_or_compile_call_site_in_the_isolation_package() -> None:
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "dream" / "sandbox" / "isolation").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name in {"eval", "exec", "compile", "runpy"}:
                    offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], f"host interpreter call sites remain: {offenders}"
