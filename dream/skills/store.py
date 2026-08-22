"""Per-skill versioning and use-outcome log (MEM Stage C).

Skill *files* stay in ``skills/``.  This store is the append-only ledger
those files cannot be: every write records a new version (nothing is
ever overwritten in place in this database), and every invocation
records an outcome the Stage D proposal loop will read.

Serialization matches the Stage A/B discipline: one ``threading.RLock``,
``BEGIN IMMEDIATE`` on writes, ``busy_timeout=5000``.  Standard library
only.  Default path ``data/dream-skills.db``, override ``DREAM_SKILLS_DB``.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from dataclasses import dataclass

__all__ = [
    "DEFAULT_SKILLS_DB_PATH",
    "SCHEMA_VERSION",
    "SkillLedger",
    "SkillUse",
    "SkillVersion",
]

SCHEMA_VERSION = 1
DEFAULT_SKILLS_DB_PATH = "data/dream-skills.db"
_BUSY_TIMEOUT_MS = 5_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS skill_versions (
    name       TEXT    NOT NULL,
    version    INTEGER NOT NULL,
    content    TEXT    NOT NULL,
    kind       TEXT    NOT NULL DEFAULT 'legacy',
    created_at REAL    NOT NULL,
    PRIMARY KEY (name, version)
);
CREATE TABLE IF NOT EXISTS skill_uses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    invoked_at  REAL    NOT NULL,
    outcome     TEXT    NOT NULL,
    duration_ms REAL    NOT NULL,
    source      TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_skill_uses_name ON skill_uses(name, invoked_at);
"""


@dataclass(frozen=True, slots=True)
class SkillVersion:
    """One immutable snapshot of a skill's file text."""

    name: str
    version: int
    content: str
    kind: str
    created_at: float


@dataclass(frozen=True, slots=True)
class SkillUse:
    """One invocation outcome (slash, skill_view, use_skill, ...)."""

    name: str
    invoked_at: float
    outcome: str
    duration_ms: float
    source: str


class SkillLedger:
    """Append-only version + use log. Never overwrites a version row."""

    def __init__(self, path: str = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            parent = os.path.dirname(os.path.abspath(self.path))
            if parent:
                os.makedirs(parent, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(
            self.path, check_same_thread=False, isolation_level=None
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        self.conn.executescript(_SCHEMA)
        self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    @classmethod
    def from_env(cls) -> SkillLedger:
        return cls(os.environ.get("DREAM_SKILLS_DB", DEFAULT_SKILLS_DB_PATH))

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def __enter__(self) -> SkillLedger:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def latest_version(self, name: str) -> int:
        """Highest stored version for ``name``, or 0 when none exist."""
        with self._lock:
            row = self.conn.execute(
                "SELECT MAX(version) AS v FROM skill_versions WHERE name = ?",
                (name,),
            ).fetchone()
        if row is None or row["v"] is None:
            return 0
        return int(row["v"])

    def record_version(self, name: str, content: str, kind: str = "legacy") -> int:
        """Append a new version. Existing rows are never updated.

        Returns the version number that was written.  If ``content`` is
        byte-identical to the latest stored snapshot, the latest version
        is returned and no row is added — a no-op is not an overwrite.
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError("skill name must be a non-empty string")
        if not isinstance(content, str):
            raise ValueError("content must be a string")
        name = name.strip()
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                row = self.conn.execute(
                    "SELECT version, content FROM skill_versions"
                    " WHERE name = ? ORDER BY version DESC LIMIT 1",
                    (name,),
                ).fetchone()
                if row is not None and str(row["content"]) == content:
                    self.conn.execute("COMMIT")
                    return int(row["version"])
                nxt = 1 if row is None else int(row["version"]) + 1
                self.conn.execute(
                    "INSERT INTO skill_versions (name, version, content, kind, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (name, nxt, content, kind, time.time()),
                )
                self.conn.execute("COMMIT")
            except Exception:
                try:
                    self.conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    pass
                raise
        return nxt

    def versions(self, name: str) -> list[SkillVersion]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT name, version, content, kind, created_at"
                " FROM skill_versions WHERE name = ? ORDER BY version",
                (name.strip(),),
            ).fetchall()
        return [
            SkillVersion(
                name=str(row["name"]),
                version=int(row["version"]),
                content=str(row["content"]),
                kind=str(row["kind"]),
                created_at=float(row["created_at"]),
            )
            for row in rows
        ]

    def log_use(
        self,
        name: str,
        outcome: str,
        duration_ms: float = 0.0,
        source: str = "",
    ) -> None:
        """Append one use-outcome row. Never updates a previous row."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("skill name must be a non-empty string")
        if not isinstance(outcome, str) or not outcome.strip():
            raise ValueError("outcome must be a non-empty string")
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.execute(
                    "INSERT INTO skill_uses (name, invoked_at, outcome, duration_ms, source)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (name.strip(), time.time(), outcome.strip(), float(duration_ms), source),
                )
                self.conn.execute("COMMIT")
            except Exception:
                try:
                    self.conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    pass
                raise

    def uses(self, name: str | None = None) -> list[SkillUse]:
        with self._lock:
            if name is None:
                rows = self.conn.execute(
                    "SELECT name, invoked_at, outcome, duration_ms, source"
                    " FROM skill_uses ORDER BY id"
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT name, invoked_at, outcome, duration_ms, source"
                    " FROM skill_uses WHERE name = ? ORDER BY id",
                    (name.strip(),),
                ).fetchall()
        return [
            SkillUse(
                name=str(row["name"]),
                invoked_at=float(row["invoked_at"]),
                outcome=str(row["outcome"]),
                duration_ms=float(row["duration_ms"]),
                source=str(row["source"]),
            )
            for row in rows
        ]


def get_ledger() -> SkillLedger:
    """Open the ledger at ``DREAM_SKILLS_DB`` (or the default path).

    A fresh connection is returned each time.  A process-wide cached
    connection would be inherited by ``multiprocessing`` tests and can
    deadlock on the SQLite file lock; callers that need several
    operations on one handle construct :class:`SkillLedger` themselves.
    """
    return SkillLedger.from_env()


def reset_ledger_for_tests() -> None:
    """Kept for test fixtures that previously dropped a process handle."""
    return None
