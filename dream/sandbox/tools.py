"""LLM Tool bindings for Code Interpreter and Execution Sandbox."""

from __future__ import annotations

from typing import Any

from dream.sandbox.engine import SandboxEngine

_GLOBAL_SANDBOX_ENGINE: SandboxEngine | None = None


def get_global_sandbox_engine() -> SandboxEngine:
    """Get or initialize singleton SandboxEngine."""
    global _GLOBAL_SANDBOX_ENGINE
    if _GLOBAL_SANDBOX_ENGINE is None:
        _GLOBAL_SANDBOX_ENGINE = SandboxEngine()
    return _GLOBAL_SANDBOX_ENGINE


def reset_global_sandbox_engine() -> None:
    """Reset SandboxEngine singleton instance."""
    global _GLOBAL_SANDBOX_ENGINE
    _GLOBAL_SANDBOX_ENGINE = None


def sandbox_execute_python(
    code: str,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    """Execute Python code in the stateful sandbox, capturing output and generated files."""
    engine = get_global_sandbox_engine()
    res = engine.run_code(code, timeout_seconds=timeout_seconds)
    return {"success": res.status.value == "success", "result": res.to_dict()}


def sandbox_analyze_dataset(
    data_or_path: str,
) -> dict[str, Any]:
    """Profile tabular data (CSV/JSON), computing column distributions and statistics."""
    engine = get_global_sandbox_engine()
    try:
        summary, report_md = engine.analyze_data(data_or_path)
        return {
            "success": True,
            "summary": summary.to_dict(),
            "markdown_report": report_md,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def sandbox_reset_session() -> dict[str, Any]:
    """Reset the sandbox stateful namespace and purge local artifacts."""
    engine = get_global_sandbox_engine()
    engine.reset()
    return {"success": True, "message": "\u0645\u062d\u06cc\u0637 \u0633\u0646\u062f\u0628\u0627\u06a9\u0633 \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."}


def sandbox_list_artifacts() -> dict[str, Any]:
    """List all charts, plots, and files produced during sandbox sessions."""
    engine = get_global_sandbox_engine()
    artifacts = engine.list_artifacts()
    return {"success": True, "artifacts": [a.to_dict() for a in artifacts]}


def sandbox_get_status() -> dict[str, Any]:
    """Get current status of sandbox execution environment."""
    engine = get_global_sandbox_engine()
    status = engine.get_status()
    return {"success": True, **status}


def get_sandbox_tools() -> list[Any]:
    """Return Sandbox tool functions for agent registration."""
    return [
        sandbox_execute_python,
        sandbox_analyze_dataset,
        sandbox_reset_session,
        sandbox_list_artifacts,
        sandbox_get_status,
    ]
