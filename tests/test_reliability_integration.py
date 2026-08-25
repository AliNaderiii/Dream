"""Integration seams: public API, bridge delay cap, package exports."""

from __future__ import annotations

import ast
from pathlib import Path

import dream.reliability as reliability
from dream.bridge import streams as bridge_streams
from dream.reliability import (
    CancelToken,
    Deadline,
    Degradation,
    StreamStalledError,
    Watchdog,
    clamp_delay,
)


def test_package_exports_the_owned_surface() -> None:
    names = {
        "CancelToken",
        "Deadline",
        "DeadlineExceeded",
        "Watchdog",
        "Budget",
        "BudgetExceeded",
        "BoundedBuffer",
        "ResourceSupervisor",
        "StreamStalledError",
        "Degradation",
        "connect_sqlite",
        "claim_delivery",
        "guarded_aiter",
        "clamp_delay",
        "adapt_agentmodes",
        "adapt_research_stop",
    }
    missing = [name for name in names if not hasattr(reliability, name)]
    assert missing == []


def test_bridge_reexports_stream_stalled_error() -> None:
    assert bridge_streams.StreamStalledError is StreamStalledError
    assert hasattr(bridge_streams, "stream_with_stall_guard")


def test_bridge_stream_chunks_clamps_delay() -> None:
    assert clamp_delay(1_000_000_000) == 2.0


def test_owned_modules_exist() -> None:
    root = Path(__file__).resolve().parents[1] / "dream" / "reliability"
    expected = {
        "__init__.py",
        "cancel.py",
        "deadline.py",
        "budget.py",
        "backpressure.py",
        "streams.py",
        "resource.py",
        "db.py",
    }
    present = {path.name for path in root.glob("*.py")}
    assert expected <= present


def test_reliability_tests_have_no_assert_inside_if() -> None:
    """M16 meta-gate: ``assert`` must not sit inside ``if`` in this suite."""
    folder = Path(__file__).resolve().parent
    offenders: list[str] = []
    for path in sorted(folder.glob("test_reliability*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            for child in ast.walk(node):
                if child is node:
                    continue
                # Nested If nodes are walked independently.
                if isinstance(child, ast.If):
                    continue
                if isinstance(child, ast.Assert):
                    # Only count asserts whose nearest If is this node.
                    pass
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                for stmt in list(node.body) + list(node.orelse):
                    if isinstance(stmt, ast.Assert):
                        offenders.append(f"{path.name}:{stmt.lineno}")
                    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                        continue
    assert offenders == []


def test_watchdog_context_manager_cancels_on_expiry() -> None:
    token = CancelToken(name="ctx")
    deadline = Deadline.after(0.1, owner="test", step="ctx")
    with Watchdog(deadline, token):
        token.wait(timeout=0.4)
    assert token.is_cancelled() is True


def test_degradation_snapshot_is_serialisable() -> None:
    ladder = Degradation()
    ladder.step_down("probe")
    snap = ladder.snapshot()
    assert snap["level"] == "reduced"
    assert "en" in snap["message"]
    assert "fa" in snap["message"]
