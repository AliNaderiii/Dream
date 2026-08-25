"""Bridge coverage for the ``research.*`` RPC family (P1).

Asserts three things: the handlers are discovered through the P0 extension
seam (``dream/bridge/methods.py`` is never touched), every expected failure
maps to ``INVALID_PARAMS``, and the streaming handler emits progress chunks
plus a final summary through the real dispatcher shape.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dream.agent import EchoBackend
from dream.bridge.errors import INVALID_PARAMS, BridgeError
from dream.bridge.methods import BridgeMethods
from dream.bridge.streams import Stream
from dream.research import ResearchEngine, SessionStore

pytest.importorskip("pandas", reason="the research engine needs pandas in the sandbox")

import dream.bridge.methods_research as research_rpc  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def space(tmp_path: Path) -> Path:
    workspace = tmp_path / "space"
    workspace.mkdir()
    (workspace / "sales.csv").write_text(
        "month,revenue\n2024-01,100\n2024-02,150\n2024-03,90\n", encoding="utf-8"
    )
    return workspace


@pytest.fixture()
def rpc(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DREAM_DATA_LOCAL_EXEC", "1")
    monkeypatch.setenv("DREAM_DATASETS_DIR", str(tmp_path / "datasets"))
    from dream.skills.data_science import DataScienceRuntime

    engine = ResearchEngine(
        store=SessionStore(tmp_path / "research"),
        runtime=DataScienceRuntime(),
        backend=EchoBackend(),
    )
    research_rpc.reset_engine(engine)
    yield research_rpc
    research_rpc.reset_engine(None)


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #


def test_research_methods_are_discovered_through_the_extension_seam():
    methods = BridgeMethods.__new__(BridgeMethods)
    table = methods._build_handler_table()
    for method in (
        "research.create", "research.list", "research.get", "research.plan",
        "research.approve", "research.modify", "research.start",
        "research.status", "research.stream", "research.stop", "research.export",
    ):
        assert method in table, method


def test_handlers_mapping_stays_inside_its_domain():
    assert all(name.startswith("research.") for name in research_rpc.HANDLERS)
    assert all(callable(handler) for handler in research_rpc.HANDLERS.values())


def test_methods_module_is_not_modified():
    source = Path("dream/bridge/methods.py").read_text(encoding="utf-8")
    assert "research." not in source.replace("research.py", "")


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"topic": ""},
        {"topic": "t"},
        {"topic": "t", "workspace": ""},
        {"topic": "x" * 3000, "workspace": "/tmp"},
        {"topic": "t", "workspace": "/tmp", "config": "not-an-object"},
    ],
)
def test_create_rejects_bad_params(rpc, params):
    with pytest.raises(BridgeError) as excinfo:
        _run(rpc.research_create(params))
    assert excinfo.value.code == INVALID_PARAMS


def test_unknown_session_maps_to_invalid_params(rpc):
    with pytest.raises(BridgeError) as excinfo:
        _run(rpc.research_get({"session_id": "a" * 32}))
    assert excinfo.value.code == INVALID_PARAMS


def test_missing_session_id_maps_to_invalid_params(rpc):
    for handler in (rpc.research_get, rpc.research_plan, rpc.research_start,
                    rpc.research_stop, rpc.research_status, rpc.research_export):
        with pytest.raises(BridgeError) as excinfo:
            _run(handler({}))
        assert excinfo.value.code == INVALID_PARAMS


def test_traversing_workspace_maps_to_invalid_params(rpc):
    with pytest.raises(BridgeError) as excinfo:
        _run(rpc.research_create({"topic": "t", "workspace": "/etc"}))
    assert excinfo.value.code == INVALID_PARAMS


def test_status_cursor_must_be_a_non_negative_integer(rpc, space: Path):
    created = _run(rpc.research_create({"topic": "revenue", "workspace": str(space)}))
    with pytest.raises(BridgeError):
        _run(rpc.research_status({"session_id": created["session_id"], "cursor": -1}))


# --------------------------------------------------------------------------- #
# Lifecycle over RPC
# --------------------------------------------------------------------------- #


def test_full_lifecycle_over_rpc(rpc, space: Path):
    created = _run(rpc.research_create({
        "topic": "Why did revenue dip in March?",
        "workspace": str(space),
        "config": {"max_iterations": 1, "max_sections": 2},
    }))
    session_id = created["session_id"]
    assert created["status"] == "IDLE"

    planned = _run(rpc.research_plan({"session_id": session_id}))
    assert planned["status"] == "APPROVAL_PENDING"
    assert planned["plan"]["sections"]
    assert planned["cost_estimate"]["estimated_model_calls"] > 0

    # An unapproved start is refused: the checkpoint is real.
    with pytest.raises(BridgeError):
        _run(rpc.research_start({"session_id": session_id}))

    modified = _run(rpc.research_modify({
        "session_id": session_id,
        "changes": {"sections": [{"title": "Revenue trend", "thesis": "trend"}]},
    }))
    assert [s["title"] for s in modified["plan"]["sections"]] == ["Revenue trend"]

    approved = _run(rpc.research_approve({"session_id": session_id}))
    assert approved["plan"]["approved"] is True

    started = _run(rpc.research_start({"session_id": session_id}))
    assert started["status"] == "COMPLETE", started["error"]
    assert started["progress"] == 1.0

    fetched = _run(rpc.research_get({"session_id": session_id}))
    assert fetched["report"]["markdown_path"]
    assert Path(fetched["report"]["markdown_path"]).exists()

    exported = _run(rpc.research_export({"session_id": session_id}))
    assert exported["published"] is True

    listed = _run(rpc.research_list({}))
    assert any(s["session_id"] == session_id for s in listed["sessions"])


def test_status_advances_the_event_cursor(rpc, space: Path):
    created = _run(rpc.research_create({"topic": "revenue", "workspace": str(space)}))
    session_id = created["session_id"]
    _run(rpc.research_plan({"session_id": session_id}))
    first = _run(rpc.research_status({"session_id": session_id, "cursor": 0}))
    assert first["cursor"] > 0
    second = _run(rpc.research_status({"session_id": session_id, "cursor": first["cursor"]}))
    assert second["new_events"] == []


def test_stop_cancels_and_reports_a_terminal_status(rpc, space: Path):
    created = _run(rpc.research_create({"topic": "revenue", "workspace": str(space)}))
    stopped = _run(rpc.research_stop({"session_id": created["session_id"]}))
    assert stopped["status"] == "CANCELLED"


# --------------------------------------------------------------------------- #
# Streaming
# --------------------------------------------------------------------------- #


def test_stream_replays_progress_events_and_returns_a_summary(rpc, space: Path):
    created = _run(rpc.research_create({
        "topic": "revenue", "workspace": str(space),
        "config": {"max_iterations": 1, "max_sections": 1},
    }))
    session_id = created["session_id"]
    _run(rpc.research_plan({"session_id": session_id}))
    _run(rpc.research_approve({"session_id": session_id}))
    _run(rpc.research_start({"session_id": session_id}))

    async def drain():
        stream = await rpc.research_stream(
            {"session_id": session_id, "cursor": 0, "follow": False}
        )
        assert isinstance(stream, Stream)
        chunks = [chunk async for chunk in stream.chunks]
        return chunks, stream.final

    chunks, final = _run(drain())
    names = [chunk["event"]["event"] for chunk in chunks]
    assert "plan.ready" in names and "report.compiled" in names
    assert chunks[-1]["cursor"] == len(chunks)
    assert final["status"] == "COMPLETE"


def test_stream_follow_stops_at_its_timeout(rpc, space: Path):
    created = _run(rpc.research_create({"topic": "revenue", "workspace": str(space)}))

    async def drain():
        stream = await rpc.research_stream(
            {"session_id": created["session_id"], "follow": True, "timeout": 0.2}
        )
        return [chunk async for chunk in stream.chunks]

    chunks = _run(drain())  # must return, not hang
    assert isinstance(chunks, list)


def test_stream_rejects_a_bad_timeout(rpc, space: Path):
    created = _run(rpc.research_create({"topic": "revenue", "workspace": str(space)}))
    with pytest.raises(BridgeError):
        _run(rpc.research_stream({"session_id": created["session_id"], "timeout": "soon"}))


def test_handlers_accept_keyword_dispatch(rpc, space: Path):
    created = _run(rpc.research_create(topic="revenue", workspace=str(space)))
    assert created["session_id"]
    fetched = _run(rpc.research_get(session_id=created["session_id"]))
    assert fetched["session_id"] == created["session_id"]
