"""Conservative semantic-memory supersession and pinning tests."""

from __future__ import annotations

import sqlite3

import pytest

import cli
from dream.agent import Dream, EchoBackend
from dream.memory import DEFAULT_CONTRADICTION_THRESHOLD, MemoryStore


@pytest.fixture()
def store(tmp_path):
    memory_store = MemoryStore(str(tmp_path / "dream.db"))
    yield memory_store
    memory_store.close()


def test_contradiction_archives_older_row_and_links_replacement(store):
    old = store.remember("the user lives in Tehran", kind="semantic")
    new = store.remember("the user lives in Shiraz", kind="semantic")

    replaced = store.get(old.id)
    assert replaced is not None
    assert replaced.archived is True
    assert replaced.superseded_by == new.id


def test_recall_returns_only_newer_contradicting_fact(store):
    store.remember("the user lives in Tehran", kind="semantic")
    store.remember("the user lives in Shiraz", kind="semantic")

    hits = store.recall("where do I live", reinforce=False)
    assert [memory.content for memory in hits] == ["the user lives in Shiraz"]


def test_one_shared_word_never_supersedes_unrelated_semantic_fact(store):
    first = store.remember("coffee tastes bitter", kind="semantic")
    store.remember("coffee plants need rain", kind="semantic")

    assert store.get(first.id, include_archived=False) is not None


def test_episodic_memories_are_never_superseded(store):
    first = store.remember("the user lives in Tehran", kind="episodic")
    second = store.remember("the user lives in Shiraz", kind="episodic")

    assert store.get(first.id, include_archived=False) is not None
    assert store.get(second.id, include_archived=False) is not None


def test_procedural_memories_are_never_superseded(store):
    first = store.remember("the user lives in Tehran", kind="procedural")
    second = store.remember("the user lives in Shiraz", kind="procedural")

    assert store.get(first.id, include_archived=False) is not None
    assert store.get(second.id, include_archived=False) is not None


def test_supersession_never_crosses_users(tmp_path):
    path = str(tmp_path / "dream.db")
    with MemoryStore(path, user="bob") as bob:
        bob_old = bob.remember("the user lives in Tehran")
    with MemoryStore(path, user="alice") as alice:
        alice_old = alice.remember("the user lives in Tehran")
        alice.remember("the user lives in Shiraz")
        assert alice.get(alice_old.id).archived is True
    with MemoryStore(path, user="bob") as bob:
        untouched = bob.get(bob_old.id)
        assert untouched is not None
        assert untouched.archived is False
        assert untouched.superseded_by is None


def test_superseded_row_remains_reachable_through_get(store):
    old = store.remember("the user lives in Tehran")
    store.remember("the user lives in Shiraz")

    archived = store.get(old.id)
    assert archived is not None
    assert archived.content == "the user lives in Tehran"
    assert archived.archived is True


def test_pinned_memory_is_never_superseded(store):
    old = store.remember("the user lives in Tehran")
    assert store.pin(old.id) is True
    store.remember("the user lives in Shiraz")

    protected = store.get(old.id)
    assert protected is not None
    assert protected.pinned is True
    assert protected.archived is False
    assert protected.superseded_by is None


def test_pinning_survives_database_reopen(tmp_path):
    path = str(tmp_path / "dream.db")
    with MemoryStore(path) as first:
        memory = first.remember("the user lives in Tehran")
        assert first.pin(memory.id) is True
    with MemoryStore(path) as reopened:
        protected = reopened.get(memory.id)
        assert protected is not None
        assert protected.pinned is True


_PRE_SUPERSESSION_SCHEMA = """
CREATE TABLE memories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      TEXT    NOT NULL DEFAULT 'local',
    kind         TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    norm         TEXT    NOT NULL,
    tags         TEXT    NOT NULL DEFAULT '[]',
    importance   REAL    NOT NULL DEFAULT 0.5,
    created_at   REAL    NOT NULL,
    last_used_at REAL    NOT NULL,
    use_count    INTEGER NOT NULL DEFAULT 0,
    source       TEXT    NOT NULL DEFAULT '',
    archived     INTEGER NOT NULL DEFAULT 0
);
"""


