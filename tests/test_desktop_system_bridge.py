"""Unit and bridge tests for ``system.*`` JSON-RPC endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.methods_system import (
    system_benchmark_hardware,
    system_configure_acceleration,
    system_export_diagnostics,
    system_get_golden_release_info,
    system_get_hardware_status,
    system_reset,
)


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def clean_system_state():
    _run(system_reset())
    yield
    _run(system_reset())


def test_system_hardware_status_and_config():
    status_res = _run(system_get_hardware_status())
    assert status_res["status"] == "healthy"
    assert "profile" in status_res
    profile = status_res["profile"]
    assert "active_backend" in profile
    assert profile["tokens_per_second"] > 0
    assert len(profile["devices"]) >= 1

    cfg_res = _run(
        system_configure_acceleration(
            {
                "speculative_streaming": True,
                "zero_latency_mode": True,
                "adaptive_compaction": True,
                "draft_buffer_size": 6,
            }
        )
    )
    assert cfg_res["status"] == "configured"
    assert cfg_res["profile"]["draft_buffer_size"] == 6


def test_system_benchmark_hardware():
    bench_res = _run(system_benchmark_hardware())
    assert bench_res["status"] == "completed"
    assert "benchmark" in bench_res
    bench = bench_res["benchmark"]
    assert bench["measured_latency_ms"] > 0
    assert bench["estimated_throughput_tps"] > 0


def test_system_golden_release_info():
    rel_info = _run(system_get_golden_release_info())
    assert rel_info["release_version"] == "5.4.0"
    assert rel_info["total_subsystems_count"] == 52
    assert rel_info["readiness_score"] == 100.0
    assert rel_info["is_golden_release"] is True
    assert len(rel_info["verified_subsystems"]) >= 8


def test_system_export_diagnostics():
    diag_res = _run(system_export_diagnostics())
    assert diag_res["status"] == "exported"
    assert "diagnostic_id" in diag_res
    assert "system_info" in diag_res
    assert diag_res["signature"].startswith("sha256_")


def test_system_invalid_params():
    with pytest.raises(BridgeError):
        _run(system_configure_acceleration({"draft_buffer_size": "invalid_string"}))


def test_system_reset():
    reset_res = _run(system_reset())
    assert reset_res["status"] == "reset"
