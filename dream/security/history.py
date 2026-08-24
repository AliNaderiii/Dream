"""Durable approval history (layer L2, SEC-G-07).

An append-only SQLite ledger of every security decision Dream makes: floor
blocks, assessor verdicts, human approvals and denials, off-mode
allowances, and autonomous-context denials. It is the audit trail (asset A8
in the threat model) behind the Security Center's approval-history surface.

Storage conventions follow the other Dream stores:

* Path: ``DREAM_APPROVAL_DB`` env override, default ``data/dream-approvals.db``.
* Missing file: initialised fresh with the schema stamped.
* Corruption: fail closed and out loud. Reads raise a bilingual
  :class:`ApprovalStoreError`; the file is NEVER wiped or silently
  rebuilt. The engine keeps protecting the owner even when the audit
  trail cannot be read — actions fail closed independently of the log,
  and a failed append is reported loudly, never raised into the turn.
* Append-only protocol: this module contains INSERT and CREATE statements
  only — no UPDATE, no DELETE, no DROP (pinned by test).
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

__all__ = [
    "APPROVAL_DB_ENV",
    "ApprovalHistory",
    "ApprovalStoreError",
    "DEFAULT_APPROVAL_DB",
]

APPROVAL_DB_ENV = "DREAM_APPROVAL_DB"
DEFAULT_APPROVAL_DB = "data/dream-approvals.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS approval_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    context TEXT NOT NULL,
    mode TEXT NOT NULL,
    tool TEXT NOT NULL,
    command TEXT NOT NULL,
    verdict TEXT NOT NULL,
    rule_class TEXT,
    detail TEXT
);
"""

_ERROR_EN = "approval history is unreadable; refusing to list it until rebuilt"
_ERROR_FA = (
    "\u062a\u0627\u0631\u06cc\u062e\u0686\u0647\u200c\u06cc "
    "\u062a\u0623\u06cc\u06cc\u062f\u0647\u0627 "
    "\u063a\u06cc\u0631\u0642\u0627\u0628\u0644 \u062e\u0648\u0627\u0646\u062f\u0646 "
    "\u0627\u0633\u062a\u061b "
    "\u062a\u0627 \u0628\u0627\u0632\u0633\u0627\u0632\u06cc \u0646\u0634\u0648\u062f "
    "\u0641\u0647\u0631\u0633\u062a "
    "\u0622\u0646 \u0646\u0634\u0627\u0646 \u062f\u0627\u062f\u0647 "
    "\u0646\u0645\u06cc\u200c\u0634\u0648\u062f"
)


class ApprovalStoreError(RuntimeError):
    """The history store is corrupt; reads fail closed, never wipe."""

    def __init__(self) -> None:
        super().__init__(f"{_ERROR_EN} / {_ERROR_FA}")


class ApprovalHistory:
    """Append-only approval event log over one SQLite file."""

    def __init__(self, path: str | None = None) -> None:
        env = os.environ.get(APPROVAL_DB_ENV, "").strip()
        self.path = str(path or env or DEFAULT_APPROVAL_DB)
        self._lock = threading.RLock()
        self._broken = False
        self._open()

    # -- lifecycle ------------------------------------------------------- #

    def _open(self) -> None:
        try:
            if self.path != ":memory:":
                parent = os.path.dirname(os.path.abspath(self.path))
                os.makedirs(parent, exist_ok=True)
            connection = sqlite3.connect(self.path, check_same_thread=False)
            connection.execute("PRAGMA journal_mode=WAL;")
            connection.executescript(_SCHEMA)
            # A structurally present but internally corrupt file must fail
            # closed here, at open/init time, not mid-turn.
            connection.execute("SELECT COUNT(*) FROM approval_events").fetchone()
        except (sqlite3.DatabaseError, sqlite3.OperationalError, OSError) as exc:
            self._broken = True
            raise ApprovalStoreError() from exc
        self._connection = connection

    # -- writes (append-only; a failed append never breaks the turn) ----- #

    def record(
        self,
        *,
        verdict: str,
        tool: str,
        command: str,
        mode: str,
        context: str = "interactive",
        rule_class: str | None = None,
        detail: str | None = None,
        ts: float | None = None,
    ) -> bool:
        """Append one event. Returns False (loudly logged) when unwritable."""
        with self._lock:
            if self._broken:
                return False
            try:
                self._connection.execute(
                    "INSERT INTO approval_events"
                    " (ts, context, mode, tool, command, verdict, rule_class, detail)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        time.time() if ts is None else ts,
                        context,
                        mode,
                        tool,
                        command,
                        verdict,
                        rule_class,
                        detail,
                    ),
                )
                self._connection.commit()
                return True
            except sqlite3.DatabaseError:
                self._broken = True
                return False

    # -- reads (fail closed on corruption) -------------------------------- #

    def entries(self, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        """Newest-first event rows; raises :class:`ApprovalStoreError` if corrupt."""
        with self._lock:
            if self._broken:
                raise ApprovalStoreError()
            try:
                rows = self._connection.execute(
                    "SELECT id, ts, context, mode, tool, command, verdict, rule_class, detail"
                    " FROM approval_events ORDER BY id DESC LIMIT ? OFFSET ?",
                    (max(1, min(int(limit), 1000)), max(0, int(offset))),
                ).fetchall()
            except sqlite3.DatabaseError as exc:
                self._broken = True
                raise ApprovalStoreError() from exc
            return [
                {
                    "id": row[0],
                    "ts": row[1],
                    "context": row[2],
                    "mode": row[3],
                    "tool": row[4],
                    "command": row[5],
                    "verdict": row[6],
                    "rule_class": row[7],
                    "detail": row[8],
                }
                for row in rows
            ]

    def count(self) -> int:
        with self._lock:
            if self._broken:
                raise ApprovalStoreError()
            try:
                row = self._connection.execute("SELECT COUNT(*) FROM approval_events").fetchone()
            except sqlite3.DatabaseError as exc:
                self._broken = True
                raise ApprovalStoreError() from exc
            return int(row[0])

    def close(self) -> None:
        with self._lock:
            if not self._broken:
                self._connection.close()


def default_history_path() -> Path:
    """The path the default store lives at, honouring the env override."""
    return Path(os.environ.get(APPROVAL_DB_ENV, "").strip() or DEFAULT_APPROVAL_DB)
