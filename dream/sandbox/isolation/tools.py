"""Tool bindings for the static isolation audit (no execution — MASTER-P0).

Every ``*_execute`` binding here returns ``available: False`` and a bilingual
refusal. The static :class:`~dream.sandbox.isolation.seccomp_filter.SyscallFilterEngine`
audit still runs and its verdict is reported, so the tools remain useful as a
*pre-flight hint*; they are not a sandbox and do not run code.
"""

from __future__ import annotations

from typing import Any

from dream.sandbox.isolation.engine import IsolatedExecutionEngine
from dream.sandbox.isolation.types import IsolationLevel, SyscallPolicy

_GLOBAL_ISOLATION_ENGINE: IsolatedExecutionEngine | None = None


def get_global_isolation_engine() -> IsolatedExecutionEngine:
    """Get or initialize singleton IsolatedExecutionEngine."""
    global _GLOBAL_ISOLATION_ENGINE
    if _GLOBAL_ISOLATION_ENGINE is None:
        _GLOBAL_ISOLATION_ENGINE = IsolatedExecutionEngine()
    return _GLOBAL_ISOLATION_ENGINE


def reset_global_isolation_engine() -> None:
    """Reset singleton IsolatedExecutionEngine."""
    global _GLOBAL_ISOLATION_ENGINE
    _GLOBAL_ISOLATION_ENGINE = None


def sandbox_isolate_execute(
    code: str,
    language: str = "python",
    policy: str = "strict_readonly",
) -> dict[str, Any]:
    """Audit *code* statically. Never executes it.

    ``available`` is always ``False``: this subsystem has no execution backend.
    ``blocked`` distinguishes a static-policy hit from the plain refusal so a
    caller can tell "your payload looked dangerous" apart from "nothing here
    runs code".
    """
    del language
    engine = get_global_isolation_engine()
    try:
        p_enum = SyscallPolicy(policy.lower())
    except ValueError:
        p_enum = SyscallPolicy.STRICT_READONLY

    result = engine.execute_isolated(code, policy=p_enum)
    return {
        "success": False,
        "available": False,
        "blocked": bool(result.security_violations),
        "result": result.to_dict(),
    }


def sandbox_wasm_execute(
    expression_or_code: str,
) -> dict[str, Any]:
    """Audit *expression_or_code* statically. Never executes it."""
    engine = get_global_isolation_engine()
    result = engine.execute_isolated(
        expression_or_code,
        isolation_level=IsolationLevel.WASM_SANDBOX,
        policy=SyscallPolicy.COMPUTE_ONLY,
    )
    return {
        "success": False,
        "available": False,
        "blocked": bool(result.security_violations),
        "result": result.to_dict(),
    }


def sandbox_get_isolation_status() -> dict[str, Any]:
    """Retrieve aggregate isolation execution statistics and blocked violations count."""
    engine = get_global_isolation_engine()
    stats = engine.get_security_stats()
    return {"success": True, "stats": stats}


def sandbox_export_security_report() -> dict[str, Any]:
    """Export formatted Markdown report of sandbox isolation and security audit."""
    engine = get_global_isolation_engine()
    report_md = engine.format_security_report()
    return {"success": True, "markdown_report": report_md}


def sandbox_reset_isolation() -> dict[str, Any]:
    """Reset sandbox isolation logs and execution metrics."""
    engine = get_global_isolation_engine()
    engine.reset()
    return {"success": True, "message": "تاریخچه اجراهای ایزوله بازنشانی شد."}


def get_isolation_tools() -> list[Any]:
    """Return isolation tool functions for agent registration."""
    return [
        sandbox_isolate_execute,
        sandbox_wasm_execute,
        sandbox_get_isolation_status,
        sandbox_export_security_report,
        sandbox_reset_isolation,
    ]
