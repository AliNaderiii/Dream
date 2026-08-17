"""Bridge coverage for the data.* and notebook.* RPC families (P-09).

The bridge is exercised with a real DataScienceRuntime wired to the local
executor (skipped when pandas is absent) plus fake-based tests that need no
scientific stack at all — parameter validation, error mapping, and the
notebook manager contract with a stub kernel.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.methods import BridgeMethods
from dream.memory import MemoryStore
from dream.skills.notebooks import (
    NotebookManager,
    NotebookUnavailableError,
    new_notebook,
    validate_notebook_name,
)


def _run(coro):
    return asyncio.run(coro)


def make_bridge(tmp_path, **kwargs):
    return BridgeMethods(
        store=MemoryStore(str(tmp_path / "bridge.db")),
        sessions_path=str(tmp_path / "sessions.json"),
        providers_path=str(tmp_path / "providers.json"),
        provenance_dir=str(tmp_path / "provenance"),
        mcp_config_path=str(tmp_path / "mcp.json"),
        acp_config_path=str(tmp_path / "acp.json"),
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Parameter validation — no runtime needed
# --------------------------------------------------------------------------- #


class ExplodingRuntime:
    """A runtime standing in so validation failures never *call* it."""

    def __getattr__(self, name):
        def explode(*args, **kwargs):  # pragma: no cover - never called
            raise AssertionError(f"runtime.{name}() must not be reached")

        return explode


@pytest.fixture()
def bridge(tmp_path):
    b = make_bridge(tmp_path, data_runtime=ExplodingRuntime())
    yield b
    b.shutdown()


def test_data_methods_registered(bridge):
    for method in (
        "data.load_data", "data.profile_data", "data.clean_data",
        "data.analyze_data", "data.auto_chart", "data.create_chart",
        "data.generate_report", "data.get_report", "data.list_datasets",
        "data.get_dataset", "data.delete_dataset",
        "notebook.create", "notebook.execute", "notebook.run_cell",
        "notebook.read", "notebook.open_lab",
    ):
        assert method in bridge.handlers, method


def test_data_load_requires_file_path(bridge):
    with pytest.raises(BridgeError) as excinfo:
        _run(bridge.data_load_data({}))
    assert excinfo.value.code == -32602
    with pytest.raises(BridgeError):
        _run(bridge.data_load_data({"file_path": "   "}))
    with pytest.raises(BridgeError):
        _run(bridge.data_load_data({"file_path": "x.csv", "name": 42}))


def test_data_methods_require_dataset_id(bridge):
    with pytest.raises(BridgeError):
        _run(bridge.data_profile_data({}))
    with pytest.raises(BridgeError):
        _run(bridge.data_clean_data({"dataset_id": "", "operations": [{"op": "drop_na"}]}))
    with pytest.raises(BridgeError):
        _run(bridge.data_analyze_data({"dataset_id": "a" * 32}))  # analyses missing
    with pytest.raises(BridgeError):
        _run(bridge.data_generate_report({"dataset_id": "a" * 32}))  # title missing


def test_data_clean_requires_operation_list(bridge):
    with pytest.raises(BridgeError):
        _run(bridge.data_clean_data({"dataset_id": "a" * 32, "operations": "drop_na"}))
    with pytest.raises(BridgeError):
        _run(bridge.data_clean_data({"dataset_id": "a" * 32, "operations": []}))


def test_data_create_chart_requires_object(bridge):
    with pytest.raises(BridgeError):
        _run(bridge.data_create_chart({"chart_spec": "bar"}))


def test_notebook_methods_validate_params(bridge):
    with pytest.raises(BridgeError):
        _run(bridge.notebook_create({"dataset_id": "a" * 32}))  # name missing
    with pytest.raises(BridgeError):
        _run(bridge.notebook_execute({}))  # path missing
    with pytest.raises(BridgeError):
        _run(bridge.notebook_run_cell({"path": "x.ipynb", "cell_index": -1}))
    with pytest.raises(BridgeError):
        _run(bridge.notebook_run_cell({"path": "x.ipynb", "cell_index": True}))
    with pytest.raises(BridgeError):
        _run(bridge.notebook_read({"path": ""}))


# --------------------------------------------------------------------------- #
# End-to-end through the bridge with the real runtime (pandas required)
# --------------------------------------------------------------------------- #


@pytest.fixture()
def live_bridge(tmp_path):
    pytest.importorskip("pandas")
    from tests._data_science_helpers import make_runtime

    runtime = make_runtime(tmp_path)
    b = make_bridge(tmp_path, data_runtime=runtime)
    yield b, tmp_path
    b.shutdown()


def _seed_csv(tmp_path):
    path = tmp_path / "input.csv"
    path.write_text(
        "region,revenue\nnorth,10\nsouth,20\nnorth,30\neast,40\n", encoding="utf-8"
    )
    return path


def test_bridge_data_pipeline_end_to_end(live_bridge):
    bridge, tmp_path = live_bridge
    csv = _seed_csv(tmp_path)

    loaded = _run(bridge.data_load_data({"file_path": str(csv), "name": "revenue"}))
    dataset_id = loaded["dataset_id"]
    assert loaded["shape"] == [4, 2]

    listed = bridge.data_list_datasets({})
    assert listed["datasets"][0]["dataset_id"] == dataset_id

    record = bridge.data_get_dataset({"dataset_id": dataset_id})
    assert record["name"] == "revenue"

    profile = _run(bridge.data_profile_data({"dataset_id": dataset_id}))
    assert profile["row_count"] == 4

    cleaned = _run(bridge.data_clean_data({
        "dataset_id": dataset_id,
        "operations": [{"op": "filter_rows", "column": "revenue",
                        "operator": "gt", "value": 15}],
    }))
    assert cleaned["rows_after"] == 3

    analyzed = _run(bridge.data_analyze_data({
        "dataset_id": dataset_id,
        "analyses": [{"kind": "correlation"}],
    }))
    assert analyzed["results"][0]["status"] == "ok"

    suggestions = _run(bridge.data_auto_chart({"dataset_id": dataset_id}))
    assert suggestions["charts"]

    chart = _run(bridge.data_create_chart({
        "chart_spec": {"type": "bar", "dataset_id": dataset_id,
                       "x": "region", "y": "revenue"},
    }))
    assert chart["sizes"]["png"] > 0

    report = _run(bridge.data_generate_report({
        "dataset_id": dataset_id, "title": "Bridge Report",
    }))
    assert report["size_bytes"] > 0

    markdown = _run(bridge.data_get_report({"dataset_id": dataset_id}))
    assert markdown["markdown"].startswith("# Bridge Report")

    deleted = bridge.data_delete_dataset({"dataset_id": dataset_id})
    assert deleted["deleted"] is True
    assert bridge.data_list_datasets({})["datasets"] == []


def test_bridge_maps_runtime_validation_to_invalid_params(live_bridge):
    bridge, tmp_path = live_bridge
    csv = _seed_csv(tmp_path)
    loaded = _run(bridge.data_load_data({"file_path": str(csv)}))
    with pytest.raises(BridgeError) as excinfo:
        _run(bridge.data_clean_data({
            "dataset_id": loaded["dataset_id"],
            "operations": [{"op": "drop_column", "column": "ghost"}],
        }))
    assert excinfo.value.code == -32602
    with pytest.raises(BridgeError) as excinfo:
        _run(bridge.data_profile_data({"dataset_id": "f" * 32}))
    assert excinfo.value.code == -32602


# --------------------------------------------------------------------------- #
# Notebook manager — file IO with no kernel, stubbed kernel for execution
# --------------------------------------------------------------------------- #


def _make_dataset_dir(tmp_path):
    dataset_id = "d" * 32
    (tmp_path / "datasets" / dataset_id).mkdir(parents=True)
    return dataset_id


def test_notebook_create_and_read_round_trip(tmp_path):
    dataset_id = _make_dataset_dir(tmp_path)
    manager = NotebookManager(tmp_path / "datasets")
    created = manager.create_notebook(dataset_id, "analysis", [
        {"type": "markdown", "source": "# Title"},
        {"type": "code", "source": "print('hi')"},
    ])
    assert created["cell_count"] == 2
    read = manager.read_notebook(created["notebook_path"])
    assert read["cells"][0]["cell_type"] == "markdown"
    assert read["cells"][1]["source"] == "print('hi')"
    assert read["cells"][1]["outputs"] == []
    # The file itself is valid nbformat v4.
    document = json.loads(open(created["notebook_path"], encoding="utf-8").read())
    assert document["nbformat"] == 4


def test_notebook_name_and_cell_validation(tmp_path):
    dataset_id = _make_dataset_dir(tmp_path)
    manager = NotebookManager(tmp_path / "datasets")
    with pytest.raises(ValueError):
        manager.create_notebook(dataset_id, "../escape", [])
    with pytest.raises(ValueError):
        manager.create_notebook(dataset_id, "ok", [{"type": "sql", "source": ""}])
    with pytest.raises(ValueError):
        validate_notebook_name("")
    assert validate_notebook_name("My Analysis_2") == "My Analysis_2"


def test_notebook_path_confinement(tmp_path):
    _make_dataset_dir(tmp_path)
    manager = NotebookManager(tmp_path / "datasets")
    with pytest.raises(PermissionError):
        manager.read_notebook("../../etc/passwd.ipynb")
    with pytest.raises(ValueError):
        manager.read_notebook("nb.txt")


def test_new_notebook_structure():
    document = new_notebook([{"type": "code", "source": "1 + 1"}])
    assert document["nbformat"] == 4
    cell = document["cells"][0]
    assert cell["cell_type"] == "code"
    assert cell["outputs"] == [] and cell["execution_count"] is None


class _StubKernelManager:
    def is_alive(self):
        return True


class _StubClient:
    """Replays a canned iopub stream for any execute call."""

    def __init__(self):
        self._queue = []

    def execute(self, source):
        msg_id = "msg-1"
        self._queue = [
            {"parent_header": {"msg_id": msg_id}, "msg_type": "execute_input",
             "content": {"execution_count": 1}},
            {"parent_header": {"msg_id": msg_id}, "msg_type": "stream",
             "content": {"name": "stdout", "text": f"ran: {source.strip()}\n"}},
            {"parent_header": {"msg_id": msg_id}, "msg_type": "execute_result",
             "content": {"execution_count": 1, "data": {"text/plain": "42"},
                         "metadata": {}}},
            {"parent_header": {"msg_id": msg_id}, "msg_type": "status",
             "content": {"execution_state": "idle"}},
        ]
        return msg_id

    def get_iopub_msg(self, timeout=None):
        if not self._queue:
            raise TimeoutError
        return self._queue.pop(0)


def _stub_kernel(manager, dataset_id):
    from dream.skills.notebooks import _KernelHandle

    manager._kernels[dataset_id] = _KernelHandle(
        kernel_id="stub-kernel", dataset_id=dataset_id,
        manager=_StubKernelManager(), client=_StubClient(),
    )


def test_notebook_execute_flows_outputs_back(tmp_path):
    dataset_id = _make_dataset_dir(tmp_path)
    manager = NotebookManager(tmp_path / "datasets")
    created = manager.create_notebook(dataset_id, "run_me", [
        {"type": "markdown", "source": "# doc"},
        {"type": "code", "source": "6 * 7"},
    ])
    _stub_kernel(manager, dataset_id)
    result = manager.execute_notebook(created["notebook_path"])
    assert result["cells_executed"] == 1
    outputs = result["outputs"][0]["outputs"]
    assert any(o["type"] == "stream" and "6 * 7" in o["text"] for o in outputs)
    assert any(o.get("text") == "42" for o in outputs)
    # Outputs persisted back into the .ipynb file.
    read = manager.read_notebook(created["notebook_path"])
    assert read["cells"][1]["execution_count"] == 1
    assert read["cells"][1]["outputs"]


def test_notebook_run_cell_by_index(tmp_path):
    dataset_id = _make_dataset_dir(tmp_path)
    manager = NotebookManager(tmp_path / "datasets")
    created = manager.create_notebook(dataset_id, "cells", [
        {"type": "code", "source": "print(1)"},
        {"type": "markdown", "source": "notes"},
    ])
    _stub_kernel(manager, dataset_id)
    result = manager.run_cell(created["notebook_path"], 0)
    assert result["cell_type"] == "code"
    assert result["outputs"]
    # Markdown cells are a no-op, not an error.
    md = manager.run_cell(created["notebook_path"], 1)
    assert md["cell_type"] == "markdown" and md["outputs"] == []
    with pytest.raises(ValueError, match="out of range"):
        manager.run_cell(created["notebook_path"], 9)


def test_notebook_kernel_shutdown_bookkeeping(tmp_path):
    dataset_id = _make_dataset_dir(tmp_path)
    manager = NotebookManager(tmp_path / "datasets")
    assert manager.shutdown_kernel(dataset_id) is False
    _stub_kernel(manager, dataset_id)

    stopped = {"channels": False, "kernel": False}
    handle = manager._kernels[dataset_id]
    handle.client.stop_channels = lambda: stopped.__setitem__("channels", True)
    handle.manager.shutdown_kernel = lambda now=True: stopped.__setitem__("kernel", True)
    assert manager.shutdown_kernel(dataset_id) is True
    assert stopped == {"channels": True, "kernel": True}


def test_bridge_notebook_end_to_end_with_stub_kernel(tmp_path):
    manager = NotebookManager(tmp_path / "datasets")
    dataset_id = _make_dataset_dir(tmp_path)
    bridge = make_bridge(tmp_path, data_runtime=ExplodingRuntime(),
                         notebook_manager=manager)
    try:
        created = _run(bridge.notebook_create({
            "dataset_id": dataset_id, "name": "bridge_nb",
            "cells": [{"type": "code", "source": "2 + 2"}],
        }))
        _stub_kernel(manager, dataset_id)
        executed = _run(bridge.notebook_execute({"path": created["notebook_path"]}))
        assert executed["cells_executed"] == 1
        ran = _run(bridge.notebook_run_cell({
            "path": created["notebook_path"], "cell_index": 0,
        }))
        assert ran["outputs"]
        read = _run(bridge.notebook_read({"path": created["notebook_path"]}))
        assert read["cells"][0]["source"] == "2 + 2"
    finally:
        bridge.shutdown()


def test_notebook_unavailable_maps_to_bridge_error(tmp_path, monkeypatch):
    manager = NotebookManager(tmp_path / "datasets")
    dataset_id = _make_dataset_dir(tmp_path)
    created = manager.create_notebook(dataset_id, "no_jupyter", [
        {"type": "code", "source": "1"},
    ])

    def boom(*args, **kwargs):
        raise NotebookUnavailableError("jupyter_client is not installed")

    monkeypatch.setattr(manager, "execute_notebook", boom)
    monkeypatch.setattr(manager, "open_jupyterlab", boom)
    bridge = make_bridge(tmp_path, data_runtime=ExplodingRuntime(),
                         notebook_manager=manager)
    try:
        with pytest.raises(BridgeError) as excinfo:
            _run(bridge.notebook_execute({"path": created["notebook_path"]}))
        assert excinfo.value.code == -32012
        with pytest.raises(BridgeError) as excinfo:
            _run(bridge.notebook_open_lab({"path": created["notebook_path"]}))
        assert excinfo.value.code == -32012
    finally:
        bridge.shutdown()


def test_delete_dataset_stops_its_kernel(tmp_path):
    pytest.importorskip("pandas")
    from tests._data_science_helpers import make_runtime

    runtime = make_runtime(tmp_path)
    csv = tmp_path / "k.csv"
    csv.write_text("a\n1\n2\n", encoding="utf-8")
    dataset_id = runtime.load_data(str(csv))["dataset_id"]
    manager = NotebookManager(runtime.datasets.root)
    _stub_kernel(manager, dataset_id)
    bridge = make_bridge(tmp_path, data_runtime=runtime, notebook_manager=manager)
    try:
        bridge.data_delete_dataset({"dataset_id": dataset_id})
        assert dataset_id not in manager._kernels
    finally:
        bridge.shutdown()