def test_migration_adds_pinned_and_superseded_by_columns(tmp_path):
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.executescript(_PRE_SUPERSESSION_SCHEMA)
    conn.execute(
        """INSERT INTO memories
           (user_id, kind, content, norm, created_at, last_used_at)
           VALUES ('local', 'semantic', 'legacy fact', 'legacy fact', 1.0, 1.0)"""
    )
    conn.commit()
    conn.close()

    with MemoryStore(path) as migrated:
        columns = {
            row["name"] for row in migrated.conn.execute("PRAGMA table_info(memories)")
        }
        assert {"pinned", "superseded_by"} <= columns
        memory = migrated.get(1)
        assert memory is not None
        assert memory.pinned is False
        assert memory.superseded_by is None


def test_cli_pin_command_protects_memory(store):
    memory = store.remember("the user lives in Tehran")
    output: list[str] = []

    assert cli.dispatch_command(f"/pin {memory.id}", Dream(store, EchoBackend()), output.append)
    assert output == ["Memory pinned."]
    assert store.get(memory.id).pinned is True


class _ContradictionBackend:
    def chat(self, messages, tools=None):
        del messages
        if tools is not None:
            return {"content": "Recorded.", "tool_calls": []}
        return {
            "content": (
                '[{"content": "the user lives in Shiraz", '
                '"kind": "semantic", "importance": 0.8}]'
            ),
            "tool_calls": [],
        }


def _feeding_input(lines):
    iterator = iter(lines)

    def read(_prompt=""):
        try:
            return next(iterator)
        except StopIteration:
            raise EOFError from None

    return read


@pytest.mark.parametrize(("quiet", "visible"), [(False, True), (True, False)])
def test_cli_reports_supersession_unless_quiet(tmp_path, monkeypatch, capsys, quiet, visible):
    path = str(tmp_path / "cli.db")
    with MemoryStore(path) as seed:
        seed.remember("the user lives in Tehran")

    monkeypatch.setattr("dream.agent.build_backend", lambda _kind=None: _ContradictionBackend())
    monkeypatch.setattr(
        "builtins.input",
        _feeding_input(["I moved recently and now live somewhere else permanently."]),
    )
    arguments = ["--db", path]
    if quiet:
        arguments.insert(0, "--quiet")

    assert cli.main(arguments) == 0
    lines = capsys.readouterr().err.splitlines()
    expected = "[memory] superseded #1 (the user lives in Tehran)"
    assert (expected in lines) is visible


def test_environment_threshold_override_changes_the_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_CONTRADICTION_THRESHOLD", "0.75")
    with MemoryStore(str(tmp_path / "override.db")) as overridden:
        old = overridden.remember("account status is active")
        overridden.remember("account status is inactive")
        assert overridden.contradiction_threshold == 0.75
        assert overridden.get(old.id).archived is True


@pytest.mark.parametrize("raw", ["not-a-number", "-0.01", "1.01", "nan"])
def test_invalid_environment_threshold_falls_back_without_raising(tmp_path, monkeypatch, raw):
    monkeypatch.setenv("DREAM_CONTRADICTION_THRESHOLD", raw)
    with MemoryStore(str(tmp_path / "fallback.db")) as fallback:
        assert fallback.contradiction_threshold == DEFAULT_CONTRADICTION_THRESHOLD


def test_coexisting_values_at_three_quarter_overlap_are_kept(store):
    """Do not erase one language just because the user also speaks another."""
    first = store.remember("the user speaks Persian")
    second = store.remember("the user speaks English")

    assert store.get(first.id, include_archived=False) is not None
    assert store.get(second.id, include_archived=False) is not None
