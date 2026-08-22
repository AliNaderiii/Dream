"""FTS5 session search with Persian normalization (MEM Stage B).

Dream's marquee retrieval property — typing one spelling variant of a Persian
word finds the other — already holds for durable memory because
:mod:`dream.memory` normalises on write and read.  Conversations deserve the
same guarantee: a session transcribed with Arabic code points
(``\\u0643\\u062a\\u0627\\u0628``: Arabic kaf + yeh) must surface when the user
types the Farsi spelling (``\\u06a9\\u062a\\u0627\\u0628``: keheh + Farsi yeh)
and vice versa, offline, in milliseconds.

**Why pre-normalised content.**  SQLite's ``unicode61`` tokenizer folds case
and (optionally) diacritics, but it does **not** fold Arabic yeh/kaf onto
their Farsi counterparts nor Persian/Arabic-Indic digits onto ASCII.  No
tokenizer option can, because they are plain different code points.  The only
place all of Dream's folding rules already live is the single shared
normalizer :func:`dream.memory.normalize_fa`, so the index normalises session
text *before* it reaches FTS5 and normalises every query the same way.  The
cost is storage: the content table keeps both the original text (for display
and snippets) and its normalised shadow (indexed by FTS5), so text is stored
roughly twice.  For a personal session corpus (10⁴ sessions, a few hundred
characters each) that is a few MB — a price worth paying for spelling-variant
retrieval, and it is why ``prefix=`` indexing was measured and then not used
(see MEM-B.md: warm p95 is ~200× under budget without it).

**Schema: external content.**  ``session_docs`` is the single source of truth
(title/body, original + normalised, updated_at); ``session_fts`` is an
external-content FTS5 table over it holding only the inverted index.
A contentless table was rejected: it cannot serve content-derived results and
cannot run the ``'rebuild'`` command; a self-contained FTS table was
rejected: it would duplicate the full text a second time inside the index
structure.  External content keeps one copy of the text, supports
``'rebuild'``, and lets searches join back to the originals for snippets.

**Snippets come from the original text, in Python.**  FTS5's ``snippet()``
highlights where the *indexed* (normalised) tokens matched — in the
normalised column.  Highlighting the user's original spelling requires
mapping matches back onto un-normalised text, which SQL cannot do; the
snippet helper below walks original words, normalises each word through the
same shared normalizer, marks the words that carry a query token, and cuts a
word-aligned window.  It never reorders anything, so RTL/bidirectional text
is sliced, not mangled.

**Lifecycle and failure discipline.**  ``index_session`` / ``append_message``
/ ``remove_session`` upsert whole documents inside one ``BEGIN IMMEDIATE``
transaction (the CLI, the scheduler daemon and the gateway can all write;
the process lock plus SQLite's write lock serialise them exactly like the
Stage A bounded stores).  ``rebuild()`` re-derives the FTS index from the
content table.  Opening validates ``PRAGMA user_version`` and the two-table
structure: a *missing* file is a fresh index, but an **unreadable, corrupt,
or schema-mismatched file fails closed** with a bilingual error — the
ledger's missing-vs-corrupt discipline — because silently wiping and
reindexing could hide the loss of the only copy of the corpus.

Standard library only: ``sqlite3``, ``re``, ``threading``.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from dream.memory import _tokenize, normalize_fa

__all__ = [
    "DEFAULT_SESSION_INDEX_PATH",
    "SCHEMA_VERSION",
    "SessionHit",
    "SessionIndexError",
    "SessionSearchIndex",
    "extract_snippet",
    "query_tokens",
]

#: Schema version stamped into ``PRAGMA user_version``.  Bump when the table
#: shapes change; a file stamped with a different value refuses to open.
SCHEMA_VERSION = 1

DEFAULT_SESSION_INDEX_PATH = "data/dream-session-index.db"

# Cross-process writers wait for the SQLite write lock instead of failing.
_BUSY_TIMEOUT_MS = 5_000

# Shapes observed when another process is mid-initialisation of a fresh
# file (its session_docs/session_fts exist before the version stamp does).
# These are waited out briefly; any other unstamped shape fails closed.
_INIT_IN_PROGRESS_TABLES = frozenset(
    {"session_docs", "session_fts", "sqlite_sequence"}
)
_INIT_WAIT_SECONDS = 5.0

# bm25 column weights: a title hit is worth three body hits. Column order in
# the weight list matches the FTS declaration (title_norm, body_norm).
TITLE_WEIGHT = 3.0
BODY_WEIGHT = 1.0

# A query longer than this is capped (first tokens win) so a pasted paragraph
# cannot turn into an unbounded MATCH expression.
MAX_QUERY_TOKENS = 12

# Default snippet window, in characters of original text, cut at word edges.
SNIPPET_WIDTH_CHARS = 110

_WORD_RE = re.compile(r"\S+")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_docs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT    NOT NULL UNIQUE,
    title_orig TEXT    NOT NULL DEFAULT '',
    body_orig  TEXT    NOT NULL DEFAULT '',
    title_norm TEXT    NOT NULL DEFAULT '',
    body_norm  TEXT    NOT NULL DEFAULT '',
    updated_at REAL    NOT NULL,
    source     TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_session_docs_updated ON session_docs(updated_at);
CREATE VIRTUAL TABLE IF NOT EXISTS session_fts USING fts5(
    title_norm,
    body_norm,
    content='session_docs',
    content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);
"""


