"""Unit and bridge tests for ``sandbox.*`` JSON-RPC endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.methods_sandbox import (
    sandbox_analyze_data,
    sandbox_get_status,
    sandbox_list_artifacts,
    sandbox_list_backends,
    sandbox_reset,
    sandbox_run_code,
    sandbox_set_backend,
)


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def clean_sandbox_state():
    _run(sandbox_reset())
    yield
    _run(sandbox_reset())


def test_sandbox_run_code_success():
    res = _run(sandbox_run_code({"code": "x = 10 * 5\nprint(f'result={x}')"}))
    assert res["status"] == "success"
    assert "result=50" in res["result"]["stdout"]
    assert "x" in res["result"]["variables_updated"]


def test_sandbox_run_code_stateful():
    _run(sandbox_run_code({"code": "a = 42"}))
    res = _run(sandbox_run_code({"code": "b = a + 8\nprint(b)"}))
    assert res["status"] == "success"
    assert "50" in res["result"]["stdout"]


def test_sandbox_run_code_security_blocked():
    res = _run(sandbox_run_code({"code": "import os\nos.system('rm -rf /')"}))
    assert res["status"] == "blocked"
    assert res["result"]["status"] == "blocked"


def test_sandbox_analyze_data_csv():
    csv_data = "name,age,salary\nAlice,30,50000\nBob,35,60000\nCharlie,25,45000"
    res = _run(sandbox_analyze_data({"data_or_path": csv_data}))
    assert res["status"] == "success"
    assert res["summary"]["total_rows"] == 3
    assert "name" in res["summary"]["column_names"]
    assert "markdown_report" in res


def test_sandbox_status_and_artifacts():
    status = _run(sandbox_get_status())
    assert status["status"] == "healthy"
    assert "workspace_dir" in status

    artifacts = _run(sandbox_list_artifacts())
    assert artifacts["status"] == "success"
    assert "artifacts" in artifacts


def test_sandbox_list_and_set_backends():
    backends = _run(sandbox_list_backends())
    assert backends["status"] == "success"
    assert len(backends["backends"]) >= 1

    set_res = _run(sandbox_set_backend({"backend": "local"}))
    assert set_res["status"] == "success"
    assert set_res["active_backend"] == "local"


def test_sandbox_invalid_params():
    with pytest.raises(BridgeError):
        _run(sandbox_run_code({"code": ""}))

    with pytest.raises(BridgeError):
        _run(sandbox_analyze_data({"data_or_path": ""}))

    with pytest.raises(BridgeError):
        _run(sandbox_set_backend({"backend": "nonexistent_backend_xyz"}))
