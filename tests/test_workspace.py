"""Workspace model: in-place import, bounded listing, CSV preview with chart."""

from __future__ import annotations

from pathlib import Path

import pytest

from dream.bridge.methods import BridgeMethods
from dream.bridge.methods_workspace import HANDLERS
from dream.workspace.errors import WorkspaceSecurityError
from dream.workspace.service import WorkspaceService


@pytest.fixture()
def space(tmp_path: Path) -> Path:
    folder = tmp_path / "space"
    folder.mkdir()
    (folder / "README.md").write_text("# Demo workspace\n", encoding="utf-8")
    (folder / "sales.csv").write_text(
        "region,revenue\nNorth,120\nSouth,80\nEast,60\n", encoding="utf-8"
    )
    nested = folder / "notes"
    nested.mkdir()
    (nested / "todo.md").write_text("- ship the workbench\n", encoding="utf-8")
    return folder


@pytest.fixture()
def service(tmp_path: Path, space: Path) -> WorkspaceService:
    return WorkspaceService(
        registry_path=tmp_path / "registry.json",
        projects_path=tmp_path / "projects.json",
    )


def test_in_place_import_never_copies_and_shows_real_contents(
    service: WorkspaceService, space: Path
) -> None:
    imported = service.import_folder(str(space), name="Lab")
    assert imported["copied"] is False
    assert imported["imported_in_place"] is True
    names = {entry["name"] for entry in imported["listing"]["entries"]}
    assert {"README.md", "sales.csv", "notes"} <= names
    # The original folder is the source of truth — a later write is visible.
    (space / "new.txt").write_text("hello", encoding="utf-8")
    listing = service.files_list(imported["root"]["root_id"], "")
    assert any(entry["name"] == "new.txt" for entry in listing["entries"])
    assert not (space.parent / "Lab").exists()


def test_csv_preview_includes_a_chart(service: WorkspaceService, space: Path) -> None:
    imported = service.import_folder(str(space), name="Lab")
    preview = service.files_preview(imported["root"]["root_id"], "sales.csv")
    assert preview["executed"] is False
    assert preview["chart"]["kind"] == "bar"
    assert preview["chart"]["labels"][0] == "North"
    assert preview["table"]["row_count"] == 3


def test_listing_is_bounded_for_large_folders(service: WorkspaceService, tmp_path: Path) -> None:
    folder = tmp_path / "big"
    folder.mkdir()
    for index in range(350):
        (folder / f"f{index:03d}.txt").write_text("x", encoding="utf-8")
    imported = service.import_folder(str(folder), name="Big")
    page = service.files_list(imported["root"]["root_id"], "", cursor=0, limit=50)
    assert page["count"] == 50
    assert page["has_more"] is True
    nxt = service.files_list(imported["root"]["root_id"], "", cursor=page["next_cursor"], limit=50)
    assert nxt["cursor"] == 50


def test_html_preview_strips_scripts(service: WorkspaceService, tmp_path: Path) -> None:
    folder = tmp_path / "web"
    folder.mkdir()
    (folder / "index.html").write_text(
        "<html><script>alert(1)</script><p onclick='x'>ok</p></html>",
        encoding="utf-8",
    )
    imported = service.import_folder(str(folder), name="Web")
    preview = service.files_preview(imported["root"]["root_id"], "index.html")
    assert "<script" not in preview["html"].lower()
    assert "onclick" not in preview["html"].lower()
    assert preview["executed"] is False


def test_workspace_methods_are_discovered_through_the_extension_seam() -> None:
    methods = BridgeMethods.__new__(BridgeMethods)
    table = methods._build_handler_table()
    for method in HANDLERS:
        assert method in table, method
    assert all(name.startswith("workspace.") for name in HANDLERS)


def test_handlers_mapping_stays_inside_its_domain() -> None:
    assert all(name.startswith("workspace.") for name in HANDLERS)
    assert all(callable(handler) for handler in HANDLERS.values())


def test_project_adopt_is_in_place(service: WorkspaceService, space: Path) -> None:
    adopted = service.project_adopt(str(space), name="Thesis")
    assert adopted["copied"] is False
    assert adopted["project"]["folder"] == str(space.resolve())
    moved = service.project_move_session(adopted["project"]["project_id"], "sess_demo")
    assert "sess_demo" in moved["session_ids"]


def test_notebook_preview_does_not_execute(service: WorkspaceService, tmp_path: Path) -> None:
    folder = tmp_path / "nb"
    folder.mkdir()
    (folder / "analysis.ipynb").write_text(
        '{"cells":[{"cell_type":"code","source":["print(1)"]}],"nbformat":4}',
        encoding="utf-8",
    )
    imported = service.import_folder(str(folder), name="Nb")
    preview = service.files_preview(imported["root"]["root_id"], "analysis.ipynb")
    assert preview["executed"] is False
    assert "print(1)" in preview["text"]


def test_parent_directory_listing_is_refused(service: WorkspaceService, space: Path) -> None:
    imported = service.import_folder(str(space), name="Lab")
    with pytest.raises(WorkspaceSecurityError):
        service.files_list(imported["root"]["root_id"], "..")