class SessionIndexError(Exception):
    """Fail-closed index failure. Bilingual message; nothing was wiped."""

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.details: dict[str, Any] = dict(details)


# Gloss: «ایندکس جست‌وجوی نشست‌ها خوانا نیست یا ساختارش خراب است و تا بازسازی
# نشود جست‌وجو انجام نمی‌شود؛ هیچ داده‌ای بی‌صدا پاک یا بازنویسی نشد. با تابع
# بازسازی (rebuild) ایندکس را از جدول محتوا دوباره بساز.»
_ERR_CORRUPT_FA = (
    "\u0627\u06cc\u0646\u062f\u06a9\u0633 \u062c\u0633\u062a\u200c\u0648\u062c\u0648"
    "\u06cc \u0646\u0634\u0633\u062a\u200c\u0647\u0627 \u062e\u0648\u0627\u0646\u0627 "
    "\u0646\u06cc\u0633\u062a \u06cc\u0627 \u0633\u0627\u062e\u062a\u0627\u0631\u0634 "
    "\u062e\u0631\u0627\u0628 \u0627\u0633\u062a \u0648 \u062a\u0627 \u0628\u0627"
    "\u0632\u0633\u0627\u0632\u06cc \u0646\u0634\u0648\u062f \u062c\u0633\u062a"
    "\u200c\u0648\u062c\u0648 \u0627\u0646\u062c\u0627\u0645 \u0646\u0645\u06cc"
    "\u200c\u0634\u0648\u062f\u061b \u0647\u06cc\u0686 \u062f\u0627\u062f\u0647"
    "\u200c\u0627\u06cc \u0628\u06cc\u200c\u0635\u062f\u0627 \u067e\u0627\u06a9 "
    "\u06cc\u0627 \u0628\u0627\u0632\u0646\u0648\u06cc\u0633\u06cc \u0646\u0634\u062f. "
    "\u0628\u0627 \u062a\u0627\u0628\u0639 \u0628\u0627\u0632\u0633\u0627\u0632\u06cc "
    "(rebuild) \u0627\u06cc\u0646\u062f\u06a9\u0633 \u0631\u0627 \u0627\u0632 "
    "\u062c\u062f\u0648\u0644 \u0645\u062d\u062a\u0648\u0627 \u062f\u0648\u0628\u0627"
    "\u0631\u0647 \u0628\u0633\u0627\u0632."
)
_ERR_CORRUPT_EN = (
    " The session search index is unreadable, corrupt, or structurally"
    " incomplete; search stays disabled until it is rebuilt. Nothing was"
    " silently deleted or overwritten. Rebuild it from the content table with"
    " SessionSearchIndex.rebuild()."
)

