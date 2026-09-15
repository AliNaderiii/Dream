"""``sandbox.*`` JSON-RPC bridge methods.

Discovered automatically by :mod:`dream.bridge.extensions`.
Exposes the Isolated Code Execution Sandbox, Data Science Profiler, and Multi-Backend Terminal:

================================  ================================================
``sandbox.run_code``              Execute code in isolated sandbox (Python/JS/SQL/Bash)
``sandbox.analyze_data``          Profile tabular dataset and generate summary & markdown
``sandbox.list_artifacts``        List charts, plots, and files generated in sandbox
``sandbox.get_status``            Retrieve status, variables count, and workspace metrics
``sandbox.reset``                 Reset stateful session, variables, and local artifacts
``sandbox.list_backends``         List available execution backends (Docker, Local, SSH, etc.)
``sandbox.set_backend``           Set active terminal execution backend
================================  ================================================
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from dream.bridge.errors import INVALID_PARAMS, BridgeError, invalid_params
from dream.sandbox.tools import get_global_sandbox_engine
from dream.terminal.manager import TerminalManager
from dream.terminal.types import TerminalBackendType

logger = logging.getLogger("dream.bridge.sandbox")

__all__ = ["HANDLERS"]

_terminal_manager: TerminalManager | None = None


def _get_terminal_manager() -> TerminalManager:
    global _terminal_manager
    if _terminal_manager is None:
        _terminal_manager = TerminalManager(auto_bootstrap_all=False)
    return _terminal_manager


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if params is not None:
        if not isinstance(params, dict):
            raise BridgeError(INVALID_PARAMS, "params must be an object")
        merged.update(params)
    merged.update(kwargs)
    return merged


async def sandbox_run_code(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Execute code in isolated sandbox.

    Params: ``code`` (str, required), ``language`` (str), ``timeout_seconds`` (float).
    """
    data = _params(params, kwargs)
    code = data.get("code")
    if code is None or not isinstance(code, str) or not code.strip():
        raise invalid_params("code must be a non-empty string")

    timeout = data.get("timeout_seconds", 15.0)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise invalid_params("timeout_seconds must be a positive number")

    engine = get_global_sandbox_engine()
    result = await asyncio.to_thread(
        engine.run_code,
        code=code.strip(),
        timeout_seconds=float(timeout),
    )
    return {
        "status": result.status.value,
        "result": result.to_dict(),
    }


async def sandbox_analyze_data(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Profile tabular dataset and generate statistical analysis.

    Params: ``data_or_path`` (str, required).
    """
    data = _params(params, kwargs)
    data_or_path = data.get("data_or_path")
    if data_or_path is None or not isinstance(data_or_path, str) or not data_or_path.strip():
        raise invalid_params("data_or_path must be a non-empty string")

    engine = get_global_sandbox_engine()
    try:
        summary, report_md = await asyncio.to_thread(
            engine.analyze_data,
            data_or_path=data_or_path.strip(),
        )
        return {
            "status": "success",
            "summary": summary.to_dict(),
            "markdown_report": report_md,
        }
    except Exception as exc:
        raise invalid_params(f"failed to analyze dataset: {exc}") from exc


async def sandbox_list_artifacts(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """List charts, plots, and files generated in sandbox."""
    _params(params, kwargs)
    engine = get_global_sandbox_engine()
    artifacts = await asyncio.to_thread(engine.list_artifacts)
    return {
        "status": "success",
        "artifacts": [a.to_dict() for a in artifacts],
        "count": len(artifacts),
    }


async def sandbox_get_status(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Retrieve status, variables count, and workspace metrics."""
    _params(params, kwargs)
    engine = get_global_sandbox_engine()
    status = await asyncio.to_thread(engine.get_status)
    return {
        "status": "healthy",
        **status,
    }


async def sandbox_reset(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Reset stateful session, variables, and local artifacts."""
    _params(params, kwargs)
    engine = get_global_sandbox_engine()
    await asyncio.to_thread(engine.reset)
    return {
        "status": "reset",
        "message": "Sandbox environment reset successfully.",
    }


async def sandbox_list_backends(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """List available execution backends."""
    _params(params, kwargs)
    tm = _get_terminal_manager()
    backends = await asyncio.to_thread(tm.list_backends)
    return {
        "status": "success",
        "backends": backends,
        "active_backend": tm.active_backend_type.value,
    }


async def sandbox_set_backend(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Set active terminal execution backend.

    Params: ``backend`` (str, required).
    """
    data = _params(params, kwargs)
    backend_str = data.get("backend")
    if backend_str is None or not isinstance(backend_str, str) or not backend_str.strip():
        raise invalid_params("backend must be a non-empty string")

    tm = _get_terminal_manager()
    try:
        b_type = TerminalBackendType(backend_str.strip().lower())
    except ValueError:
        raise invalid_params(f"unknown backend type: {backend_str}") from None

    success = await asyncio.to_thread(tm.set_active_backend, b_type)
    if not success:
        raise invalid_params(f"backend '{backend_str}' is not registered or unavailable")

    return {
        "status": "success",
        "active_backend": b_type.value,
    }


HANDLERS: dict[str, Any] = {
    "sandbox.run_code": sandbox_run_code,
    "sandbox.analyze_data": sandbox_analyze_data,
    "sandbox.list_artifacts": sandbox_list_artifacts,
    "sandbox.get_status": sandbox_get_status,
    "sandbox.reset": sandbox_reset,
    "sandbox.list_backends": sandbox_list_backends,
    "sandbox.set_backend": sandbox_set_backend,
}
