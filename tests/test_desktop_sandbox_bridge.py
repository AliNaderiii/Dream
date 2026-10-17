"""Bridge-level tests for ``sandbox.*`` JSON-RPC endpoints.

MASTER-P0 rewrote this file. It used to import ``sandbox_run_code`` from
:mod:`dream.bridge.methods_sandbox` and assert the host ``eval``/``exec``
interpreter's output. That method no longer exists in the extension module —
it was collapsed into the single container handler — so the assertions here now
describe the *contract* (``dream.security.codeexec``) rather than an interpreter
that Dream no longer has.

The deep validation matrix lives in ``tests/test_code_execution_contract.py`` and
the route-containment proofs in ``tests/test_code_execution_route_containment.py``.
This file keeps the "does the bridge still answer the desktop view correctly"
level of coverage, including the browser-preview case where there is no core.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.methods import BridgeMethods
from dream.bridge.methods_sandbox import (
    HANDLERS as SANDBOX_HANDLERS,
)
from dream.bridge.methods_sandbox import (
    sandbox_analyze_data,
    sandbox_get_status,
    sandbox_list_artifacts,
    sandbox_list_backends,
    sandbox_reset,
    sandbox_set_backend,
)
from dream.security import codeexec
from dream.security.codeexec import CodeExecutionRuntime


class StubResult:
    def __init__(self, **kwargs: Any) -> None:
        self.stdout = kwargs.get("stdout", "")
        self.stderr = kwargs.get("stderr", "")
        self.return_code = kwargs.get("return_code", 0)
        self.timed_out = kwargs.get("timed_out", False)
        self.cancelled = kwargs.get("cancelled", False)
        self.output_files: list[str] = []
        self.container_name = ""


class StubRunner:
    """A container double: available, records calls, returns one fixed result."""

    def __init__(self, result: StubResult | None = None, *, available: bool = True) -> None:
        self.result = result or StubResult(stdout="result=50\n")
        self.available = available
        self.calls: list[dict[str, Any]] = []

    async def check_available(self) -> bool:
        return self.available

    async def run_code(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.result

    async def force_remove_container(self, container_name: str) -> bool:
        return True


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CodeExecutionRuntime:
    monkeypatch.setenv("DREAM_SANDBOX_ROOT", str(tmp_path / "sandbox"))
    runner = StubRunner()
    rt = CodeExecutionRuntime(runner, root=tmp_path / "sandbox")
    codeexec.reset_code_execution_runtime(rt)
    yield rt
    codeexec.reset_code_execution_runtime()


@pytest.fixture
def bridge(tmp_path: Path) -> BridgeMethods:
    return BridgeMethods(
        sessions_path=str(tmp_path / "s.json"),
        projects_path=str(tmp_path / "p.json"),
        disabled_skills_path=str(tmp_path / "d.json"),
        providers_path=str(tmp_path / "pr.json"),
        provenance_dir=str(tmp_path / "prov"),
        mcp_config_path=str(tmp_path / "m.json"),
        acp_config_path=str(tmp_path / "a.json"),
    )


# --------------------------------------------------------------------------- #
# Registration: the method the desktop actually calls
# --------------------------------------------------------------------------- #


def test_desktop_method_is_registered_on_the_bridge(bridge: BridgeMethods) -> None:
    for method in (
        "sandbox.run_code",
        "sandbox.cancel",
        "sandbox.status",
        "sandbox.get_status",
        "sandbox.reset",
        "sandbox.list_artifacts",
    ):
        assert method in bridge.handlers, method
        assert callable(bridge.handlers[method])


def test_extension_module_does_not_shadow_run_code() -> None:
    assert "sandbox.run_code" not in SANDBOX_HANDLERS


# --------------------------------------------------------------------------- #
# The success contract the Code view renders
# --------------------------------------------------------------------------- #


def test_run_code_success_envelope(runtime: CodeExecutionRuntime, bridge: BridgeMethods) -> None:
    payload = _run(bridge.sandbox_run_code({"code": "x = 10 * 5\nprint(f'result={x}')"}))

    assert payload["status"] == "success"
    assert payload["result"]["status"] == "success"
    assert "result=50" in payload["result"]["stdout"]
    assert payload["result"]["exit_code"] == 0
    # Container runs are stateless: the field is present and honestly empty.
    assert payload["result"]["variables_updated"] == []


def test_run_code_carries_the_isolation_profile(
    runtime: CodeExecutionRuntime, bridge: BridgeMethods
) -> None:
    payload = _run(bridge.sandbox_run_code({"code": "print(1)"}))
    isolation = payload["result"]["isolation"]
    assert isolation["network"] == "none"
    assert isolation["rootfs"] == "read-only"
    assert isolation["privileged"] is False
    assert isolation["capabilities"] == "drop-all"


def test_run_code_rejects_empty_payload(
    runtime: CodeExecutionRuntime, bridge: BridgeMethods
) -> None:
    payload = _run(bridge.sandbox_run_code({"code": "   "}))
    assert payload["status"] == "denied"
    assert payload["result"]["error_message"]


def test_run_code_rejects_a_removed_boundary_field(
    runtime: CodeExecutionRuntime, bridge: BridgeMethods
) -> None:
    payload = _run(bridge.sandbox_run_code({"code": "print(1)", "network_enabled": True}))
    assert payload["status"] == "denied"
    assert payload["result"]["error"]["code"] == "removed_field"


def test_run_code_rejects_non_object_params(
    runtime: CodeExecutionRuntime, bridge: BridgeMethods
) -> None:
    with pytest.raises(BridgeError):
        _run(bridge.sandbox_run_code("print(1)"))


def test_run_code_is_unavailable_without_a_runner(
    tmp_path: Path, bridge: BridgeMethods
) -> None:
    rt = CodeExecutionRuntime(None, root=tmp_path / "sandbox", sandbox_factory=lambda: None)
    codeexec.reset_code_execution_runtime(rt)
    payload = _run(bridge.sandbox_run_code({"code": "print(1)"}))
    assert payload["status"] == "unavailable"
    assert payload["result"]["stdout"] == ""
    codeexec.reset_code_execution_runtime()


def test_cancel_of_an_unknown_execution_is_not_an_error(
    runtime: CodeExecutionRuntime, bridge: BridgeMethods
) -> None:
    result = _run(bridge.sandbox_cancel({"execution_id": "exe-does-not-exist"}))
    assert result["status"] == "not_running"


# --------------------------------------------------------------------------- #
# Dataset analysis, status, artifacts, backends (unchanged surfaces)
# --------------------------------------------------------------------------- #


def test_sandbox_analyze_data_csv() -> None:
    csv_data = "name,age,salary\nAlice,30,50000\nBob,35,60000\nCharlie,25,45000"
    res = _run(sandbox_analyze_data({"data_or_path": csv_data}))
    assert res["status"] == "success"
    assert res["summary"]["total_rows"] == 3
    assert "name" in res["summary"]["column_names"]
    assert "markdown_report" in res


def test_status_and_artifacts_reflect_the_real_runtime(
    runtime: CodeExecutionRuntime,
) -> None:
    _run(runtime.run(codeexec.CodeExecutionRequest.from_params(
        {"code": "print(1)"}, sandbox_root=runtime.root
    )))

    status = _run(sandbox_get_status())
    assert status["status"] == "healthy"
    assert status["backend"] == "docker"
    assert status["sandbox_root"]

    artifacts = _run(sandbox_list_artifacts())
    assert artifacts["status"] == "success"
    assert artifacts["count"] == 0


def test_reset_answers_with_the_contract(runtime: CodeExecutionRuntime) -> None:
    res = _run(sandbox_reset())
    assert res["status"] == "reset"
    assert res["sandbox_root"]


def test_list_and_set_backends() -> None:
    backends = _run(sandbox_list_backends())
    assert backends["status"] == "success"
    assert len(backends["backends"]) >= 1

    set_res = _run(sandbox_set_backend({"backend": "local"}))
    assert set_res["status"] == "success"
    assert set_res["active_backend"] == "local"