# Gloss: «نسخهٔ ساختار ایندکس جست‌وجوی نشست‌ها با این نسخهٔ دریم سازگار نیست
# ({found} در برابر {expected})؛ برای جلوگیری از از دست رفتن داده، جست‌وجو
# متوقف شد. ایندکس را با نسخهٔ سازگار باز کنید یا بازسازی کنید.»
_ERR_VERSION_FA = (
    "\u0646\u0633\u062e\u0647\u0654 \u0633\u0627\u062e\u062a\u0627\u0631 "
    "\u0627\u06cc\u0646\u062f\u06a9\u0633 \u062c\u0633\u062a\u200c\u0648\u062c"
    "\u0648\u06cc \u0646\u0634\u0633\u062a\u200c\u0647\u0627 \u0628\u0627 "
    "\u0627\u06cc\u0646 \u0646\u0633\u062e\u0647\u0654 \u062f\u0631\u06cc\u0645 "
    "\u0633\u0627\u0632\u06af\u0627\u0631 \u0646\u06cc\u0633\u062a ({found} "
    "\u062f\u0631 \u0628\u0631\u0627\u0628\u0631 {expected})\u061b \u0628\u0631"
    "\u0627\u06cc \u062c\u0644\u0648\u06af\u06cc\u0631\u06cc \u0627\u0632 \u0627"
    "\u0632 \u062f\u0633\u062a \u0631\u0641\u062a\u0646 \u062f\u0627\u062f\u0647"
    "\u060c \u062c\u0633\u062a\u200c\u0648\u062c\u0648 \u0645\u062a\u0648\u0642"
    "\u0641 \u0634\u062f. \u0627\u06cc\u0646\u062f\u06a9\u0633 \u0631\u0627 "
    "\u0628\u0627 \u0646\u0633\u062e\u0647\u0654 \u0633\u0627\u0632\u06af\u0627"
    "\u0631 \u0628\u0627\u0632 \u06a9\u0646\u06cc\u062f \u06cc\u0627 \u0628\u0627"
    "\u0632\u0633\u0627\u0632\u06cc \u06a9\u0646\u06cc\u062f."
)
_ERR_VERSION_EN = (
    " Session-index schema version {found} is incompatible with this Dream"
    " (expects {expected}); search is stopped to avoid data loss. Open the"
    " index with a compatible Dream version or rebuild it."
)

# Gloss: «عبارت جست‌وجو بعد از نرمال‌سازی خالی است؛ عبارتی معتبر بفرست.»
_ERR_QUERY_FA = (
    "\u0639\u0628\u0627\u0631\u062a \u062c\u0633\u062a\u200c\u0648\u062c\u0648 "
    "\u0628\u0639\u062f \u0627\u0632 \u0646\u0631\u0645\u0627\u0644"
    "\u200c\u0633\u0627\u0632\u06cc \u062e\u0627\u0644\u06cc \u0627\u0633\u062a"
    "\u061b \u0639\u0628\u0627\u0631\u062a\u06cc \u0645\u0639\u062a\u0628\u0631 "
    "\u0628\u0641\u0631\u0633\u062a."
)


def query_tokens(query: str, limit: int = MAX_QUERY_TOKENS) -> list[str]:
    """Normalised, de-duplicated query tokens through the shared normalizer."""
    seen: set[str] = set()
    tokens: list[str] = []
    for token in _tokenize(query):
        if token not in seen:
            seen.add(token)
            tokens.append(token)
            if len(tokens) >= limit:
                break
    return tokens


def _fts_escape(token: str) -> str:
    return '"' + token.replace('"', '""') + '"'


def _clip(original: str, width: int) -> str:
    """Plain head-of-text window at a word edge, no highlight markers."""
    if len(original) <= width:
        return original
    head = original[:width]
    cut = head.rfind(" ")
    if cut > 0:
        head = head[:cut]
    return head + "…"


