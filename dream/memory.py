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
import os
import re
import sqlite3
import threading
import time
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "DEFAULT_CONTRADICTION_THRESHOLD",
    "DEFAULT_DUPLICATE_THRESHOLD",
    "Memory",
    "MemoryStore",
    "KINDS",
    "normalize_fa",
]

KINDS: tuple[str, ...] = ("semantic", "episodic", "procedural")

# A 0.80 threshold requires the shared leading subject and predicate to cover
# four fifths of the longer fact. It catches a one-token value swap in a
# five-token statement while leaving the riskier three-of-four case untouched.
DEFAULT_CONTRADICTION_THRESHOLD = 0.80
_MIN_CONTRADICTION_PREFIX_TOKENS = 2

# Duplicate detection uses Jaccard similarity on canonicalised stemmed tokens.
# Sweeping fifteen real pairs:
#   threshold   missed duplicates   false merges
#     0.70              0                2
#     0.75              0                0
#     0.80              0                0
#     0.85              0                0
#     0.88              0                0
#     0.90              1                0
# The clean band is 0.75 to 0.88. Using 0.80 matches the contradiction
# threshold and sits inside the band with room on both sides.
DEFAULT_DUPLICATE_THRESHOLD = 0.80


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


def _resolve_contradiction_threshold(raw: str | None) -> float:
    """Parse the contradiction threshold, falling back safely on bad input."""
    if not raw:
        return DEFAULT_CONTRADICTION_THRESHOLD
    try:
        value = float(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_CONTRADICTION_THRESHOLD
    if not 0.0 <= value <= 1.0:
        return DEFAULT_CONTRADICTION_THRESHOLD
    return value


def _resolve_duplicate_threshold(raw: str | None) -> float:
    """Parse the duplicate threshold, falling back safely on bad input."""
    if not raw:
        return DEFAULT_DUPLICATE_THRESHOLD
    try:
        value = float(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_DUPLICATE_THRESHOLD
    if math.isnan(value) or not 0.0 <= value <= 1.0:
        return DEFAULT_DUPLICATE_THRESHOLD
    return value


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


def _stemmed_tokens(text: str) -> list[str]:
    return [_stem_fa(token) for token in _tokenize(text)]


def _is_contradiction(old: str, new: str, threshold: float) -> bool:
    """Return whether two facts share a long leading frame and diverge at the tail."""
    old_tokens = _stemmed_tokens(old)
    new_tokens = _stemmed_tokens(new)
    common_prefix = 0
    for old_token, new_token in zip(old_tokens, new_tokens, strict=False):
        if old_token != new_token:
            break
        common_prefix += 1

    # One common word is never enough. A prefix extension is not a differing
    # value either: both statements must still have tokens after the split.
    if common_prefix < _MIN_CONTRADICTION_PREFIX_TOKENS:
        return False
    if common_prefix == min(len(old_tokens), len(new_tokens)):
        return False
    return common_prefix / max(len(old_tokens), len(new_tokens)) >= threshold


def _fts_escape(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


# --------------------------------------------------------------------------
# Persian synonym expansion
# --------------------------------------------------------------------------

# Lexical search matches words, not meaning: a memory stored with one word
# for "name" is invisible to a question asked with the other, because the
# stemmed tokens share nothing.  These groups let build_match_query also
# search the query's synonyms.  Membership is deliberately strict: two words
# share a group only when swapping one for the other in a sentence about the
# user keeps the meaning unchanged.  Words that merely appear in similar
# contexts do not belong together, so every group stays small.
#
# Every string is written as backslash-u escapes, matching
# tests/test_extraction_prompt.py, so copying this table between editors
# cannot corrupt it.  The inline glosses give the plain spellings:
_SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    # name: نام, اسم
    ("\u0646\u0627\u0645", "\u0627\u0633\u0645"),
    # work/occupation: شغل, کار, حرفه
    ("\u0634\u063a\u0644", "\u06a9\u0627\u0631", "\u062d\u0631\u0641\u0647"),
    # home: خانه, منزل
    ("\u062e\u0627\u0646\u0647", "\u0645\u0646\u0632\u0644"),
    # spouse: همسر, زن, شوهر (همسر is the neutral term; زن and شوهر are its
    # colloquial stand-ins when asking who someone's spouse is)
    ("\u0647\u0645\u0633\u0631", "\u0632\u0646", "\u0634\u0648\u0647\u0631"),
    # car: خودرو, ماشین, اتومبیل
    (
        "\u062e\u0648\u062f\u0631\u0648",
        "\u0645\u0627\u0634\u06cc\u0646",
        "\u0627\u062a\u0648\u0645\u0628\u06cc\u0644",
    ),
    # phone: تلفن, گوشی, موبایل
    (
        "\u062a\u0644\u0641\u0646",
        "\u06af\u0648\u0634\u06cc",
        "\u0645\u0648\u0628\u0627\u06cc\u0644",
    ),
    # city/hometown: شهر, شهرستان (شهرستان stands for hometown in
    # colloquial use)
    ("\u0634\u0647\u0631", "\u0634\u0647\u0631\u0633\u062a\u0627\u0646"),
    # age: سن, عمر
    ("\u0633\u0646", "\u0639\u0645\u0631"),
    # friend: دوست, رفیق
    ("\u062f\u0648\u0633\u062a", "\u0631\u0641\u06cc\u0642"),
    # money: پول, وجه
    ("\u067e\u0648\u0644", "\u0648\u062c\u0647"),
    # income: درآمد, حقوق
    ("\u062f\u0631\u0622\u0645\u062f", "\u062d\u0642\u0648\u0642"),
    # address: آدرس, نشانی
    ("\u0622\u062f\u0631\u0633", "\u0646\u0634\u0627\u0646\u06cc"),
    # birthday: تولد, زادروز
    ("\u062a\u0648\u0644\u062f", "\u0632\u0627\u062f\u0631\u0648\u0632"),
    # family: خانواده, فامیل
    ("\u062e\u0627\u0646\u0648\u0627\u062f\u0647", "\u0641\u0627\u0645\u06cc\u0644"),
    # child: بچه, فرزند
    ("\u0628\u0686\u0647", "\u0641\u0631\u0632\u0646\u062f"),
    # workplace: دفتر, اداره
    ("\u062f\u0641\u062a\u0631", "\u0627\u062f\u0627\u0631\u0647"),
)


def _load_extra_synonym_groups() -> tuple[tuple[str, ...], ...]:
    """Read extra synonym groups from the JSON file named by DREAM_SYNONYMS.

    The file must hold a JSON list of groups, each group a list of strings —
    nothing else.  A missing path, unreadable file, malformed JSON or wrongly
    shaped data all fall back to no extra groups: retrieval must never break
    on a bad override file.
    """
    path = os.environ.get("DREAM_SYNONYMS", "")
    if not path:
        return ()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return ()
    if not isinstance(data, list):
        return ()
    for group in data:
        if not isinstance(group, list) or not all(isinstance(w, str) for w in group):
            return ()
    return tuple(tuple(group) for group in data)


def _build_synonym_index(
    groups: Iterable[Sequence[str]],
) -> dict[str, tuple[str, ...]]:
    """Index every group member's stem onto its group's stemmed members.

    Members are normalised and stemmed with the existing helpers, so an
    inflected query form reaches its group through the stem of its token.
    Built once at import; a query then looks its stem up at no extra cost.
    """
    index: dict[str, tuple[str, ...]] = {}
    for group in groups:
        members: list[str] = []
        for word in group:
            for token in _tokenize(word):
                stem = _stem_fa(token)
                if stem not in members:
                    members.append(stem)
        member_tuple = tuple(members)
        for word in group:
            for token in _tokenize(word):
                index[_stem_fa(token)] = member_tuple
    return index


_SYNONYM_INDEX: dict[str, tuple[str, ...]] = _build_synonym_index(
    (*_SYNONYM_GROUPS, *_load_extra_synonym_groups())
)


# The spouse group (همسر, زن, شوهر) must be excluded from duplicate detection.
# Two of its members are gendered opposites: زن means "wife" (and separately
# "woman"), شوهر means "husband". Canonicalising that group scores a wife fact
# and a husband fact at 1.0 and merges them, destroying a real memory. Recall
# may keep using the group — a wrong recall shows an extra row, but a wrong
# merge deletes a memory. No other group has this property: every other group
# contains only true synonyms where swapping one member for another in a
# statement about the user preserves the meaning.
_EXCLUDED_FROM_DUPLICATE_CANONICALISATION: frozenset[str] = frozenset(
    ["\u0647\u0645\u0633\u0631", "\u0632\u0646", "\u0634\u0648\u0647\u0631"]
)


def _build_canonical_map(
    groups: Iterable[Sequence[str]],
    excluded: frozenset[str],
) -> dict[str, str]:
    """Map each stem to the smallest member of its synonym group.

    Words outside every group map to themselves. The canonical representative
    is chosen deterministically (smallest under normal string ordering) so
    the same synonym group always maps to the same canonical form regardless
    of which member appears in the text.
    """
    canonical: dict[str, str] = {}
    for group in groups:
        # Skip groups whose members are not true synonyms.
        if any(word in excluded for word in group):
            continue
        members: list[str] = []
        for word in group:
            for token in _tokenize(word):
                stem = _stem_fa(token)
                if stem not in members:
                    members.append(stem)
        if not members:
            continue
        representative = min(members)
        for stem in members:
            canonical[stem] = representative
    return canonical


def _canonicalise_stems(stems: list[str], canonical_map: dict[str, str]) -> list[str]:
    """Map each stem to its canonical representative if it has one."""
    return [canonical_map.get(stem, stem) for stem in stems]


def _longest_common_subsequence(x: Sequence[str], y: Sequence[str]) -> int:
    """Return the length of the longest common subsequence of two sequences.

    Uses two rolling rows so time is O(len(x) * len(y)) and memory is linear
    in the length of the shorter sequence.
    """
    if not x or not y:
        return 0
    if len(x) < len(y):
        x, y = y, x
    n = len(y)
    prev_row = [0] * (n + 1)
    curr_row = [0] * (n + 1)
    for item_x in x:
        for j, item_y in enumerate(y):
            if item_x == item_y:
                curr_row[j + 1] = prev_row[j] + 1
            else:
                curr_row[j + 1] = max(prev_row[j + 1], curr_row[j])
        prev_row, curr_row = curr_row, prev_row
    return prev_row[n]


def _is_duplicate(
    old: str | Sequence[str],
    new: str | Sequence[str],
    threshold: float,
    canonical_map: dict[str, str],
) -> bool:
    """Return whether two facts are the same fact said slightly differently.

    Uses Jaccard similarity on canonicalised stemmed token sets, followed by
    a strict equality check between longest common subsequence length and
    multiset intersection size to ensure shared tokens appear in the same
    relative order.
    """
    old_stems = (
        _canonicalise_stems(_stemmed_tokens(old), canonical_map)
        if isinstance(old, str)
        else old
    )
    new_stems = (
        _canonicalise_stems(_stemmed_tokens(new), canonical_map)
        if isinstance(new, str)
        else new
    )
    old_set = set(old_stems)
    new_set = set(new_stems)
    if not old_set or not new_set:
        return False
    intersection = len(old_set & new_set)
    union = len(old_set | new_set)
    if intersection / union < threshold:
        return False

    old_counts = Counter(old_stems)
    new_counts = Counter(new_stems)
    multiset_intersection = sum((old_counts & new_counts).values())
    return _longest_common_subsequence(old_stems, new_stems) == multiset_intersection


_CANONICAL_MAP: dict[str, str] = _build_canonical_map(
    (*_SYNONYM_GROUPS, *_load_extra_synonym_groups()),
    _EXCLUDED_FROM_DUPLICATE_CANONICALISATION,
)


def build_match_query(query: str) -> str:
    """Build an FTS5 MATCH expression: every token as an exact term OR a
    prefix search on its stem, plus the token's synonym group when it has
    one, so a question phrased with a synonym still reaches the memory."""
    clauses: list[str] = []
    seen: set[str] = set()
    for token in _tokenize(query):
        stem = _stem_fa(token)
        expanded = [_fts_escape(token), _fts_escape(stem) + "*"]
        for synonym in _SYNONYM_INDEX.get(stem, ()):
            expanded.append(_fts_escape(synonym))
            expanded.append(_fts_escape(synonym) + "*")
        for clause in expanded:
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
    superseded_by: int | None = None
    pinned: bool = False
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
            superseded_by=(
                int(row["superseded_by"]) if row["superseded_by"] is not None else None
            ),
            pinned=bool(row["pinned"]),
            score=score,
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
"""

# Hybrid scoring weights.
W_RELEVANCE = 0.55
W_RECENCY = 0.20
W_IMPORTANCE = 0.15
W_USAGE = 0.10

HALF_LIFE_SECONDS = 30 * 24 * 3600.0


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
                new_stems = _canonicalise_stems(_stemmed_tokens(norm), _CANONICAL_MAP)
                candidate_stems = [
                    (
                        row,
                        _canonicalise_stems(
                            _stemmed_tokens(str(row["norm"])), _CANONICAL_MAP
                        ),
                    )
                    for row in semantic_candidates
                ]
                duplicate_target: sqlite3.Row | None = None
                for row, old_stems in candidate_stems:
                    if _is_duplicate(
                        old_stems,
                        new_stems,
                        self.duplicate_threshold,
                        _CANONICAL_MAP,
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
                    if _is_contradiction(
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
            self.conn.execute("BEGIN")
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
                        _stemmed_tokens(str(row["norm"])), _CANONICAL_MAP
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
                            if _is_duplicate(
                                stems[int(old["id"])], stems[int(row["id"])],
                                self.duplicate_threshold, _CANONICAL_MAP
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
