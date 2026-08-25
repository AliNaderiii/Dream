"""Path-traversal, symlink, and preview-safety gates for the workspace."""

from __future__ import annotations

from pathlib import Path

import pytest

from dream.workspace.errors import WorkspaceSecurityError
from dream.workspace.paths import normalize_root, resolve_inside
from dream.workspace.preview import TEXT_CHARS, preview_file, redact
from dream.workspace.service import WorkspaceService


@pytest.fixture()
def space(tmp_path: Path) -> Path:
    folder = tmp_path / "space"
    folder.mkdir()
    (folder / "ok.txt").write_text("visible", encoding="utf-8")
    return folder


def test_dotdot_traversal_is_refused(space: Path) -> None:
    with pytest.raises(WorkspaceSecurityError):
        resolve_inside(space, "../secret")
    with pytest.raises(WorkspaceSecurityError):
        resolve_inside(space, "nested/../../etc/passwd")


def test_absolute_path_is_refused(space: Path) -> None:
    with pytest.raises(WorkspaceSecurityError):
        resolve_inside(space, "/etc/passwd")


def test_symlink_escape_is_refused(tmp_path: Path, space: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = space / "escape"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")
    with pytest.raises(WorkspaceSecurityError):
        resolve_inside(space, "escape")


def test_symlink_root_is_refused(tmp_path: Path, space: Path) -> None:
    link = tmp_path / "alias"
    try:
        link.symlink_to(space, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")
    with pytest.raises(WorkspaceSecurityError):
        normalize_root(link)


def test_import_refuses_a_file(tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-dir.txt"
    file_path.write_text("x", encoding="utf-8")
    service = WorkspaceService(
        registry_path=tmp_path / "registry.json", projects_path=tmp_path / "projects.json"
    )
    with pytest.raises(WorkspaceSecurityError):
        service.import_folder(str(file_path))


def test_preview_never_executes_html(tmp_path: Path) -> None:
    (tmp_path / "page.html").write_text(
        "<html><body onload='steal()'>hi<script>steal()</script></body></html>",
        encoding="utf-8",
    )
    preview = preview_file(tmp_path, "page.html")
    assert preview["executed"] is False
    assert "steal" not in preview["html"]


def test_secrets_are_redacted_from_text_preview(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("password=super-secret-value-12345\n", encoding="utf-8")
    preview = preview_file(tmp_path, "notes.txt")
    assert "super-secret-value-12345" not in preview["text"]
    assert "[REDACTED]" in preview["text"]
    assert "super-secret-value-12345" not in redact("token: super-secret-value-12345")


def test_null_byte_path_is_refused(space: Path) -> None:
    with pytest.raises(WorkspaceSecurityError):
        resolve_inside(space, "ok\x00.txt")


def test_preview_read_is_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    huge = tmp_path / "huge.txt"
    huge.write_bytes(b"a" * (256 * 1024))

    def forbid_read_bytes(self: Path) -> bytes:
        del self
        raise AssertionError("read_bytes must not slurp the whole file")

    monkeypatch.setattr(Path, "read_bytes", forbid_read_bytes)
    preview = preview_file(tmp_path, "huge.txt")
    assert preview["truncated"] is True
    assert len(preview["text"]) <= TEXT_CHARS
