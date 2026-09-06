"""P-14 workspace path-safety and preview hardening.

Deterministic security tests: traversal, escapes, depth caps, binary sniff,
permission mapping, case/separator normalization, and log privacy. Temp dirs
only — no sleeps, no network, no user data.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from dream.workspace.errors import WorkspaceError, WorkspaceSecurityError
from dream.workspace.files import list_entries
from dream.workspace.paths import relative_key, resolve_inside
from dream.workspace.preview import preview_file
from dream.workspace.service import WorkspaceService


@pytest.fixture()
def space(tmp_path: Path) -> Path:
    folder = tmp_path / "space"
    folder.mkdir()
    (folder / "ok.txt").write_text("visible", encoding="utf-8")
    return folder


@pytest.fixture()
def service(tmp_path: Path) -> WorkspaceService:
    svc = WorkspaceService(
        registry_path=tmp_path / "registry.json",
        projects_path=tmp_path / "projects.json",
    )
    svc.ops_path = tmp_path / "ops.jsonl"
    return svc


# ================================================= traversal & escape forms


@pytest.mark.parametrize(
    "rel",
    [
        "..",
        "../outside.txt",
        "a/../../outside.txt",
        "a/b/../../../c",
        "..\\windows\\style",
    ],
)
def test_relative_traversal_forms_are_refused(space: Path, rel: str) -> None:
    with pytest.raises(WorkspaceSecurityError):
        resolve_inside(space, rel)


@pytest.mark.parametrize("rel", ["/etc/passwd", "C:\\Windows\\System32", "c:/temp"])
def test_absolute_escapes_are_refused(space: Path, rel: str) -> None:
    with pytest.raises(WorkspaceSecurityError):
        resolve_inside(space, rel)


def test_percent_encoded_dots_are_a_literal_name_not_traversal(space: Path) -> None:
    """The RPC layer never URL-decodes: %2e%2e is just a (missing) file name."""
    resolved = resolve_inside(space, "%2e%2e/%2e%2e/etc/passwd")
    assert str(resolved).startswith(str(space))


def test_depth_cap_refuses_extreme_nesting(space: Path) -> None:
    deep = "/".join(["d"] * 65)
    with pytest.raises(WorkspaceSecurityError, match="depth"):
        relative_key(deep)
    # 64 segments is still legal (bound, not off-by-one).
    assert relative_key("/".join(["d"] * 64)).count("/") == 63


def test_separator_normalization_is_stable(space: Path) -> None:
    assert relative_key("a\\b\\c") == "a/b/c"
    assert relative_key("./a//b/.") == "a/b"
    assert relative_key(None) == ""


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink semantics")
def test_symlink_escape_is_refused_in_listing(tmp_path: Path, space: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    (space / "link").symlink_to(outside)
    with pytest.raises(WorkspaceSecurityError):
        resolve_inside(space, "link/secret.txt")
    # And the listing never follows or shows the link.
    listing = list_entries(space, "")
    assert all(entry["name"] != "link" for entry in listing["entries"])


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink semantics")
def test_junction_like_directory_link_escape_is_refused(
    tmp_path: Path, space: Path
) -> None:
    """A directory link inside the root that resolves outside is refused —
    the same resolve+relative_to check catches NTFS junctions on Windows,
    where os.symlink-style links may not report is_symlink()."""
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (space / "jct").symlink_to(outside, target_is_directory=True)
    with pytest.raises(WorkspaceSecurityError):
        resolve_inside(space, "jct")


# ======================================================== bounded operations


def test_directory_entry_limit_is_enforced(tmp_path: Path) -> None:
    big = tmp_path / "big"
    big.mkdir()
    for index in range(250):
        (big / f"f{index:04d}.txt").write_text("x", encoding="utf-8")
    listing = list_entries(big, "", cursor=0, limit=200)
    assert listing["count"] <= 200
    assert listing["truncated"] is True
    with pytest.raises(WorkspaceError):
        list_entries(big, "", cursor=0, limit=201)
    with pytest.raises(WorkspaceError):
        list_entries(big, "", cursor=-1, limit=10)


def test_file_size_limit_caps_preview(tmp_path: Path) -> None:
    folder = tmp_path / "space"
    folder.mkdir()
    (folder / "big.txt").write_text("A" * 200_000, encoding="utf-8")
    preview = preview_file(folder, "big.txt")
    assert preview["truncated"] is True
    assert len(preview["text"]) <= 24_000
    assert preview["executed"] is False


# ================================================== binary & preview policy


def test_binary_bytes_in_a_text_suffix_are_not_decoded(tmp_path: Path) -> None:
    folder = tmp_path / "space"
    folder.mkdir()
    (folder / "fake.txt").write_bytes(b"\x00\x01\x02binary\x00payload")
    preview = preview_file(folder, "fake.txt")
    assert preview["text"] == ""
    assert preview["type"] == "file"
    assert "Binary" in preview["warning"]
    assert preview["executed"] is False


def test_binary_bytes_in_a_csv_suffix_are_not_decoded(tmp_path: Path) -> None:
    folder = tmp_path / "space"
    folder.mkdir()
    (folder / "fake.csv").write_bytes(b"a,b\x00\xff\xfe,c")
    preview = preview_file(folder, "fake.csv")
    assert preview["table"] is None
    assert preview["text"] == ""
    assert "Binary" in preview["warning"]


def test_utf8_text_still_previews(tmp_path: Path) -> None:
    folder = tmp_path / "space"
    folder.mkdir()
    (folder / "fa.txt").write_text("سلام دنیا", encoding="utf-8")
    assert "سلام" in preview_file(folder, "fa.txt")["text"]


# ================================================ permission-error mapping


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="chmod-based denial needs a non-root POSIX user",
)
def test_permission_error_maps_to_workspace_error(tmp_path: Path) -> None:
    folder = tmp_path / "space"
    folder.mkdir()
    locked = folder / "locked"
    locked.mkdir()
    (locked / "f.txt").write_text("x", encoding="utf-8")
    locked.chmod(0)
    try:
        with pytest.raises(WorkspaceError) as excinfo:
            list_entries(folder, "locked")
        # Typed and safe: no absolute path in the message.
        assert str(tmp_path) not in str(excinfo.value)
    finally:
        locked.chmod(stat.S_IRWXU)


# ============================================================= log privacy


def test_ops_log_never_contains_paths_or_contents(
    service: WorkspaceService, tmp_path: Path
) -> None:
    space = tmp_path / "private-place"
    space.mkdir()
    (space / "secret-name.txt").write_text("api_key = sk-123", encoding="utf-8")
    imported = service.import_folder(str(space), name="P")
    root_id = imported["root"]["root_id"]
    service.files_preview(root_id, "secret-name.txt")

    logged = service.ops_path.read_text(encoding="utf-8")
    assert "private-place" not in logged
    assert "secret-name" not in logged
    assert "sk-123" not in logged
    # Every line is valid JSON (machine-checkable, not str(dict)).
    for line in logged.splitlines():
        record = json.loads(line)
        assert record["action"] in {"import_folder", "preview", "move_session"}


def test_secret_values_are_redacted_in_preview(tmp_path: Path) -> None:
    folder = tmp_path / "space"
    folder.mkdir()
    (folder / "env.txt").write_text("password=hunter2\ntoken: abc", encoding="utf-8")
    text = preview_file(folder, "env.txt")["text"]
    assert "hunter2" not in text
    assert "[REDACTED]" in text


# ====================================== error messages stay path-free & typed


def test_security_errors_do_not_echo_the_root_path(space: Path) -> None:
    with pytest.raises(WorkspaceSecurityError) as excinfo:
        resolve_inside(space, "../escape")
    assert str(space) not in str(excinfo.value)
