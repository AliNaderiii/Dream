"""G7 — live jupyter_client kernel round-trips plus output summarisation.

The live-kernel tests skip when ``jupyter_client``/``ipykernel`` are absent
(minimal CI); the summarisation and JupyterLab-degradation tests always run.
"""

from __future__ import annotations

import sys
import types

import pytest

from dream.skills.notebooks import (
    NotebookManager,
    NotebookUnavailableError,
    _summarise_output,
)

DATASET_ID = "e" * 32


@pytest.fixture()
def manager(tmp_path):
    (tmp_path / "datasets" / DATASET_ID).mkdir(parents=True)
    nb_manager = NotebookManager(tmp_path / "datasets")
    yield nb_manager
    nb_manager.shutdown_all()


# --------------------------------------------------------------------------- #
# Output summarisation — pure functions, no kernel
# --------------------------------------------------------------------------- #


def test_summarise_stream_output():
    out = _summarise_output({"output_type": "stream", "name": "stderr", "text": "warn"})
    assert out == {"type": "stream", "name": "stderr", "text": "warn"}


def test_summarise_stream_output_truncates():
    out = _summarise_output({"output_type": "stream", "text": "x" * 30_000})
    assert len(out["text"]) < 25_000
    assert "truncated" in out["text"]


def test_summarise_execute_result_with_image():
    out = _summarise_output({
        "output_type": "execute_result",
        "data": {"text/plain": "<Figure>", "image/png": "aGVsbG8="},
    })
    assert out["image_mime"] == "image/png"
    assert out["image_data"] == "aGVsbG8="
    assert out["text"] == "<Figure>"


def test_summarise_oversized_image_is_flagged_not_shipped():
    out = _summarise_output({
        "output_type": "display_data",
        "data": {"image/png": "A" * (5 * 1024 * 1024)},
    })
    assert out.get("image_truncated") is True
    assert "image_data" not in out


def test_summarise_html_output():
    out = _summarise_output({
        "output_type": "display_data",
        "data": {"text/html": "<table><tr><td>1</td></tr></table>"},
    })
    assert out["html"].startswith("<table>")


def test_summarise_error_output():
    out = _summarise_output({
        "output_type": "error",
        "ename": "ZeroDivisionError",
        "evalue": "division by zero",
        "traceback": ["Traceback...", "ZeroDivisionError: division by zero"],
    })
    assert out["type"] == "error"
    assert out["ename"] == "ZeroDivisionError"
    assert "division by zero" in out["traceback"]


def test_summarise_unknown_output_type():
    assert _summarise_output({})["type"] == "unknown"


# --------------------------------------------------------------------------- #
# JupyterLab degradation
# --------------------------------------------------------------------------- #


def test_open_jupyterlab_degrades_without_install(manager, monkeypatch):
    created = manager.create_notebook(DATASET_ID, "lab_nb", [
        {"type": "code", "source": "1"},
    ])
    monkeypatch.setitem(sys.modules, "jupyterlab", None)
    # A None module entry makes ``import jupyterlab`` raise ImportError.
    with pytest.raises(NotebookUnavailableError, match="JupyterLab"):
        manager.open_jupyterlab(created["notebook_path"])


def test_open_jupyterlab_spawns_and_reuses(manager, monkeypatch):
    created = manager.create_notebook(DATASET_ID, "lab_nb2", [
        {"type": "code", "source": "1"},
    ])
    monkeypatch.setitem(sys.modules, "jupyterlab", types.ModuleType("jupyterlab"))

    spawned = []

    class FakeProcess:
        def poll(self):
            return None

        def terminate(self):
            spawned.append("terminated")

        def wait(self, timeout=None):
            return 0

    def fake_popen(command, **kwargs):
        spawned.append(command)
        return FakeProcess()

    monkeypatch.setattr("dream.skills.notebooks.subprocess.Popen", fake_popen)
    first = manager.open_jupyterlab(created["notebook_path"])
    assert first["already_running"] is False
    assert "?token=" in first["url"] and "lab/tree" in first["url"]
    assert len([s for s in spawned if isinstance(s, list)]) == 1

    second = manager.open_jupyterlab(created["notebook_path"])
    assert second["already_running"] is True
    assert len([s for s in spawned if isinstance(s, list)]) == 1  # no respawn

    manager.shutdown_all()
    assert "terminated" in spawned


# --------------------------------------------------------------------------- #
# Live kernel (skipped when jupyter_client / ipykernel are absent)
# --------------------------------------------------------------------------- #

jupyter_client = pytest.importorskip("jupyter_client")
pytest.importorskip("ipykernel")


def test_live_kernel_execute_and_run_cell(manager):
    created = manager.create_notebook(DATASET_ID, "live", [
        {"type": "markdown", "source": "# fixture"},
        {"type": "code", "source": "value = 21 * 2\nprint('computed', value)"},
        {"type": "code", "source": "value"},
    ])
    kernel_id = manager.ensure_kernel(DATASET_ID)
    assert kernel_id

    result = manager.execute_notebook(created["notebook_path"], kernel_id)
    assert result["cells_executed"] == 2
    stream = result["outputs"][0]["outputs"]
    assert any("computed 42" in o.get("text", "") for o in stream)
    final = result["outputs"][1]["outputs"]
    assert any(o.get("text") == "42" for o in final)

    # State persists across run_cell on the same kernel.
    rerun = manager.run_cell(created["notebook_path"], 2)
    assert any(o.get("text") == "42" for o in rerun["outputs"])

    # ensure_kernel reuses the live kernel.
    assert manager.ensure_kernel(DATASET_ID) == kernel_id
    assert manager.shutdown_kernel(DATASET_ID) is True


def test_live_kernel_error_output_flows_back(manager):
    created = manager.create_notebook(DATASET_ID, "boom", [
        {"type": "code", "source": "1 / 0"},
    ])
    result = manager.execute_notebook(created["notebook_path"])
    outputs = result["outputs"][0]["outputs"]
    assert any(o["type"] == "error" and o["ename"] == "ZeroDivisionError"
               for o in outputs)
