"""Workspace confinement (Security audit, P-11).

Verifies that notebook paths handed to the data workbench cannot escape the
configured datasets directory (traversal, absolute paths, and non-notebook
files are all refused).
"""

from __future__ import annotations

import pytest

from dream.skills.notebooks import NotebookManager


def test_relative_notebook_resolves_inside_root(tmp_path) -> None:
    manager = NotebookManager(datasets_root=tmp_path)
    resolved = manager._resolve_notebook("notebooks/foo.ipynb")
    assert resolved == (tmp_path / "notebooks/foo.ipynb").resolve()


def test_parent_traversal_is_refused(tmp_path) -> None:
    manager = NotebookManager(datasets_root=tmp_path)
    with pytest.raises(PermissionError, match="escapes the datasets directory"):
        manager._resolve_notebook("../outside.ipynb")


def test_absolute_path_outside_root_is_refused(tmp_path) -> None:
    manager = NotebookManager(datasets_root=tmp_path)
    with pytest.raises(PermissionError, match="escapes the datasets directory"):
        manager._resolve_notebook("/etc/passwd")


def test_non_notebook_suffix_is_refused(tmp_path) -> None:
    manager = NotebookManager(datasets_root=tmp_path)
    with pytest.raises(ValueError, match="\\.ipynb"):
        manager._resolve_notebook("report.md")


def test_empty_path_is_refused(tmp_path) -> None:
    manager = NotebookManager(datasets_root=tmp_path)
    with pytest.raises(ValueError, match="non-empty string"):
        manager._resolve_notebook("")


def test_non_string_path_is_refused(tmp_path) -> None:
    manager = NotebookManager(datasets_root=tmp_path)
    with pytest.raises(ValueError, match="non-empty string"):
        manager._resolve_notebook(None)


def test_dataset_id_is_validated(tmp_path) -> None:
    manager = NotebookManager(datasets_root=tmp_path)
    with pytest.raises(ValueError, match="32-character hex id"):
        manager._dataset_dir("../etc")