def extract_snippet(
    original: str, query: str, *, width: int = SNIPPET_WIDTH_CHARS
) -> str:
    """Word-aligned snippet of *original* with ``[...]`` around matched words.

    Matching runs per original word: each whitespace-delimited word is
    normalised through the shared normalizer and marked when it contains one
    of the query's normalised tokens.  The window grows around the first
    match to roughly *width* characters, always cut at word boundaries, so
    the result — markers and ellipses aside — is a verbatim contiguous slice
    of the original text, never a reordering.  ASCII brackets and ``…`` are
    directionally neutral in practice and bidi text is sliced, not reshaped.
    """
    tokens = query_tokens(query)
    if not original.strip() or not tokens:
        return _clip(original, width)
    words = list(_WORD_RE.finditer(original))
    if not words:
        return _clip(original, width)
    flags = [
        any(token in normalize_fa(word.group(0)) for token in tokens)
        for word in words
    ]
    if not any(flags):
        return _clip(original, width)
    first = flags.index(True)
    start = end = first
    # Grow the window to ~width chars, preferring context after the match,
    # then before it; boundaries always land on word edges.
    while True:
        span = words[end].end() - words[start].start()
        if span >= width:
            break
        grew = False
        if end < len(words) - 1:
            end += 1
            grew = True
        if start > 0 and words[end].end() - words[start].start() < width:
            start -= 1
            grew = True
        if not grew:
            break
    segment_start = words[start].start()
    segment = original[segment_start : words[end].end()]
    pieces: list[str] = []
    prev = 0
    for word, flag in zip(
        words[start : end + 1], flags[start : end + 1], strict=True
    ):
        s = word.start() - segment_start
        e = word.end() - segment_start
        pieces.append(segment[prev:s])
        pieces.append(f"[{segment[s:e]}]" if flag else segment[s:e])
        prev = e
    pieces.append(segment[prev:])
    snippet = "".join(pieces)
    if start > 0:
        snippet = "…" + snippet
    if end < len(words) - 1:
        snippet += "…"
    return snippet


@dataclass(frozen=True, slots=True)
class SessionHit:
    """One ranked search result over the session corpus."""

    session_id: str
    title: str
    snippet: str
    score: float
    matched_in_title: bool
    updated_at: float
    source: str


