"""Persian-aware memory storage for Dream.

Everything here is standard library only: text normalisation, a light Persian
stemmer, and a SQLite-backed store with an FTS5 index.

Persian text arrives from keyboards, phones, web pages and OCR in a dozen
byte-level spellings of the same word.  ``مي‌خواهم`` (Arabic yeh) and
``می‌خواهم`` (Farsi yeh) look identical on screen and never match each other in
a database.  Normalising on write *and* on read is what makes retrieval work at
all, so it happens in one place: :func:`normalize_fa`.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Memory",
    "MemoryStore",
    "KINDS",
    "normalize_fa",
]

KINDS: tuple[str, ...] = ("semantic", "episodic", "procedural")

# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

# Persian (U+06F0-U+06F9) and Arabic-Indic (U+0660-U+0669) digits to ASCII.
_DIGIT_MAP = {
    **{0x06F0 + i: ord("0") + i for i in range(10)},
    **{0x0660 + i: ord("0") + i for i in range(10)},
}

# Arabic letter forms unified onto their Persian counterparts.
_CHAR_MAP = {
    0x064A: 0x06CC,  # ARABIC YEH        -> FARSI YEH
    0x0649: 0x06CC,  # ALEF MAKSURA      -> FARSI YEH
    0x0643: 0x06A9,  # ARABIC KAF        -> KEHEH
    0x0629: 0x0647,  # TEH MARBUTA       -> HEH
    0x0623: 0x0627,  # ALEF WITH HAMZA ABOVE -> ALEF
    0x0625: 0x0627,  # ALEF WITH HAMZA BELOW -> ALEF
    0x0622: 0x0627,  # ALEF WITH MADDA ABOVE -> ALEF
    0x0624: 0x0648,  # WAW WITH HAMZA    -> WAW
    0x0626: 0x06CC,  # YEH WITH HAMZA    -> FARSI YEH
}

# Harakat, superscript alef and tatweel carry no lexical weight here.
_DIACRITICS = {cp: None for cp in range(0x064B, 0x0653)}
_DIACRITICS[0x0670] = None  # SUPERSCRIPT ALEF
_DIACRITICS[0x0640] = None  # TATWEEL

_ZWNJ = "\u200c"
_WS_RE = re.compile(r"\s+")


def normalize_fa(text: str) -> str:
    """Normalise Persian/Arabic text to one canonical spelling.

    Steps run in a fixed order: NFKC, digit folding, character unification,
    diacritic stripping, ZWNJ to space, whitespace collapsing.
    """
    if not text:
        return ""
    out = unicodedata.normalize("NFKC", text)
    out = out.translate(_DIGIT_MAP)
    out = out.translate(_CHAR_MAP)
    out = out.translate(_DIACRITICS)
    out = out.replace(_ZWNJ, " ")
    return _WS_RE.sub(" ", out).strip()


# Longest suffixes first so ``هایمان`` is not shortened to ``ها`` + junk.
_SUFFIXES: tuple[str, ...] = (
    "هایمان",
    "هایتان",
    "هایشان",
    "هایی",
    "هایم",
    "هایت",
    "هایش",
    "مان",
    "تان",
    "شان",
    "های",
    "ها",
    "ترین",
    "تر",
    "ام",
    "ات",
    "اش",
    "ی",
    "م",
    "ت",
    "ش",
)


def _stem_fa(token: str) -> str:
    """Strip one Persian suffix when a meaningful stem remains.

    Retrieval, not linguistics: ``استارتاپم`` must reach a stored
    ``استارتاپ``.
    """
    for suffix in _SUFFIXES:
        if token.endswith(suffix):
            stem = token[: -len(suffix)]
            if len(stem) > 2:
                return stem
    return token


_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(normalize_fa(text))


def _fts_escape(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def build_match_query(query: str) -> str:
    """Build an FTS5 MATCH expression: every token as an exact term OR a
    prefix search on its stem."""
    clauses: list[str] = []
    seen: set[str] = set()
    for token in _tokenize(query):
        stem = _stem_fa(token)
        for clause in (_fts_escape(token), _fts_escape(stem) + "*"):
            if clause not in seen:
                seen.add(clause)
                clauses.append(clause)
    return " OR ".join(clauses)


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------


@dataclass(slots=True)
class Memory:
    """A single distilled memory."""

    id: int
    kind: str
    content: str
    norm: str
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5
    created_at: float = 0.0
    last_used_at: float = 0.0
    use_count: int = 0
    source: str = ""
    archived: bool = False
    score: float = 0.0

    @classmethod
    def from_row(cls, row: sqlite3.Row, score: float = 0.0) -> Memory:
        try:
            tags = json.loads(row["tags"] or "[]")
        except (TypeError, ValueError):
            tags = []
        return cls(
            id=row["id"],
            kind=row["kind"],
            content=row["content"],
            norm=row["norm"],
            tags=list(tags),
            importance=float(row["importance"]),
            created_at=float(row["created_at"]),
            last_used_at=float(row["last_used_at"]),
            use_count=int(row["use_count"]),
            source=row["source"] or "",
            archived=bool(row["archived"]),
            score=score,
        )


_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    norm         TEXT    NOT NULL,
    tags         TEXT    NOT NULL DEFAULT '[]',
    importance   REAL    NOT NULL DEFAULT 0.5,
    created_at   REAL    NOT NULL,
    last_used_at REAL    NOT NULL,
    use_count    INTEGER NOT NULL DEFAULT 0,
    user_id      TEXT    NOT NULL DEFAULT 'local',
    source       TEXT    NOT NULL DEFAULT '',
    archived     INTEGER NOT NULL DEFAULT 0,
    superseded_by INTEGER
);

CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);
CREATE INDEX IF NOT EXISTS idx_memories_archived ON memories(archived);
CREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories(user_id);

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
    ts         REAL NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    user_id     TEXT    NOT NULL DEFAULT 'local'
);

CREATE INDEX IF NOT EXISTS idx_journal_session ON journal(session_id);
"""

