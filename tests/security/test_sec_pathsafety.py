"""Stage C — L4 sensitive-path denylist + traversal corpus (G-09, G-10).

Windows + POSIX shapes, symlink escapes, 8.3 short names, UNC shares, and
the over-block guards that keep ordinary workspace writes flowing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import dream.tools as tools
from dream.security.pathsafety import check_write_path, is_sensitive_path

# -- POSIX system + credential surfaces -------------------------------------- #


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "/etc/../etc/shadow",
        "/usr/bin/evil",
        "/boot/vmlinuz",
        "/var/log/syslog",
        "/lib/x.so",
        "/root/.bashrc",
        "/sys/class",
    ],
)
def test_posix_system_paths_are_denied(path: str) -> None:
    hit = is_sensitive_path(path)
    assert hit is not None, path
    assert "system directory" in hit.reason_en
    assert hit.reason_fa  # bilingual


def test_home_credential_directories_are_denied() -> None:
    home = Path.home()
    for sub in (".ssh/id_rsa", ".ssh/authorized_keys", ".aws/credentials", ".gnupg/secring"):
        hit = is_sensitive_path(home / sub)
        assert hit is not None, sub
        assert "credentials" in hit.reason_en


@pytest.mark.parametrize(
    "name",
    [".env", ".env.production", ".netrc", ".git-credentials", "id_ed25519", "known_hosts"],
)
def test_credential_file_names_are_denied_anywhere(tmp_path: Path, name: str) -> None:
    assert is_sensitive_path(tmp_path / "project" / name) is not None


def test_dream_stores_and_private_dirs_are_denied(tmp_path: Path) -> None:
    for store in ("dream-bounded.db", "dream-session-index.db", "dream-skills.db",
                  "gateway_tokens.json"):
        assert is_sensitive_path(tmp_path / "data" / store) is not None, store
    assert is_sensitive_path(tmp_path / ".dream" / "anything") is not None
    assert is_sensitive_path(tmp_path / "data" / "provenance" / "p.jsonl") is not None


# -- Windows + UNC + 8.3 surfaces --------------------------------------------- #


@pytest.mark.parametrize(
    "path",
    [
        "C:/Windows/System32/config",
        "c:/windows/explorer.exe",
        "C:/Program Files/App/x.dll",
        "C:/Program Files (x86)/App/x.dll",
        "C:/Users/x/AppData/Roaming/steal.txt",
        "D:/AppData/Local/x",
    ],
)
def test_windows_system_paths_are_denied(path: str) -> None:
    hit = is_sensitive_path(path)
    assert hit is not None, path


@pytest.mark.parametrize("path", ["\\\\server\\share\\file.txt", "//nas/backups/x"])
def test_unc_paths_are_denied(path: str) -> None:
    hit = is_sensitive_path(path)
    assert hit is not None
    assert "network share" in hit.reason_en


@pytest.mark.parametrize("path", ["PROGRA~1/app.exe", "sub/DOCUME~1/x.txt", "C:/PROGRA~1/x"])
def test_8_3_short_names_are_denied(path: str) -> None:
    hit = is_sensitive_path(path)
    assert hit is not None
    assert "8.3" in hit.reason_en


def test_check_write_path_raises_bilingually() -> None:
    with pytest.raises(PermissionError) as exc:
        check_write_path("/etc/passwd")
    message = str(exc.value)
    assert "write refused" in message
    assert "\u0646\u0648\u0634\u062a\u0646 \u0631\u062f \u0634\u062f" in message


# -- over-block guards ---------------------------------------------------------- #


@pytest.mark.parametrize(
    "path",
    [
        "notes/today.txt",
        "skills/my-skill/SKILL.md",
        "skills/my-skill/references/soil.md",
        "build/out/report.html",
        "dataset.csv",
        "environment-plan.md",  # contains "env" but is not a .env file
    ],
)
def test_benign_workspace_paths_pass(tmp_path: Path, path: str) -> None:
    assert is_sensitive_path(tmp_path / path) is None


# -- the wired tool surface ------------------------------------------------------ #


def test_write_note_refuses_a_sensitive_target_inside_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", tmp_path.resolve())
    with pytest.raises(PermissionError, match="write refused"):
        tools.write_note(".env", "SECRET=x")
    assert not (tmp_path / ".env").exists()
    # ordinary writes still work
    tools.write_note("notes/ok.txt", "hello")
    assert (tmp_path / "notes" / "ok.txt").read_text(encoding="utf-8") == "hello"


def test_write_note_refuses_symlinked_escape_to_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "id_rsa"
    secret.write_text("PRIVATE", encoding="utf-8")
    (workspace / "sneaky").symlink_to(outside)
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", workspace.resolve())
    # _safe_path's resolve() + relative_to already catches the escape; the
    # denylist is the second opinion — both must refuse.
    with pytest.raises(PermissionError):
        tools.write_note("sneaky/id_rsa", "replaced")
    assert secret.read_text(encoding="utf-8") == "PRIVATE"


def test_skill_writes_consult_the_denylist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A skill whose resolved path carries a sensitive component is refused
    # by the denylist even though it stays inside the workspace.
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", workspace.resolve())
    monkeypatch.setenv("DREAM_SKILLS_DB", str(tmp_path / "ledger.db"))
    import dream.skills as skills

    with pytest.raises(PermissionError, match="write refused"):
        skills.save_skill_md("provenance", "when tracing", "body")
    # …while an ordinary skill writes without trouble.
    relative = skills.save_skill_md("tea-brewing", "when brewing", "steps")
    assert (workspace / relative).exists()
