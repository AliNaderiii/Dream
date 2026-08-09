"""Tests for Windows reserved device names and trailing-dot handling.

What this pins and what evidence justified it:

- The skill name validator and the note writer must refuse every Windows
  reserved base name (CON, PRN, AUX, NUL, COM1-9, LPT1-9) case-insensitively,
  bare and with any extension, because on Windows those names are device
  aliases that cannot be deleted with ordinary tools (brief defect, measured
  on merged trunk: all accepted before).
- Ordinary names that merely begin with a reserved word must stay accepted
  (conference, control, contact list, common tasks, aux ideas) — prefix trap
  pinned by measured legitimate list.
- Persian digit folding runs before the check: COM + Persian 1 folds to COM1
  and must be refused (brief second trap, measured via normalize_fa).
- Trailing dot is refused (Windows strips it, collision hazard measured).
- Both writing surfaces refuse (save_skill via validate_name and write_note
  via safe_path) and leave nothing behind (data integrity veto).
- Placement is a single helper in tools; both surfaces call it (argued in
  status document).
"""

from __future__ import annotations

import json

import pytest

from dream import tools
from dream.memory import normalize_fa

# 22 reserved base names
RESERVED_BARE = [
    "con",
    "prn",
    "aux",
    "nul",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
]

LEGITIMATE_NAMES = [
    "conference",
    "control",
    "contact list",
    "common tasks",
    "aux ideas",
]


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", tmp_path.resolve())
    return tmp_path


def _save_skill_payload(name: str):
    return json.loads(
        tools.execute(
            "save_skill",
            {"name": name, "description": "x", "steps": ["y"]},
        )
    )


def _write_note_payload(filename: str):
    return json.loads(
        tools.execute("write_note", {"filename": filename, "content": "hello"})
    )


class TestReservedBareLowercase:
    @pytest.mark.parametrize("name", RESERVED_BARE)
    def test_skill_refuses_bare_lowercase(self, workspace, name):
        payload = _save_skill_payload(name)
        assert payload["status"] == "error", name
        # listing after must be empty -> nothing behind
        assert list(workspace.rglob("*")) == []

    @pytest.mark.parametrize("name", RESERVED_BARE)
    def test_note_refuses_bare_lowercase(self, workspace, name):
        payload = _write_note_payload(name)
        assert payload["status"] == "error", name
        assert list(workspace.rglob("*")) == []

    @pytest.mark.parametrize("name", RESERVED_BARE)
    def test_note_refuses_with_extension(self, workspace, name):
        payload = _write_note_payload(f"{name}.txt")
        assert payload["status"] == "error", name
        assert list(workspace.rglob("*")) == []

    @pytest.mark.parametrize("name", RESERVED_BARE)
    def test_skill_refuses_with_extension_via_validate(self, workspace, name):
        # save_skill with name "con.txt" -> stem is "con" must be refused
        payload = _save_skill_payload(f"{name}.txt")
        assert payload["status"] == "error", name
        assert list(workspace.rglob("*")) == []


class TestReservedUppercase:
    @pytest.mark.parametrize("name", RESERVED_BARE)
    def test_skill_refuses_uppercase(self, workspace, name):
        payload = _save_skill_payload(name.upper())
        assert payload["status"] == "error", name
        assert list(workspace.rglob("*")) == []

    @pytest.mark.parametrize("name", RESERVED_BARE)
    def test_note_refuses_uppercase(self, workspace, name):
        payload = _write_note_payload(name.upper())
        assert payload["status"] == "error", name
        assert list(workspace.rglob("*")) == []

    @pytest.mark.parametrize("name", RESERVED_BARE)
    def test_skill_refuses_uppercase_with_extension(self, workspace, name):
        payload = _save_skill_payload(f"{name.upper()}.txt")
        assert payload["status"] == "error", name
        assert list(workspace.rglob("*")) == []


class TestLegitimatePrefixNames:
    @pytest.mark.parametrize("name", LEGITIMATE_NAMES)
    def test_skill_accepts_legitimate(self, workspace, name):
        payload = _save_skill_payload(name)
        assert payload["status"] == "ok", payload

    @pytest.mark.parametrize("name", LEGITIMATE_NAMES)
    def test_note_accepts_legitimate(self, workspace, name):
        payload = _write_note_payload(name)
        assert payload["status"] == "ok", payload


class TestPersianDigitFolding:
    def test_com_persian_one_is_refused_skill(self, workspace):
        # Persian digit U+06F1
        name = "com\u06f1"
        assert normalize_fa(name) == "com1"
        payload = _save_skill_payload(name)
        assert payload["status"] == "error"
        assert list(workspace.rglob("*")) == []

    def test_lpt_persian_nine_is_refused_note(self, workspace):
        name = "lpt\u06f9.txt"
        assert normalize_fa(name).lower().startswith("lpt9")
        payload = _write_note_payload(name)
        assert payload["status"] == "error"
        assert list(workspace.rglob("*")) == []

    def test_persian_digit_side_of_folding(self, workspace):
        # rule runs after folding, prove with folded and unfolded spellings
        # unfolded: Persian digit, folded: Latin digit, both refused
        for variant in ["com\u06f1", "com1"]:
            payload = _save_skill_payload(variant)
            assert payload["status"] == "error", variant
            # clean up workspace between variants
            for p in workspace.rglob("*"):
                if p.is_file():
                    p.unlink()


class TestTrailingDot:
    def test_skill_trailing_dot_refused(self, workspace):
        payload = _save_skill_payload("report.")
        assert payload["status"] == "error"
        assert list(workspace.rglob("*")) == []

    def test_note_trailing_dot_refused(self, workspace):
        payload = _write_note_payload("report.")
        assert payload["status"] == "error"
        assert list(workspace.rglob("*")) == []

    def test_skill_trailing_dot_after_reserved_refused(self, workspace):
        payload = _save_skill_payload("con.")
        assert payload["status"] == "error"
        assert list(workspace.rglob("*")) == []

    def test_refused_leaves_nothing_behind(self, workspace):
        payload = _save_skill_payload("con")
        assert payload["status"] == "error"
        # directory listing after must be empty, no skills dir
        assert list(workspace.rglob("*")) == []
        payload2 = _write_note_payload("nul.txt")
        assert payload2["status"] == "error"
        assert list(workspace.rglob("*")) == []


class TestMessages:
    def test_skill_message_mentions_reserved(self, workspace):
        payload = _save_skill_payload("con")
        msg = payload["error"]["message"]
        assert "con" in msg.lower() or "reserved" in msg.lower()

    def test_note_message_mentions_reserved(self, workspace):
        payload = _write_note_payload("aux.md")
        msg = payload["error"]["message"]
        assert "aux" in msg.lower() or "reserved" in msg.lower()