# Hybrid scoring weights.
W_RELEVANCE = 0.55
W_RECENCY = 0.20
W_IMPORTANCE = 0.15
W_USAGE = 0.10

HALF_LIFE_SECONDS = 30 * 24 * 3600.0


class MemoryStore:
    """SQLite-backed memory: one file, no external service."""

    def __init__(self, path: str = "data/dream.db") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            import os

            parent = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = threading.RLock()
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
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
    ) -> Memory:
        """Store a memory, or boost the existing one if it is a duplicate."""
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
        content = content.strip()
        if not content:
            raise ValueError("content must not be empty")
        norm = normalize_fa(content)
        tag_list = [normalize_fa(t) for t in (tags or []) if t.strip()]
        now = time.time()

        existing = self.conn.execute(
            "SELECT * FROM memories WHERE norm = ? AND kind = ? AND archived = 0",
            (norm, kind),
        ).fetchone()
        if existing is not None:
            boosted = min(1.0, float(existing["importance"]) + 0.1)
            merged = sorted(set(json.loads(existing["tags"] or "[]")) | set(tag_list))
            self.conn.execute(
                "UPDATE memories SET importance = ?, tags = ?, last_used_at = ? WHERE id = ?",
                (boosted, json.dumps(merged, ensure_ascii=False), now, existing["id"]),
            )
            self.conn.commit()
            return self.get(existing["id"])  # type: ignore[return-value]

        cur = self.conn.execute(
            """INSERT INTO memories
               (kind, content, norm, tags, importance, created_at, last_used_at,
                use_count, source, archived)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, 0)""",
            (
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
        self.conn.commit()
        return self.get(int(cur.lastrowid))  # type: ignore[return-value]

    def forget(self, memory_id: int, hard: bool = False) -> bool:
        """Archive a memory (default) or delete it outright."""
        if hard:
            cur = self.conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        else:
            cur = self.conn.execute(
                "UPDATE memories SET archived = 1 WHERE id = ? AND archived = 0",
                (memory_id,),
            )
        self.conn.commit()
        return cur.rowcount > 0

    # -- reading -----------------------------------------------------------

    def get(self, memory_id: int, include_archived: bool = True) -> Memory | None:
        sql = "SELECT * FROM memories WHERE id = ?"
        if not include_archived:
            sql += " AND archived = 0"
        row = self.conn.execute(sql, (memory_id,)).fetchone()
        return Memory.from_row(row) if row is not None else None

    def all(
        self,
        kinds: Iterable[str] | None = None,
        include_archived: bool = False,
        limit: int | None = None,
    ) -> list[Memory]:
        sql = "SELECT * FROM memories WHERE 1=1"
        params: list[Any] = []
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
        kind_list = list(kinds) if kinds else []
        match = build_match_query(query)
        hits: list[tuple[int, float]] = []

        if match:
            try:
                rows = self.conn.execute(
                    """SELECT rowid AS rid, bm25(memories_fts, 1.0, 0.5) AS rank_score
                       FROM memories_fts WHERE memories_fts MATCH ?
                       ORDER BY rank_score LIMIT ?""",
                    (match, max(limit * 8, 40)),
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
            sql = "SELECT * FROM memories WHERE id = ? AND archived = 0"
            params: list[Any] = [rid]
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
                "UPDATE memories SET use_count = use_count + 1, last_used_at = ? WHERE id = ?",
                [(now, m.id) for m in results],
            )
            self.conn.commit()
            for m in results:
                m.use_count += 1
                m.last_used_at = now

        return results

    def _like_scan(self, query: str, kind_list: list[str], limit: int) -> list[int]:
        """Substring fallback for when FTS finds nothing."""
        tokens = _tokenize(query)
        if not tokens:
            return []
        clauses = []
        params: list[Any] = []
        for token in tokens:
            stem = _stem_fa(token)
            clauses.append("(norm LIKE ? OR tags LIKE ?)")
            params.extend([f"%{stem}%", f"%{stem}%"])
        sql = f"SELECT id FROM memories WHERE archived = 0 AND ({' OR '.join(clauses)})"
        if kind_list:
            sql += f" AND kind IN ({','.join('?' * len(kind_list))})"
            params.extend(kind_list)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(limit * 8, 40))
        return [int(r["id"]) for r in self.conn.execute(sql, params)]

    # -- journal -----------------------------------------------------------

    def log(self, role: str, content: str, session_id: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO journal (ts, role, content, session_id) VALUES (?, ?, ?, ?)",
            (time.time(), role, content, session_id),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def recent_journal(
        self, limit: int = 20, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM journal"
        params: list[Any] = []
        if session_id is not None:
            sql += " WHERE session_id = ?"
            params.append(session_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in reversed(rows)]

    # -- introspection -----------------------------------------------------

    def stats(self) -> dict[str, Any]:
        total = self.conn.execute("SELECT COUNT(*) FROM memories WHERE archived = 0").fetchone()[0]
        archived = self.conn.execute("SELECT COUNT(*) FROM memories WHERE archived = 1").fetchone()[
            0
        ]
        by_kind = {
            row["kind"]: row["n"]
            for row in self.conn.execute(
                "SELECT kind, COUNT(*) AS n FROM memories WHERE archived = 0 GROUP BY kind"
            )
        }
        journal = self.conn.execute("SELECT COUNT(*) FROM journal").fetchone()[0]
        return {
            "total": int(total),
            "archived": int(archived),
            "by_kind": {k: int(by_kind.get(k, 0)) for k in KINDS},
            "journal": int(journal),
            "path": self.path,
        }
