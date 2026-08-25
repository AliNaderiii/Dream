"""SQLite concurrency helpers: busy timeout, IMMEDIATE writes, idempotency.

These are **helpers**. They do not rewrite ``dream.reminders`` or
``dream.memory_stores``. Owners opt in at their call sites.

Invariant: ``PRAGMA busy_timeout`` is set **before** ``journal_mode=WAL``.
Setting WAL first lets a second process raise ``database is locked``
during the WAL handshake.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")

DEFAULT_BUSY_TIMEOUT_MS = 5_000
MAX_BUSY_TIMEOUT_MS = 30_000
DEFAULT_RETRIES = 5
_RETRY_BACKOFF = (0.01, 0.03, 0.09, 0.20, 0.40)

__all__ = [
    "DEFAULT_BUSY_TIMEOUT_MS",
    "begin_immediate",
    "claim_delivery",
    "connect_sqlite",
    "durable_write",
    "ensure_delivery_schema",
    "is_locked_error",
    "run_transaction",
]


def _clamp_busy_timeout_ms(value: int | float) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_BUSY_TIMEOUT_MS
    if number < 0:
        return 0
    if number > MAX_BUSY_TIMEOUT_MS:
        return MAX_BUSY_TIMEOUT_MS
    return number


def is_locked_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "locked" in text or "busy" in text


def connect_sqlite(
    path: str | os.PathLike[str],
    *,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    wal: bool = True,
    check_same_thread: bool = False,
) -> sqlite3.Connection:
    """Open SQLite with ``busy_timeout`` applied *before* WAL.

    ``isolation_level=None`` puts the connection in autocommit mode so
    :func:`begin_immediate` can take the reserved lock itself.
    """
    timeout_ms = _clamp_busy_timeout_ms(busy_timeout_ms)
    timeout_s = timeout_ms / 1000.0
    conn = sqlite3.connect(
        str(path),
        timeout=timeout_s,
        check_same_thread=check_same_thread,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    # Order is load-bearing. busy_timeout must precede journal_mode=WAL.
    conn.execute(f"PRAGMA busy_timeout = {timeout_ms}")
    if wal:
        conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def begin_immediate(conn: sqlite3.Connection) -> None:
    """Take the reserved lock for a read-before-write transaction."""
    conn.execute("BEGIN IMMEDIATE")


def run_transaction(
    conn: sqlite3.Connection,
    fn: Callable[[sqlite3.Connection], T],
    *,
    retries: int = DEFAULT_RETRIES,
) -> T:
    """Run *fn* inside ``BEGIN IMMEDIATE`` with locked-retry backoff."""
    attempts = 1 if retries < 1 else int(retries)
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            begin_immediate(conn)
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if is_locked_error(exc) and attempt + 1 < attempts:
                time.sleep(_RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)])
                continue
            raise
        try:
            result = fn(conn)
            conn.execute("COMMIT")
            return result
        except sqlite3.OperationalError as exc:
            last_exc = exc
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            if is_locked_error(exc) and attempt + 1 < attempts:
                time.sleep(_RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)])
                continue
            raise
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("transaction failed without an exception")


def durable_write(
    path: str | os.PathLike[str],
    data: str | bytes,
    *,
    encoding: str = "utf-8",
) -> None:
    """Atomic write: temp file, ``fsync``, ``os.replace``."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(
        dir=str(destination.parent), prefix=".dream-rel-", suffix=".tmp"
    )
    try:
        if isinstance(data, str):
            with os.fdopen(handle, "w", encoding=encoding) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        else:
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(tmp_name, destination)
        tmp_name = ""
    finally:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


DELIVERIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS reliability_deliveries (
    reminder_id INTEGER NOT NULL,
    destination TEXT NOT NULL,
    fired_at REAL NOT NULL,
    delivered_at REAL NOT NULL,
    PRIMARY KEY (reminder_id, destination, fired_at)
)
"""


def ensure_delivery_schema(conn: sqlite3.Connection) -> None:
    """Create the per-destination delivery table if it does not exist."""
    conn.execute(DELIVERIES_SCHEMA)


def claim_delivery(
    conn: sqlite3.Connection,
    *,
    reminder_id: int,
    destination: str,
    fired_at: float,
    delivered_at: float | None = None,
) -> bool:
    """Idempotent per-destination claim. ``True`` if this caller won.

    Modelled on ``dream.reminders.check_due_reminders`` (destination +
    fired_at uniqueness) but kept as a helper so reminders.py is not edited.
    """
    when = time.time() if delivered_at is None else float(delivered_at)

    def _insert(txn: sqlite3.Connection) -> bool:
        cursor = txn.execute(
            "INSERT OR IGNORE INTO reliability_deliveries "
            "(reminder_id, destination, fired_at, delivered_at) "
            "VALUES (?, ?, ?, ?)",
            (int(reminder_id), str(destination), float(fired_at), when),
        )
        return int(cursor.rowcount) == 1

    return run_transaction(conn, _insert)


def increment_counter(conn: sqlite3.Connection, key: str = "n", amount: int = 1) -> int:
    """Transactional integer increment. Used by the two-process barrier test."""

    def _bump(txn: sqlite3.Connection) -> int:
        txn.execute(
            "CREATE TABLE IF NOT EXISTS reliability_kv ("
            "k TEXT PRIMARY KEY, v INTEGER NOT NULL)"
        )
        txn.execute(
            "INSERT OR IGNORE INTO reliability_kv (k, v) VALUES (?, 0)",
            (key,),
        )
        txn.execute(
            "UPDATE reliability_kv SET v = v + ? WHERE k = ?",
            (int(amount), key),
        )
        row = txn.execute(
            "SELECT v FROM reliability_kv WHERE k = ?",
            (key,),
        ).fetchone()
        return int(row[0]) if row is not None else 0

    return run_transaction(conn, _bump)


def read_counter(conn: sqlite3.Connection, key: str = "n") -> int:
    row = conn.execute(
        "SELECT v FROM reliability_kv WHERE k = ?",
        (key,),
    ).fetchone()
    return int(row[0]) if row is not None else 0


# Worker entry point for the two-process barrier (imported by tests / soak).
def _barrier_worker(db_path: str, iterations: int, key: str = "n") -> dict[str, Any]:
    conn = connect_sqlite(db_path)
    locked = 0
    try:
        for _ in range(int(iterations)):
            try:
                increment_counter(conn, key=key, amount=1)
            except sqlite3.OperationalError as exc:
                if is_locked_error(exc):
                    locked += 1
                raise
        return {"ok": True, "locked": locked}
    finally:
        conn.close()
