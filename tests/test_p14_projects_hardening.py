"""P-14 project persistence hardening.

Pins the dual-writer merge (F1), fail-closed corrupt-metadata recovery (F2),
and the name/folder validation caps (F3). Everything runs against temporary
files — no sleeps, no network, no real user data.
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
from typing import Any

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.methods import BridgeMethods
from dream.memory import MemoryStore
from dream.workspace.projects import ProjectOverlay
from dream.workspace.registry import WorkspaceRegistry


def make_methods(projects_path: str | None = None, **kwargs: Any) -> BridgeMethods:
    store = MemoryStore(":memory:")
    return BridgeMethods(
        store,
        sessions_path=tempfile.mktemp(suffix=".json"),
        providers_path=tempfile.mktemp(suffix=".json"),
        projects_path=projects_path or tempfile.mktemp(suffix=".json"),
        default_provider="echo",
        **kwargs,
    )


# ================================================== F1 — dual-writer merge


def test_save_preserves_rows_written_by_the_overlay(tmp_path: pathlib.Path) -> None:
    """A project adopted through workspace.* after startup must survive a
    project.* save instead of being silently deleted."""
    index = tmp_path / "projects.json"
    m = make_methods(projects_path=str(index))
    mine = m.project_create({"name": "Mine"})

    # Another writer (the Projects 2.0 overlay) adds a row at runtime.
    space = tmp_path / "space"
    space.mkdir()
    overlay = ProjectOverlay(index)
    adopted = overlay.adopt(str(space), name="Adopted")

    # A project.* mutation triggers a full save — the foreign row survives.
    m.project_update({"project_id": mine["project_id"], "name": "Mine 2"})
    rows = json.loads(index.read_text(encoding="utf-8"))
    ids = {row["id"] for row in rows}
    assert adopted["project_id"] in ids
    assert mine["project_id"] in ids


def test_save_round_trips_overlay_extra_fields(tmp_path: pathlib.Path) -> None:
    """Overlay fields (settings, imported_in_place, copied) on a row the S06
    surface tracks are kept verbatim across a project.* save."""
    index = tmp_path / "projects.json"
    seed = [
        {
            "id": "prj_extras",
            "name": "Seeded",
            "folder": None,
            "session_ids": [],
            "created_at": 1.0,
            "updated_at": 1.0,
            "settings": {"default_mode": "plan", "language": "fa"},
            "imported_in_place": True,
            "copied": False,
        }
    ]
    index.write_text(json.dumps(seed), encoding="utf-8")
    m = make_methods(projects_path=str(index))
    m.project_update({"project_id": "prj_extras", "name": "Renamed"})

    rows = json.loads(index.read_text(encoding="utf-8"))
    row = next(r for r in rows if r["id"] == "prj_extras")
    assert row["name"] == "Renamed"
    assert row["settings"] == {"default_mode": "plan", "language": "fa"}
    assert row["imported_in_place"] is True
    assert row["copied"] is False


def test_delete_wins_over_the_merge(tmp_path: pathlib.Path) -> None:
    """project.delete removes the row even though the merge re-reads disk."""
    index = tmp_path / "projects.json"
    m = make_methods(projects_path=str(index))
    doomed = m.project_create({"name": "Doomed"})
    kept = m.project_create({"name": "Kept"})
    m.project_delete({"project_id": doomed["project_id"]})

    rows = json.loads(index.read_text(encoding="utf-8"))
    ids = {row["id"] for row in rows}
    assert doomed["project_id"] not in ids
    assert kept["project_id"] in ids


def test_merge_survives_a_reload(tmp_path: pathlib.Path) -> None:
    """Foreign rows merged once stay present for a fresh BridgeMethods."""
    index = tmp_path / "projects.json"
    m = make_methods(projects_path=str(index))
    m.project_create({"name": "A"})
    space = tmp_path / "space"
    space.mkdir()
    ProjectOverlay(index).adopt(str(space), name="B")
    m.project_create({"name": "C"})  # triggers merge-preserving save

    m2 = make_methods(projects_path=str(index))
    names = {p["name"] for p in m2.project_list()["projects"]}
    assert {"A", "B", "C"} <= names


# ============================================ F2 — corrupt metadata fails closed


def test_corrupt_bridge_index_is_quarantined_not_overwritten(
    tmp_path: pathlib.Path,
) -> None:
    index = tmp_path / "projects.json"
    index.write_text("{not json", encoding="utf-8")
    m = make_methods(projects_path=str(index))
    assert m.project_list()["projects"] == []
    backup = tmp_path / "projects.json.corrupt-1"
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "{not json"
    # A save now writes a fresh file without touching the backup.
    m.project_create({"name": "Fresh"})
    assert backup.read_text(encoding="utf-8") == "{not json"
    rows = json.loads(index.read_text(encoding="utf-8"))
    assert [row["name"] for row in rows] == ["Fresh"]


def test_non_list_bridge_index_is_quarantined(tmp_path: pathlib.Path) -> None:
    index = tmp_path / "projects.json"
    index.write_text(json.dumps({"oops": True}), encoding="utf-8")
    make_methods(projects_path=str(index))
    assert (tmp_path / "projects.json.corrupt-1").exists()


def test_corrupt_overlay_store_is_quarantined(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "overlay.json"
    path.write_text("]", encoding="utf-8")
    overlay = ProjectOverlay(path)
    space = tmp_path / "space"
    space.mkdir()
    overlay.adopt(str(space), name="After corruption")
    backup = tmp_path / "overlay.json.corrupt-1"
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "]"


def test_corrupt_registry_is_quarantined(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text("no json here", encoding="utf-8")
    registry = WorkspaceRegistry(path)
    assert registry.list() == []
    assert (tmp_path / "registry.json.corrupt-1").exists()


def test_missing_index_is_not_a_corruption(tmp_path: pathlib.Path) -> None:
    """A simply absent file loads as empty without creating a backup."""
    index = tmp_path / "projects.json"
    m = make_methods(projects_path=str(index))
    assert m.project_list()["projects"] == []
    assert not any(p.name.startswith("projects.json.corrupt") for p in tmp_path.iterdir())


# ===================================================== F3 — validation caps


def test_project_name_length_is_bounded() -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="200"):
        m.project_create({"name": "x" * 201})
    ok = m.project_create({"name": "x" * 200})
    with pytest.raises(BridgeError, match="200"):
        m.project_update({"project_id": ok["project_id"], "name": "y" * 201})


def test_project_name_rejects_null_bytes() -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="control"):
        m.project_create({"name": "bad\x00name"})


def test_project_folder_length_and_nul_are_bounded() -> None:
    m = make_methods()
    with pytest.raises(BridgeError, match="4"):
        m.project_create({"name": "P", "folder": "/x/" + "a" * 5000})
    with pytest.raises(BridgeError, match="control"):
        m.project_create({"name": "P", "folder": "/tmp/\x00evil"})
    project = m.project_create({"name": "P"})
    with pytest.raises(BridgeError, match="control"):
        m.project_update({"project_id": project["project_id"], "folder": "/a\x00b"})


def test_atomic_save_leaves_no_tmp_file(tmp_path: pathlib.Path) -> None:
    index = tmp_path / "projects.json"
    m = make_methods(projects_path=str(index))
    m.project_create({"name": "Atomic"})
    assert index.exists()
    assert not os.path.exists(str(index) + ".tmp")


# ======================================= project/session association integrity


def test_session_association_survives_merge_saves(tmp_path: pathlib.Path) -> None:
    index = tmp_path / "projects.json"
    m = make_methods(projects_path=str(index))
    session = m.session_create({"title": "S"})
    project = m.project_create({"name": "P"})
    m.project_add_session(
        {"project_id": project["project_id"], "session_id": session["session_id"]}
    )
    # An unrelated create triggers another merge-preserving save.
    m.project_create({"name": "Q"})
    got = m.project_get({"project_id": project["project_id"]})
    assert got["session_ids"] == [session["session_id"]]
