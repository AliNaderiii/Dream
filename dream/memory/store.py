"""SQLite-backed associative memory store with FTS5, decay, and hybrid retrieval."""

from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from dream.memory.models import _MISSING, KINDS, Memory
from dream.memory.normalization import (
    _CANONICAL_MAP,
    _canonicalise_stems,
    _is_contradiction,
    _is_duplicate,
    _resolve_contradiction_threshold,
    _resolve_duplicate_threshold,
    _stem_fa,
    _stemmed_tokens,
    _tokenize,
    build_match_query,
    normalize_fa,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      TEXT    NOT NULL DEFAULT 'local',
    kind         TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    norm         TEXT    NOT NULL,
    tags         TEXT    NOT NULL DEFAULT '[]',
    importance   REAL    NOT NULL DEFAULT 0.5,
    created_at   REAL    NOT NULL,
    last_used_at REAL    NOT NULL,
    use_count      INTEGER NOT NULL DEFAULT 0,
    source         TEXT    NOT NULL DEFAULT '',
    archived       INTEGER NOT NULL DEFAULT 0,
    superseded_by  INTEGER,
    pinned         INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);
CREATE INDEX IF NOT EXISTS idx_memories_archived ON memories(archived);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    norm,
    tags,
    content='memories',
    content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, norm, tags) VALUES (new.id, new.norm, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, norm, tags)
    VALUES ('delete', old.id, old.norm, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, norm, tags)
    VALUES ('delete', old.id, old.norm, old.tags);
    INSERT INTO memories_fts(rowid, norm, tags) VALUES (new.id, new.norm, new.tags);
END;

CREATE TABLE IF NOT EXISTS journal (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT    NOT NULL DEFAULT 'local',
    ts         REAL NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_journal_session ON journal(session_id);

CREATE TABLE IF NOT EXISTS reminders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        TEXT    NOT NULL DEFAULT 'local',
    text           TEXT    NOT NULL,
    due_at         REAL    NOT NULL,
    next_due       REAL    NOT NULL,
    repeat_days    INTEGER,
    repeat_months  INTEGER,
    last_fired_at  REAL,
    created_at     REAL    NOT NULL,
    active         INTEGER NOT NULL DEFAULT 1,
    anchor_day     INTEGER
);

CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_at);
CREATE INDEX IF NOT EXISTS idx_reminders_active ON reminders(active);
"""

# Hybrid scoring weights.
W_RELEVANCE = 0.55
W_RECENCY = 0.20
W_IMPORTANCE = 0.15
W_USAGE = 0.10

HALF_LIFE_SECONDS = 30 * 24 * 3600.0



def _get_is_duplicate() -> Any:
    import dream.memory as memory_mod
    return getattr(memory_mod, "_is_duplicate", _is_duplicate)

def _get_is_contradiction() -> Any:
    import dream.memory as memory_mod
    return getattr(memory_mod, "_is_contradiction", _is_contradiction)

def _get_canonical_map() -> dict[str, str]:
    import dream.memory as memory_mod
    return getattr(memory_mod, "_CANONICAL_MAP", _CANONICAL_MAP)
class MemoryStore:
    """SQLite-backed memory: one file, no external service.

    The store is safe to share across threads: the connection is opened with
    ``check_same_thread=False`` and every method that touches it runs under
    one re-entrant lock.  Both halves are required — the flag alone only
    silences the cross-thread exception while concurrent writes still lose
    rows.  The lock is an ``RLock`` because methods call each other while
    holding it (``remember`` into ``get``, ``recall`` into ``_like_scan``), so
    a plain ``Lock`` would deadlock.  WAL mode stays on: it is what keeps a
    reader cheap while one writer holds the lock.
    """

    def __init__(
        self,
        path: str = "data/dream.db",
        user: str | None = None,
    ) -> None:
        self.path = str(path)
        self.user_id = user if user is not None else os.environ.get("DREAM_USER", "local")
        if not isinstance(self.user_id, str) or not self.user_id:
            raise ValueError("user must be a non-empty string")
        self.contradiction_threshold = _resolve_contradiction_threshold(
            os.environ.get("DREAM_CONTRADICTION_THRESHOLD")
        )
        self.duplicate_threshold = _resolve_duplicate_threshold(
            os.environ.get("DREAM_DUPLICATE_THRESHOLD")
        )
        self._lock = threading.RLock()
        if self.path != ":memory:":
            parent = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(_SCHEMA)
        self._ensure_user_column()
        self._ensure_supersession_columns()
        self._ensure_reminders_table()
        self.conn.commit()

    def _ensure_user_column(self) -> None:
        """Backfill user_id on databases created before this column existed.

        Idempotent: PRAGMA table_info tells us whether the column is present;
        running twice is a no-op.  Existing rows inherit the DEFAULT 'local'.
        The index is created with IF NOT EXISTS so it appears on both fresh
        and migrated files, and never errors on a repeat open.
        """
        for table in ("memories", "journal"):
            cols = {
                row["name"]
                for row in self.conn.execute(f"PRAGMA table_info({table})")
            }
            if "user_id" not in cols:
                self.conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'"
                )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id)")

    def _ensure_supersession_columns(self) -> None:
        """Add supersession state to databases created before this feature."""
        cols = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(memories)")
        }
        if "superseded_by" not in cols:
            self.conn.execute("ALTER TABLE memories ADD COLUMN superseded_by INTEGER")
        if "pinned" not in cols:
            self.conn.execute(
                "ALTER TABLE memories ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0"
            )

    def _ensure_reminders_table(self) -> None:
        """Create reminders table and add missing columns for old databases."""
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS reminders (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        TEXT    NOT NULL DEFAULT 'local',
                text           TEXT    NOT NULL,
                due_at         REAL    NOT NULL,
                next_due       REAL    NOT NULL,
                repeat_days    INTEGER,
                repeat_months  INTEGER,
                last_fired_at  REAL,
                created_at     REAL    NOT NULL,
                active         INTEGER NOT NULL DEFAULT 1,
                anchor_day     INTEGER
            )"""
        )
        cols = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(reminders)")
        }
        if "text" not in cols:
            self.conn.execute(
                "ALTER TABLE reminders ADD COLUMN text TEXT NOT NULL DEFAULT ''"
            )
        if "due_at" not in cols:
            self.conn.execute(
                "ALTER TABLE reminders ADD COLUMN due_at REAL NOT NULL DEFAULT 0"
            )
        if "next_due" not in cols:
            self.conn.execute("ALTER TABLE reminders ADD COLUMN next_due REAL")
            self.conn.execute(
                "UPDATE reminders SET next_due = due_at WHERE next_due IS NULL"
            )
        if "repeat_days" not in cols:
            self.conn.execute("ALTER TABLE reminders ADD COLUMN repeat_days INTEGER")
        if "repeat_months" not in cols:
            self.conn.execute("ALTER TABLE reminders ADD COLUMN repeat_months INTEGER")
        if "last_fired_at" not in cols:
            self.conn.execute("ALTER TABLE reminders ADD COLUMN last_fired_at REAL")
        if "created_at" not in cols:
            self.conn.execute(
                "ALTER TABLE reminders ADD COLUMN created_at REAL NOT NULL DEFAULT 0"
            )
        if "active" not in cols:
            self.conn.execute(
                "ALTER TABLE reminders ADD COLUMN active INTEGER NOT NULL DEFAULT 1"
            )
        if "anchor_day" not in cols:
            self.conn.execute("ALTER TABLE reminders ADD COLUMN anchor_day INTEGER")
            # Backfill anchor from existing due dates — best info available
            rows = list(
                self.conn.execute(
                    "SELECT id, due_at FROM reminders WHERE anchor_day IS NULL"
                )
            )
            for row in rows:
                try:
                    import datetime

                    from dream.jalali import gregorian_to_jalali

                    dt = datetime.datetime.fromtimestamp(
                        float(row["due_at"]), tz=datetime.timezone.utc
                    )
                    _, _, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
                    self.conn.execute(
                        "UPDATE reminders SET anchor_day = ? WHERE id = ?",
                        (jd, row["id"]),
                    )
                except Exception:
                    continue
        if "user_id" not in cols:
            self.conn.execute(
                "ALTER TABLE reminders ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'"
            )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_at)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reminders_active ON reminders(active)"
        )
        self.conn.execute("""CREATE TABLE IF NOT EXISTS reminder_deliveries (
            reminder_id INTEGER NOT NULL, destination TEXT NOT NULL,
            fired_at REAL NOT NULL, delivered_at REAL NOT NULL,
            PRIMARY KEY (reminder_id, destination, fired_at),
            FOREIGN KEY (reminder_id) REFERENCES reminders(id) ON DELETE CASCADE
        )""")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS reminder_destinations (
            user_id TEXT NOT NULL, destination TEXT NOT NULL, first_seen REAL NOT NULL,
            PRIMARY KEY (user_id, destination)
        )""")
        self._migrate_reminder_deliveries_cascade()

    def _migrate_reminder_deliveries_cascade(self) -> None:
        """Rebuild reminder_deliveries with ON DELETE CASCADE on old databases.

        The delivery table references ``reminders(id)``. Without
        ``ON DELETE CASCADE`` a reminder that has already fired — and
        therefore owns delivery rows — cannot be deleted: the foreign key
        raises ``IntegrityError`` and the row survives. Fresh databases are
        created with the cascade (see :meth:`_ensure_reminders_table`), so this
        only rebuilds the table on databases created before the cascade
        existed.

        Idempotent: the stored schema text is read back and the rebuild runs
        only when the cascade is absent, so opening the same file twice changes
        nothing the second time. The rebuild copies every row to a new table,
        drops the old one, and renames the new one into place, all inside one
        transaction so an interrupted migration can never lose rows while leaving
        the new table absent.

        The ``foreign_keys`` pragma is turned off BEFORE the transaction and
        back on after it commits: SQLite silently ignores the switch while a
        transaction is open (verified in ``tests/test_m21_fk_cascade.py``), so
        setting it inside the transaction would leave enforcement on and the
        rebuild unable to move the child table.
        """
        schema = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='reminder_deliveries'"
        ).fetchone()
        if schema is None or not schema[0]:
            return  # table not created yet; nothing to migrate
        if "ON DELETE CASCADE" in schema[0].upper():
            return  # already cascades — idempotent, a no-op second open
        # Commit any pending transaction from the schema-setup DDL before
        # touching the pragma: PRAGMA foreign_keys is a no-op inside a
        # transaction (trap two), and _ensure_reminders_table may have left an
        # open implicit transaction. Committing first guarantees the switch is
        # applied outside any transaction.
        self.conn.commit()
        # Turn enforcement off before opening the transaction. See trap two:
        # the pragma is a no-op inside a transaction, so it MUST go here.
        self.conn.execute("PRAGMA foreign_keys = OFF")
        # Read it back and prove the switch took effect: if this pragma were
        # (mis)placed inside the transaction, SQLite would silently ignore it
        # and the read-back would still be 1 — the rebuild would then proceed
        # under enforcement and could fail loudly on a schema it cannot move.
        fk_off = self.conn.execute("PRAGMA foreign_keys").fetchone()[0]
        if fk_off != 0:
            raise RuntimeError(
                "could not disable foreign key enforcement before rebuilding "
                "reminder_deliveries: the PRAGMA foreign_keys switch is a no-op "
                "inside a transaction, so it must be set before BEGIN"
            )
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(
                """CREATE TABLE reminder_deliveries_new (
                    reminder_id INTEGER NOT NULL, destination TEXT NOT NULL,
                    fired_at REAL NOT NULL, delivered_at REAL NOT NULL,
                    PRIMARY KEY (reminder_id, destination, fired_at),
                    FOREIGN KEY (reminder_id) REFERENCES reminders(id) ON DELETE CASCADE
                )"""
            )
            self.conn.execute(
                """INSERT INTO reminder_deliveries_new
                       (reminder_id, destination, fired_at, delivered_at)
                   SELECT reminder_id, destination, fired_at, delivered_at
                   FROM reminder_deliveries"""
            )
            self.conn.execute("DROP TABLE reminder_deliveries")
            self.conn.execute(
                "ALTER TABLE reminder_deliveries_new RENAME TO reminder_deliveries"
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            self.conn.execute("PRAGMA foreign_keys = ON")

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def __enter__(self) -> MemoryStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- writing -----------------------------------------------------------

    def remember(
        self,
        content: str,
        kind: str = "semantic",
        tags: Sequence[str] | None = None,
        importance: float = 0.5,
        source: str = "",
        on_supersede: Callable[[Memory], None] | None = None,
        on_merge: Callable[[Memory], None] | None = None,
    ) -> Memory:
        """Store a memory, or boost the existing one if it is a duplicate."""
        with self._lock:
            if kind not in KINDS:
                raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
            content = content.strip()
            if not content:
                raise ValueError("content must not be empty")
            norm = normalize_fa(content)
            tag_list = [normalize_fa(t) for t in (tags or []) if t.strip()]
            now = time.time()

            existing = self.conn.execute(
                """SELECT * FROM memories
                   WHERE user_id = ? AND norm = ? AND kind = ? AND archived = 0""",
                (self.user_id, norm, kind),
            ).fetchone()
            if existing is not None:
                boosted = min(1.0, float(existing["importance"]) + 0.1)
                merged = sorted(set(json.loads(existing["tags"] or "[]")) | set(tag_list))
                self.conn.execute(
                    """UPDATE memories SET importance = ?, tags = ?, last_used_at = ?
                       WHERE user_id = ? AND id = ?""",
                    (
                        boosted,
                        json.dumps(merged, ensure_ascii=False),
                        now,
                        self.user_id,
                        existing["id"],
                    ),
                )
                self.conn.commit()
                return self.get(existing["id"])  # type: ignore[return-value]

            # Semantic candidates: same user, kind, not archived, not pinned.
            # Fetched once and reused for both duplicate and contradiction
            # checks rather than issuing two queries.
            semantic_candidates: list[sqlite3.Row] = []
            if kind == "semantic":
                semantic_candidates = self.conn.execute(
                    """SELECT * FROM memories
                       WHERE user_id = ? AND kind = 'semantic'
                         AND archived = 0 AND pinned = 0
                       ORDER BY id""",
                    (self.user_id,),
                ).fetchall()

            # Near-duplicate detection: same fact said slightly differently.
            # Runs after exact dedupe and before contradiction detection, so a
            # true duplicate never reaches the supersede path.
            if kind == "semantic":
                new_stems = _canonicalise_stems(_stemmed_tokens(norm), _get_canonical_map())
                candidate_stems = [
                    (
                        row,
                        _canonicalise_stems(
                            _stemmed_tokens(str(row["norm"])), _get_canonical_map()
                        ),
                    )
                    for row in semantic_candidates
                ]
                duplicate_target: sqlite3.Row | None = None
                for row, old_stems in candidate_stems:
                    if _get_is_duplicate()(
                        old_stems,
                        new_stems,
                        self.duplicate_threshold,
                        _get_canonical_map(),
                    ):
                        duplicate_target = row
                        break  # oldest by id wins
                if duplicate_target is not None:
                    old_importance = float(duplicate_target["importance"])
                    new_importance = float(importance)
                    merged_importance = min(1.0, max(old_importance, new_importance) + 0.1)
                    old_tags = set(json.loads(duplicate_target["tags"] or "[]"))
                    merged_tags = sorted(old_tags | set(tag_list))
                    self.conn.execute(
                        """UPDATE memories
                           SET importance = ?, tags = ?, last_used_at = ?
                           WHERE user_id = ? AND id = ?""",
                        (
                            merged_importance,
                            json.dumps(merged_tags, ensure_ascii=False),
                            now,
                            self.user_id,
                            duplicate_target["id"],
                        ),
                    )
                    self.conn.commit()
                    merged_memory = self.get(duplicate_target["id"])
                    if on_merge is not None and merged_memory is not None:
                        on_merge(merged_memory)
                    return merged_memory  # type: ignore[return-value]

            contradictions: list[Memory] = []
            if kind == "semantic":
                contradictions = [
                    Memory.from_row(row)
                    for row in semantic_candidates
                    if _get_is_contradiction()(
                        str(row["norm"]), norm, self.contradiction_threshold
                    )
                ]

            cur = self.conn.execute(
                """INSERT INTO memories
                   (user_id, kind, content, norm, tags, importance, created_at, last_used_at,
                    use_count, source, archived)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0)""",
                (
                    self.user_id,
                    kind,
                    content,
                    norm,
                    json.dumps(tag_list, ensure_ascii=False),
                    float(importance),
                    now,
                    now,
                    source,
                ),
            )
            memory_id = int(cur.lastrowid)
            superseded: list[Memory] = []
            for old in contradictions:
                updated = self.conn.execute(
                    """UPDATE memories SET archived = 1, superseded_by = ?
                       WHERE user_id = ? AND id = ? AND archived = 0 AND pinned = 0""",
                    (memory_id, self.user_id, old.id),
                )
                if updated.rowcount:
                    old.archived = True
                    old.superseded_by = memory_id
                    superseded.append(old)
            self.conn.commit()
            memory = self.get(memory_id)
            if on_supersede is not None:
                for old in superseded:
                    on_supersede(old)
            return memory  # type: ignore[return-value]

    def forget(self, memory_id: int, hard: bool = False) -> bool:
        """Archive a memory (default) or delete it outright."""
        with self._lock:
            if hard:
                cur = self.conn.execute(
                    "DELETE FROM memories WHERE user_id = ? AND id = ?",
                    (self.user_id, memory_id),
                )
            else:
                cur = self.conn.execute(
                    """UPDATE memories SET archived = 1
                       WHERE user_id = ? AND id = ? AND archived = 0""",
                    (self.user_id, memory_id),
                )
            self.conn.commit()
            return cur.rowcount > 0

    def pin(self, memory_id: int) -> bool:
        """Protect one active memory from automatic supersession."""
        with self._lock:
            cur = self.conn.execute(
                """UPDATE memories SET pinned = 1
                   WHERE user_id = ? AND id = ? AND archived = 0""",
                (self.user_id, memory_id),
            )
            self.conn.commit()
            return cur.rowcount > 0

    # -- reading -----------------------------------------------------------

    def get(self, memory_id: int, include_archived: bool = True) -> Memory | None:
        with self._lock:
            sql = "SELECT * FROM memories WHERE user_id = ? AND id = ?"
            params: list[Any] = [self.user_id, memory_id]
            if not include_archived:
                sql += " AND archived = 0"
            row = self.conn.execute(sql, params).fetchone()
            return Memory.from_row(row) if row is not None else None

    def deduplicate(self, dry_run: bool = True) -> dict[str, Any]:
        """Merge old near-duplicate semantic memories in one atomic pass."""
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                rows = self.conn.execute(
                    """SELECT * FROM memories
                       WHERE user_id = ? AND kind = 'semantic'
                         AND archived = 0 AND pinned = 0""",
                    (self.user_id,),
                ).fetchall()
                # The write path merges into the oldest row, so id order is the authority.
                rows = sorted(rows, key=lambda row: int(row["id"]))
                stems = {
                    int(row["id"]): _canonicalise_stems(
                        _stemmed_tokens(str(row["norm"])), _get_canonical_map()
                    )
                    for row in rows
                }
                kept: list[sqlite3.Row] = []
                pairs: list[tuple[int, int]] = []
                details: list[tuple[int, int, str, str]] = []
                now = time.time()
                for row in rows:
                    target = next(
                        (
                            old
                            for old in kept
                            if _get_is_duplicate()(
                                stems[int(old["id"])], stems[int(row["id"])],
                                self.duplicate_threshold, _get_canonical_map()
                            )
                        ),
                        None,
                    )
                    if target is None:
                        kept.append(row)
                        continue
                    old_id, new_id = int(target["id"]), int(row["id"])
                    pairs.append((new_id, old_id))
                    details.append((old_id, new_id, str(target["content"]), str(row["content"])))
                    importance = min(
                        1.0, max(float(target["importance"]), float(row["importance"])) + 0.1
                    )
                    tags = sorted(
                        set(json.loads(target["tags"] or "[]"))
                        | set(json.loads(row["tags"] or "[]"))
                    )
                    self.conn.execute(
                        """UPDATE memories
                           SET importance = ?, tags = ?, last_used_at = ? WHERE id = ?""",
                        (importance, json.dumps(tags, ensure_ascii=False), now, old_id),
                    )
                    self.conn.execute(
                        "DELETE FROM memories WHERE user_id = ? AND id = ?",
                        (self.user_id, new_id),
                    )
                result = {
                    "examined": len(rows),
                    "merged": len(pairs),
                    "remaining": len(kept),
                    "pairs": pairs,
                    "details": details,
                }
                if dry_run:
                    self.conn.rollback()
                else:
                    self.conn.commit()
                return result
            except Exception:
                self.conn.rollback()
                raise

    def cleanup_duplicates(self, dry_run: bool = True) -> dict[str, Any]:
        """Compatibility name for the duplicate maintenance pass."""
        return self.deduplicate(dry_run=dry_run)

    def all(
        self,
        kinds: Iterable[str] | None = None,
        include_archived: bool = False,
        limit: int | None = None,
    ) -> list[Memory]:
        with self._lock:
            sql = "SELECT * FROM memories WHERE user_id = ?"
            params: list[Any] = [self.user_id]
            if not include_archived:
                sql += " AND archived = 0"
            kind_list = list(kinds) if kinds else []
            if kind_list:
                sql += f" AND kind IN ({','.join('?' * len(kind_list))})"
                params.extend(kind_list)
            sql += " ORDER BY created_at DESC"
            if limit is not None:
                sql += " LIMIT ?"
                params.append(int(limit))
            return [Memory.from_row(r) for r in self.conn.execute(sql, params)]

    def recall(
        self,
        query: str,
        limit: int = 8,
        kinds: Iterable[str] | None = None,
        reinforce: bool = True,
    ) -> list[Memory]:
        """Hybrid search: relevance, recency, importance and usage."""
        with self._lock:
            kind_list = list(kinds) if kinds else []
            match = build_match_query(query)
            hits: list[tuple[int, float]] = []

            if match:
                try:
                    rows = self.conn.execute(
                        """SELECT memories_fts.rowid AS rid,
                                  bm25(memories_fts, 1.0, 0.5) AS rank_score
                           FROM memories_fts
                           JOIN memories ON memories.id = memories_fts.rowid
                           WHERE memories_fts MATCH ? AND memories.user_id = ?
                           ORDER BY rank_score LIMIT ?""",
                        (match, self.user_id, max(limit * 8, 40)),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
                hits = [(int(r["rid"]), float(r["rank_score"])) for r in rows]

            if not hits:
                hits = [(rid, -1.0) for rid in self._like_scan(query, kind_list, limit)]

            if not hits:
                return []

            # bm25() is negative, more negative meaning better; normalise against
            # the best hit so relevance lands in (0, 1].
            best = min(raw for _, raw in hits)
            now = time.time()
            scored: list[Memory] = []

            for rid, raw in hits:
                # Archived rows must never resurface, otherwise forget() is a lie.
                sql = "SELECT * FROM memories WHERE user_id = ? AND id = ? AND archived = 0"
                params: list[Any] = [self.user_id, rid]
                if kind_list:
                    sql += f" AND kind IN ({','.join('?' * len(kind_list))})"
                    params.extend(kind_list)
                row = self.conn.execute(sql, params).fetchone()
                if row is None:
                    continue

                relevance = (raw / best) if best < 0 else 0.0
                relevance = max(0.0, min(1.0, relevance))
                age = max(0.0, now - float(row["created_at"]))
                recency = math.exp(-math.log(2) * age / HALF_LIFE_SECONDS)
                importance = max(0.0, min(1.0, float(row["importance"])))
                usage = 1.0 - math.exp(-int(row["use_count"]) / 5.0)

                score = (
                    W_RELEVANCE * relevance
                    + W_RECENCY * recency
                    + W_IMPORTANCE * importance
                    + W_USAGE * usage
                )
                scored.append(Memory.from_row(row, score=score))

            scored.sort(key=lambda m: m.score, reverse=True)
            results = scored[:limit]

            if reinforce and results:
                now = time.time()
                self.conn.executemany(
                    """UPDATE memories SET use_count = use_count + 1, last_used_at = ?
                       WHERE user_id = ? AND id = ?""",
                    [(now, self.user_id, m.id) for m in results],
                )
                self.conn.commit()
                for m in results:
                    m.use_count += 1
                    m.last_used_at = now

            # L5 (SEC Stage D): recalled memories re-enter context as
            # untrusted text; each is scanned on the way in.
            from dream.security.injection import guard_untrusted

            for memory in results:
                memory.content = guard_untrusted(memory.content, source="memory")

            return results

    def _like_scan(self, query: str, kind_list: list[str], limit: int) -> list[int]:
        """Substring fallback for when FTS finds nothing."""
        with self._lock:
            tokens = _tokenize(query)
            if not tokens:
                return []
            clauses = []
            params: list[Any] = []
            for token in tokens:
                stem = _stem_fa(token)
                clauses.append("(norm LIKE ? OR tags LIKE ?)")
                params.extend([f"%{stem}%", f"%{stem}%"])
            sql = (
                "SELECT id FROM memories WHERE user_id = ? AND archived = 0 AND "
                f"({' OR '.join(clauses)})"
            )
            params.insert(0, self.user_id)
            if kind_list:
                sql += f" AND kind IN ({','.join('?' * len(kind_list))})"
                params.extend(kind_list)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(max(limit * 8, 40))
            return [int(r["id"]) for r in self.conn.execute(sql, params)]

    # -- journal -----------------------------------------------------------

    def log(self, role: str, content: str, session_id: str = "") -> int:
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO journal (user_id, ts, role, content, session_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (self.user_id, time.time(), role, content, session_id),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def recent_journal(
        self, limit: int = 20, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        with self._lock:
            sql = "SELECT * FROM journal WHERE user_id = ?"
            params: list[Any] = [self.user_id]
            if session_id is not None:
                sql += " AND session_id = ?"
                params.append(session_id)
            sql += " ORDER BY id DESC LIMIT ?"
            params.append(int(limit))
            rows = self.conn.execute(sql, params).fetchall()
            return [dict(r) for r in reversed(rows)]

    # -- reminders ---------------------------------------------------------

    def add_reminder(
        self,
        text: str,
        due_at: float,
        repeat_days: int | None = None,
        repeat_months: int | None = None,
    ):
        """Add a reminder for the owning user.

        Delegates to :mod:`dream.reminders` so the schema logic stays in one
        place. Mirrors the store's lock and user filtering conventions.
        """
        from dream.reminders import add_reminder as _add

        return _add(self, text, due_at, repeat_days, repeat_months)

    def list_reminders(self, include_inactive: bool = False):
        """List reminders for the owning user, active by default."""
        from dream.reminders import list_reminders as _list

        return _list(self, include_inactive)

    def get_reminder(self, reminder_id: int):
        """Fetch one reminder by id, filtered by user."""
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM reminders WHERE user_id = ? AND id = ?",
                (self.user_id, reminder_id),
            ).fetchone()
            if row is None:
                return None
            from dream.reminders import _row_to_reminder

            return _row_to_reminder(row)

    def delete_reminder(self, reminder_id: int) -> bool:
        """Delete a reminder by id. Returns True if deleted."""
        from dream.reminders import delete_reminder as _delete

        return _delete(self, reminder_id)

    def update_reminder(
        self,
        reminder_id: int,
        *,
        text: str | None = _MISSING,  # type: ignore[assignment]
        due_at: float | None = _MISSING,  # type: ignore[assignment]
        repeat_days: int | None = _MISSING,  # type: ignore[assignment]
        repeat_months: int | None = _MISSING,  # type: ignore[assignment]
    ):
        """Update a reminder in place, keeping its identifier.

        An edit must keep the same row so delivery history is not lost.
        Deleting and re-creating would change the identifier and drop
        ``reminder_deliveries`` rows. This method updates the existing row
        and preserves every delivery row.

        Only supplied fields are changed; others keep their stored value.
        Validates the same constraints as :func:`dream.reminders.add_reminder`.

        Returns the updated :class:`dream.reminders.Reminder` or ``None`` when
        no row with that id exists for this user.
        """
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM reminders WHERE user_id = ? AND id = ?",
                (self.user_id, reminder_id),
            ).fetchone()
            if row is None:
                return None
            # Determine new values
            new_text: str
            if text is _MISSING:
                new_text = str(row["text"])
            else:
                if not isinstance(text, str):
                    raise ValueError("text must be a string")
                new_text = text.strip()
                if not new_text:
                    raise ValueError("text must not be empty")
            new_due = float(due_at) if due_at is not _MISSING else float(row["due_at"])
            new_repeat_days = repeat_days if repeat_days is not _MISSING else row["repeat_days"]
            if new_repeat_days is not None:
                new_repeat_days = int(new_repeat_days)  # type: ignore[arg-type]
            new_repeat_months = (
                repeat_months if repeat_months is not _MISSING else row["repeat_months"]
            )
            if new_repeat_months is not None:
                new_repeat_months = int(new_repeat_months)  # type: ignore[arg-type]
            if new_repeat_days == 0 or new_repeat_months == 0:
                raise ValueError("repeat must be non-zero")
            if new_repeat_days is not None and new_repeat_months is not None:
                raise ValueError("repeat must be either days or months, not both")
            # Anchor recomputation: when due_at changes or monthly repeat changes,
            # recompute the Jalali anchor day from the new due timestamp.
            anchor = row["anchor_day"]
            need_anchor = (
                due_at is not _MISSING
                or (repeat_months is not _MISSING and repeat_months != row["repeat_months"])
            )
            if need_anchor and new_repeat_months is not None:
                try:
                    import datetime

                    from dream.jalali import gregorian_to_jalali

                    dt = datetime.datetime.fromtimestamp(new_due, tz=datetime.timezone.utc)
                    _, _, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
                    anchor = jd
                except Exception:
                    pass
            self.conn.execute(
                "UPDATE reminders SET text = ?, due_at = ?, next_due = ?, "
                "repeat_days = ?, repeat_months = ?, anchor_day = ? "
                "WHERE user_id = ? AND id = ?",
                (
                    new_text,
                    float(new_due),
                    float(new_due),
                    new_repeat_days,
                    new_repeat_months,
                    anchor,
                    self.user_id,
                    reminder_id,
                ),
            )
            self.conn.commit()
            return self.get_reminder(reminder_id)

    def update_memory(
        self,
        memory_id: int,
        *,
        content: str | None = _MISSING,  # type: ignore[assignment]
        kind: str | None = _MISSING,  # type: ignore[assignment]
        tags: Sequence[str] | None = _MISSING,  # type: ignore[assignment]
        importance: float | None = _MISSING,  # type: ignore[assignment]
    ):
        """Update a memory in place, keeping its identifier.

        Deleting and re-creating would change the identifier and lose the
        ``created_at`` lineage. This method updates the existing row, keeps
        its ``id`` and ``created_at``, refreshes ``norm`` and the FTS index
        via the ``UPDATE`` trigger, and bumps ``last_used_at``.
        """
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM memories WHERE user_id = ? AND id = ?",
                (self.user_id, memory_id),
            ).fetchone()
            if row is None:
                return None
            new_content = content if content is not _MISSING else str(row["content"])  # type: ignore[assignment]
            if not isinstance(new_content, str):
                raise ValueError("content must be a string")
            new_content = new_content.strip()
            if not new_content:
                raise ValueError("content must not be empty")
            new_kind = kind if kind is not _MISSING else str(row["kind"])  # type: ignore[assignment]
            if new_kind not in KINDS:
                raise ValueError(f"kind must be one of {KINDS}, got {new_kind!r}")
            if tags is _MISSING:
                # keep existing tags as stored list
                try:
                    new_tags = json.loads(row["tags"] or "[]")
                except (TypeError, ValueError):
                    new_tags = []
            else:
                if tags is None:
                    new_tags = []
                else:
                    new_tags = [normalize_fa(t) for t in tags if isinstance(t, str) and t.strip()]
            if importance is _MISSING:
                new_importance = float(row["importance"])
            else:
                new_importance = float(importance)  # type: ignore[arg-type]
                if not 0.0 <= new_importance <= 1.0:
                    # keep as float but allow any [0,1]; storage already does
                    pass
            new_norm = normalize_fa(new_content)
            now = time.time()
            self.conn.execute(
                "UPDATE memories SET kind = ?, content = ?, norm = ?, tags = ?, "
                "importance = ?, last_used_at = ? WHERE user_id = ? AND id = ?",
                (
                    new_kind,
                    new_content,
                    new_norm,
                    json.dumps(new_tags, ensure_ascii=False),
                    float(new_importance),
                    now,
                    self.user_id,
                    memory_id,
                ),
            )
            self.conn.commit()
            return self.get(memory_id)

    def check_due_reminders(self, now: float | None = None, destination: str = "terminal"):
        """Run the due check for one notification destination."""
        from dream.reminders import check_due_reminders as _check

        return _check(self, now, destination=destination)

    # -- introspection -----------------------------------------------------

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self.conn.execute(
                "SELECT COUNT(*) FROM memories WHERE user_id = ? AND archived = 0",
                (self.user_id,),
            ).fetchone()[0]
            archived = self.conn.execute(
                "SELECT COUNT(*) FROM memories WHERE user_id = ? AND archived = 1",
                (self.user_id,),
            ).fetchone()[0]
            by_kind = {
                row["kind"]: row["n"]
                for row in self.conn.execute(
                    """SELECT kind, COUNT(*) AS n FROM memories
                       WHERE user_id = ? AND archived = 0 GROUP BY kind""",
                    (self.user_id,),
                )
            }
            journal = self.conn.execute(
                "SELECT COUNT(*) FROM journal WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()[0]
        return {
            "total": int(total),
            "archived": int(archived),
            "by_kind": {k: int(by_kind.get(k, 0)) for k in KINDS},
            "journal": int(journal),
            "path": self.path,
        }
