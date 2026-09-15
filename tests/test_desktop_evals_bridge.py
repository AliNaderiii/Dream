"""Unit and bridge tests for ``evals.*`` JSON-RPC endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.methods_evals import (
    evals_compare_hermes,
    evals_distill_dpo,
    evals_evolve_generation,
    evals_get_evolution_status,
    evals_list_suites,
    evals_reset,
    evals_run_suite,
)


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def clean_evals_state():
    _run(evals_reset())
    yield
    _run(evals_reset())


def test_evals_list_and_run_suites():
    suites_res = _run(evals_list_suites())
    assert suites_res["status"] == "success"
    assert suites_res["total_suites"] >= 4

    # Run Persian core suite
    run_res = _run(evals_run_suite({"suite_id": "persian_core"}))
    assert run_res["status"] == "completed"
    assert "report" in run_res
    report = run_res["report"]
    assert report["suite_id"] == "persian_core"
    assert report["overall_pass_rate"] >= 0.8
    assert len(report["results"]) >= 3


def test_evals_compare_hermes():
    res = _run(evals_compare_hermes())
    assert res["status"] == "completed"
    assert res["overall_winner"] == "Dream"
    assert res["dream_composite_score"] > res["hermes_composite_score"]
    assert res["dream_composite_score"] > res["openclaw_composite_score"]
    assert len(res["dimensions"]) == 6
    assert res["win_rate_percentage"] == 100.0


def test_evals_distill_dpo():
    dpo_res = _run(evals_distill_dpo({"count": 3}))
    assert dpo_res["status"] == "distilled"
    assert dpo_res["total_pairs"] == 3
    assert dpo_res["export_format"] == "huggingface_dpo_jsonl"
    for pair in dpo_res["pairs"]:
        assert "prompt" in pair
        assert "chosen" in pair
        assert "rejected" in pair
        assert pair["reward_delta"] > 0.0


def test_evals_evolution_and_status():
    status_res = _run(evals_get_evolution_status())
    assert status_res["status"] == "healthy"
    assert status_res["total_strategies"] >= 3
    assert len(status_res["leaderboard"]) >= 3

    evolve_res = _run(evals_evolve_generation({"rounds": 2}))
    assert evolve_res["status"] == "evolved"
    assert "top_strategy" in evolve_res
    assert len(evolve_res["leaderboard"]) >= 3


def test_evals_invalid_params():
    with pytest.raises(BridgeError):
        _run(evals_run_suite({"suite_id": ""}))

    with pytest.raises(BridgeError):
        _run(evals_run_suite({"suite_id": "nonexistent_suite_xyz"}))


def test_evals_reset():
    reset_res = _run(evals_reset())
    assert reset_res["status"] == "reset"
