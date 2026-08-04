"""Tests for the user_id tenant column on memories and journal."""

from __future__ import annotations

import sqlite3

from dream.memory import MemoryStore

_PRE_CHANGE_SCHEMA = """
CREATE TABLE memories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE INDEX idx_memories_kind ON memories(kind);
CREATE INDEX idx_memories_archived ON memories(archived);

CREATE VIRTUAL TABLE memories_fts USING fts5(
    norm,
    tags,
    content='memories',
    content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);

CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, norm, tags) VALUES (new.id, new.norm, new.tags);
END;

CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, norm, tags)
    VALUES ('delete', old.id, old.norm, old.tags);
END;

CREATE TRIGGER memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, norm, tags)
    VALUES ('delete', old.id, old.norm, old.tags);
    INSERT INTO memories_fts(rowid, norm, tags) VALUES (new.id, new.norm, new.tags);
END;

CREATE TABLE journal (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT ''
);

CREATE INDEX idx_journal_session ON journal(session_id);
"""


def _make_legacy_db(path: str, content: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_PRE_CHANGE_SCHEMA)
    conn.execute(
        """INSERT INTO memories
           (kind, content, norm, tags, importance, created_at, last_used_at, source, archived)
           VALUES (?, ?, ?, '[]', 0.5, 1700000000.0, 1700000000.0, '', 0)""",
        ("semantic", content, content),
    )
    conn.execute(
        "INSERT INTO journal (ts, role, content, session_id) VALUES (?, ?, ?, ?)",
        (1700000000.0, "user", "old journal line", ""),
    )
    conn.commit()
    conn.close()


def test_legacy_database_is_migrated_and_rows_read_as_local(tmp_path):
    db = tmp_path / "dream.db"
    _make_legacy_db(str(db), "I like dark coffee")
    with MemoryStore(str(db)) as store:
        mems = store.all(limit=100)
        assert len(mems) == 1
        assert mems[0].content == "I like dark coffee"
        rows = store.conn.execute(
            "SELECT user_id FROM memories"
        ).fetchall()
        assert all(r["user_id"] == "local" for r in rows)
        journal_rows = store.conn.execute(
            "SELECT user_id FROM journal"
        ).fetchall()
        assert all(r["user_id"] == "local" for r in journal_rows)


def test_migration_is_idempotent(tmp_path):
    db = tmp_path / "dream.db"
    _make_legacy_db(str(db), "first memory")
    with MemoryStore(str(db)) as store:
        store.remember("second memory")
    # Opening a second time must not alter counts or raise.
    with MemoryStore(str(db)) as store:
        rows = store.conn.execute(
            "SELECT COUNT(*) AS n FROM memories"
        ).fetchone()["n"]
        assert rows == 2
        for table in ("memories", "journal"):
            cols = [r["name"] for r in store.conn.execute(f"PRAGMA table_info({table})")]
            assert cols.count("user_id") == 1
        indexed = [
            r["name"] for r in store.conn.execute("PRAGMA index_info(idx_memories_user)")
        ]
        assert indexed == ["user_id"]


def test_two_users_writing_same_content_produce_two_rows(tmp_path):
    with MemoryStore(str(tmp_path / "dream.db"), user="alice") as a:
        a.remember("shared fact")
    with MemoryStore(str(tmp_path / "dream.db"), user="bob") as b:
        b.remember("shared fact")
        assert len(b.all(limit=100)) == 1
    with MemoryStore(str(tmp_path / "dream.db"), user="alice") as a:
        assert len(a.all(limit=100)) == 1
    raw = sqlite3.connect(str(tmp_path / "dream.db"))
    try:
        rows = raw.execute("SELECT user_id FROM memories ORDER BY user_id").fetchall()
        assert rows == [("alice",), ("bob",)]
    finally:
        raw.close()


def test_recall_isolation_between_users(tmp_path):
    with MemoryStore(str(tmp_path / "dream.db"), user="alice") as a:
        a.remember("alice secret project")
    with MemoryStore(str(tmp_path / "dream.db"), user="bob") as b:
        b.remember("bob secret project")
        hits = b.recall("secret project", limit=10)
        assert [m.content for m in hits] == ["bob secret project"]
        assert [m.content for m in b.all(limit=100)] == ["bob secret project"]


def test_forget_cannot_touch_another_users_memory(tmp_path):
    with MemoryStore(str(tmp_path / "dream.db"), user="alice") as a:
        m = a.remember("do not touch me")
    with MemoryStore(str(tmp_path / "dream.db"), user="bob") as b:
        assert b.forget(m.id) is False
    with MemoryStore(str(tmp_path / "dream.db"), user="alice") as a:
        got = a.get(m.id)
        assert got is not None
        assert got.archived is False


def test_stats_count_only_calling_user(tmp_path):
    with MemoryStore(str(tmp_path / "dream.db"), user="alice") as a:
        archived = a.remember("alice archived")
        a.remember("alice active")
        a.forget(archived.id)
        a.log("user", "alice journal line")
    with MemoryStore(str(tmp_path / "dream.db"), user="bob") as b:
        b.remember("bob one")
        b.log("user", "bob journal line")
        s = b.stats()
        assert (s["total"], s["archived"], s["journal"]) == (1, 0, 1)
    with MemoryStore(str(tmp_path / "dream.db"), user="alice") as a:
        s = a.stats()
        assert (s["total"], s["archived"], s["journal"]) == (1, 1, 1)


def test_fts_matches_pre_migration_rows(tmp_path):
    db = tmp_path / "dream.db"
    _make_legacy_db(str(db), "قهوه تلخ دوست دارم")
    with MemoryStore(str(db)) as store:
        fts_rows = store.conn.execute(
            "SELECT rowid FROM memories_fts WHERE memories_fts MATCH ?",
            ("قهوه",),
        ).fetchall()
        assert [row["rowid"] for row in fts_rows] == [1]
        hits = store.recall("قهوه تلخ", limit=10)
        assert len(hits) == 1
        assert hits[0].content == "قهوه تلخ دوست دارم"


def test_dream_user_env_var_honoured(monkeypatch, tmp_path):
    monkeypatch.setenv("DREAM_USER", "zahra")
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        assert store.user_id == "zahra"
        store.remember("zahra memory")
    with MemoryStore(str(tmp_path / "dream.db"), user="local") as local:
        assert local.all(limit=10) == []
    with MemoryStore(str(tmp_path / "dream.db"), user="zahra") as z:
        assert len(z.all(limit=10)) == 1


def test_unset_dream_user_defaults_to_local(monkeypatch, tmp_path):
    monkeypatch.delenv("DREAM_USER", raising=False)
    with MemoryStore(str(tmp_path / "dream.db")) as store:
        assert store.user_id == "local"


def test_recent_journal_is_isolated_by_user(tmp_path):
    with MemoryStore(str(tmp_path / "dream.db"), user="alice") as a:
        a.log("user", "alice hi")
    with MemoryStore(str(tmp_path / "dream.db"), user="bob") as b:
        b.log("user", "bob hi")
        rows = b.recent_journal(limit=10)
        assert len(rows) == 1
        assert rows[0]["content"] == "bob hi"