class SessionSearchIndex:
    """SQLite FTS5 index over session conversations (external content).

    Writers serialize exactly like the Stage A bounded stores: one re-entrant
    process lock plus ``BEGIN IMMEDIATE`` per upsert, ``busy_timeout`` for
    other processes.  Searches are read-only and never take the write lock.
    """

    def __init__(self, path: str = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            parent = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(parent, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(
            self.path, check_same_thread=False, isolation_level=None
        )
        self.conn.row_factory = sqlite3.Row
        self._validate_or_init()

    # -- open/close --------------------------------------------------------

    def _fail_closed(self, reason: str, **details: Any) -> SessionIndexError:
        message = _ERR_CORRUPT_FA + _ERR_CORRUPT_EN
        if "found" in details:
            message = (
                _ERR_VERSION_FA.format(
                    found=details["found"], expected=details["expected"]
                )
                + _ERR_VERSION_EN.format(
                    found=details["found"], expected=details["expected"]
                )
            )
        return SessionIndexError(message, path=self.path, reason=reason, **details)

    def _validate_or_init(self) -> None:
        """Ledger-style open check: missing file is fresh; anything unreadable,
        structurally incomplete, or version-mismatched fails closed.

        Two processes can open the same *fresh* file at the same instant (the
        CLI and the scheduler daemon both may).  The loser of that race sees
        the winner's tables before the winner stamps ``user_version``; that
        specific shape — exactly our tables, stamp still zero — is waited out
        briefly rather than refused, because it is initialisation in flight,
        not corruption.  Anything else with tables and no stamp fails closed.
        """
        try:
            version = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
        except sqlite3.DatabaseError as exc:
            raise self._fail_closed(f"unreadable: {exc}") from exc
        if version == 0:
            tables = self._table_names()
            if not tables:
                # Fresh (or still empty) database file: initialise.
                self._apply_pragmas()
                self.conn.executescript(_SCHEMA)
                self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                return
            if tables <= _INIT_IN_PROGRESS_TABLES:
                deadline = time.monotonic() + _INIT_WAIT_SECONDS
                while time.monotonic() < deadline:
                    time.sleep(0.05)
                    stamped = int(
                        self.conn.execute("PRAGMA user_version").fetchone()[0]
                    )
                    if stamped == SCHEMA_VERSION:
                        self._complete_stamped_open()
                        return
                raise self._fail_closed(
                    "tables present without a schema version stamp",
                    tables=sorted(tables),
                )
            # Foreign tables: refuse rather than guess.
            raise self._fail_closed(
                "tables present without a schema version stamp", tables=sorted(tables)
            )
        if version != SCHEMA_VERSION:
            raise self._fail_closed(
                "schema version mismatch",
                found=version,
                expected=SCHEMA_VERSION,
            )
        self._complete_stamped_open()

    def _complete_stamped_open(self) -> None:
        """Validate the stamped structure and apply the runtime pragmas."""
        tables = self._table_names()
        missing = {"session_docs", "session_fts"} - tables
        if missing:
            raise self._fail_closed("structurally incomplete", missing=sorted(missing))
        self._apply_pragmas()

    def _apply_pragmas(self) -> None:
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")

    def _table_names(self) -> set[str]:
        try:
            rows = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise self._fail_closed(f"unreadable sqlite_master: {exc}") from exc
        names = {str(row["name"]) for row in rows}
        # Shadow tables of the FTS index are part of the structure.
        return {n for n in names if not n.startswith("session_fts_")}

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def __enter__(self) -> SessionSearchIndex:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- writing -----------------------------------------------------------

    def _upsert_locked(
        self, session_id: str, title: str, body: str, source: str
    ) -> None:
        """Replace one session document (content row + FTS entries) atomically."""
        title = title.strip()
        body = body.strip()
        title_norm = normalize_fa(title)
        body_norm = normalize_fa(body)
        now = time.time()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT id, title_norm, body_norm FROM session_docs WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is not None:
                doc_id = int(row["id"])
                # External content: the old index entries must be removed by
                # hand, with the old values, before rewriting the row.
                self.conn.execute(
                    "INSERT INTO session_fts(session_fts, rowid, title_norm, body_norm)"
                    " VALUES ('delete', ?, ?, ?)",
                    (doc_id, row["title_norm"], row["body_norm"]),
                )
                self.conn.execute(
                    """UPDATE session_docs
                       SET title_orig = ?, body_orig = ?, title_norm = ?,
                           body_norm = ?, updated_at = ?, source = ?
                       WHERE id = ?""",
                    (title, body, title_norm, body_norm, now, source, doc_id),
                )
            else:
                cursor = self.conn.execute(
                    """INSERT INTO session_docs
                       (session_id, title_orig, body_orig, title_norm, body_norm,
                        updated_at, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (session_id, title, body, title_norm, body_norm, now, source),
                )
                doc_id = int(cursor.lastrowid)
            self.conn.execute(
                "INSERT INTO session_fts(rowid, title_norm, body_norm)"
                " VALUES (?, ?, ?)",
                (doc_id, title_norm, body_norm),
            )
            self.conn.execute("COMMIT")
        except Exception:
            try:
                self.conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise

    def index_session(
        self,
        session_id: str,
        title: str,
        messages: Sequence[str],
        source: str = "",
    ) -> None:
        """Index (or re-index) one whole session: title plus every message."""
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        body = "\n".join(message.strip() for message in messages if str(message).strip())
        with self._lock:
            self._upsert_locked(session_id, title, body, source)

    def append_message(
        self, session_id: str, message: str, title: str | None = None, source: str = ""
    ) -> None:
        """Incrementally append one message to a session's document.

        The append event flow's primitive: an existing document grows by one
        line (keeping its title unless *title* overrides); a new session_id
        creates its document.
        """
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        message = str(message).strip()
        with self._lock:
            row = self.conn.execute(
                "SELECT title_orig, body_orig, source FROM session_docs"
                " WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                self._upsert_locked(
                    session_id,
                    title if title is not None else session_id,
                    message,
                    source,
                )
                return
            body = str(row["body_orig"])
            if body:
                body = f"{body}\n{message}"
            else:
                body = message
            self._upsert_locked(
                session_id,
                title if title is not None else str(row["title_orig"]),
                body,
                source or str(row["source"]),
            )

    def remove_session(self, session_id: str) -> bool:
        """Delete one session's document and index entries. False if absent."""
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                row = self.conn.execute(
                    "SELECT id, title_norm, body_norm FROM session_docs"
                    " WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if row is None:
                    self.conn.execute("COMMIT")
                    return False
                self.conn.execute(
                    "INSERT INTO session_fts(session_fts, rowid, title_norm, body_norm)"
                    " VALUES ('delete', ?, ?, ?)",
                    (int(row["id"]), row["title_norm"], row["body_norm"]),
                )
                self.conn.execute(
                    "DELETE FROM session_docs WHERE id = ?", (int(row["id"]),)
                )
                self.conn.execute("COMMIT")
            except Exception:
                try:
                    self.conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    pass
                raise
            return True

    def rebuild(self) -> int:
        """Re-derive the whole FTS index from the content table.

        The documented recovery path after a fail-closed refusal: the content
        table is the source of truth, so this loses no session text.  Returns
        the number of documents re-indexed.
        """
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                count = int(
                    self.conn.execute("SELECT COUNT(*) FROM session_docs").fetchone()[0]
                )
                self.conn.execute(
                    "INSERT INTO session_fts(session_fts) VALUES ('rebuild')"
                )
                self.conn.execute("COMMIT")
            except Exception:
                try:
                    self.conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    pass
                raise
            return count

    # -- reading -----------------------------------------------------------

    def doc_count(self) -> int:
        with self._lock:
            return int(
                self.conn.execute("SELECT COUNT(*) FROM session_docs").fetchone()[0]
            )

    def search(
        self, query: str, limit: int = 20, offset: int = 0
    ) -> list[SessionHit]:
        """Ranked keyword search; every hit carries an original-text snippet.

        The query is normalised through the shared normalizer, tokenised, and
        issued as an OR-MATCH over the normalised columns; ``bm25`` ranks
        (title hits weighted ×3 over body hits) with a deterministic
        ``id DESC`` tie-break so equal scores resolve newest-first, stably.
        """
        tokens = query_tokens(query)
        if not tokens:
            raise SessionIndexError(
                _ERR_QUERY_FA + " Query normalizes to no searchable tokens.",
                query=query,
            )
        match = " OR ".join(_fts_escape(token) for token in tokens)
        sql = (
            "SELECT d.session_id AS sid, d.title_orig AS title,"
            " d.body_orig AS body, d.title_norm AS title_norm,"
            " d.updated_at AS updated_at, d.source AS source,"
            " bm25(session_fts, ?, ?) AS rank"
            " FROM session_fts JOIN session_docs d ON d.id = session_fts.rowid"
            " WHERE session_fts MATCH ?"
            " ORDER BY rank ASC, d.id DESC"
            " LIMIT ? OFFSET ?"
        )
        with self._lock:
            rows = self.conn.execute(
                sql, (TITLE_WEIGHT, BODY_WEIGHT, match, int(limit), int(offset))
            ).fetchall()
        hits: list[SessionHit] = []
        for row in rows:
            title_orig = str(row["title"])
            body_orig = str(row["body"])
            title_norm = str(row["title_norm"])
            matched_in_title = any(
                token in title_norm for token in tokens
            )
            body_snippet = extract_snippet(body_orig, query)
            snippet = body_snippet
            if "[" not in body_snippet and matched_in_title:
                # The body window carries no highlighted word (or the body
                # has none): fall back to the title so the hit still shows
                # a match in context.
                snippet = extract_snippet(title_orig, query)
            hits.append(
                SessionHit(
                    session_id=str(row["sid"]),
                    title=title_orig,
                    snippet=snippet,
                    score=-float(row["rank"]),
                    matched_in_title=matched_in_title,
                    updated_at=float(row["updated_at"]),
                    source=str(row["source"]),
                )
            )
        return hits
