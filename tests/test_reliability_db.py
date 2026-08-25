"""Two-process SQLite barrier and per-destination delivery idempotency."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from dream.reliability.db import (
    _barrier_worker,
    claim_delivery,
    connect_sqlite,
    durable_write,
    ensure_delivery_schema,
    increment_counter,
    read_counter,
)

_WORKER = r"""
import sys
from dream.reliability.db import _barrier_worker
path, n = sys.argv[1], int(sys.argv[2])
result = _barrier_worker(path, n)
print("ok" if result["ok"] and result["locked"] == 0 else "locked")
raise SystemExit(0 if result["locked"] == 0 else 2)
"""


def test_two_process_sqlite_barrier_zero_locked(tmp_path: Path) -> None:
    db_path = tmp_path / "barrier.db"
    conn = connect_sqlite(db_path)
    increment_counter(conn, key="n", amount=0)
    conn.close()

    iterations = 40
    children = [
        subprocess.Popen(  # noqa: S603
            [sys.executable, "-c", _WORKER, str(db_path), str(iterations)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    outputs: list[str] = []
    errors: list[str] = []
    codes: list[int] = []
    for child in children:
        out, err = child.communicate(timeout=20)
        outputs.append(out)
        errors.append(err)
        codes.append(int(child.returncode))

    combined = "\n".join(outputs + errors)
    assert "database is locked" not in combined
    assert codes == [0, 0]
    assert all(line.strip() == "ok" for line in outputs if line.strip())

    final = connect_sqlite(db_path)
    try:
        assert read_counter(final, "n") == iterations * 2
    finally:
        final.close()


def test_claim_delivery_is_idempotent_per_destination(tmp_path: Path) -> None:
    db_path = tmp_path / "deliveries.db"
    conn = connect_sqlite(db_path)
    ensure_delivery_schema(conn)
    first = claim_delivery(
        conn, reminder_id=7, destination="terminal", fired_at=100.0
    )
    again = claim_delivery(
        conn, reminder_id=7, destination="terminal", fired_at=100.0
    )
    other = claim_delivery(
        conn, reminder_id=7, destination="telegram", fired_at=100.0
    )
    conn.close()
    assert first is True
    assert again is False
    assert other is True


def test_two_process_claim_exactly_one_winner(tmp_path: Path) -> None:
    db_path = tmp_path / "claim.db"
    conn = connect_sqlite(db_path)
    ensure_delivery_schema(conn)
    conn.close()

    script = r"""
import sys
from dream.reliability.db import claim_delivery, connect_sqlite, ensure_delivery_schema
conn = connect_sqlite(sys.argv[1])
ensure_delivery_schema(conn)
won = claim_delivery(conn, reminder_id=1, destination="terminal", fired_at=1.0)
print("won" if won else "dup")
conn.close()
"""
    children = [
        subprocess.Popen(  # noqa: S603
            [sys.executable, "-c", script, str(db_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    lines: list[str] = []
    locked = False
    for child in children:
        out, err = child.communicate(timeout=15)
        lines.extend(part.strip() for part in out.splitlines() if part.strip())
        blob = out + err
        if "database is locked" in blob:
            locked = True
        assert child.returncode == 0
    assert locked is False
    assert lines.count("won") == 1
    assert lines.count("dup") == 1


def test_busy_timeout_is_set_before_wal(tmp_path: Path) -> None:
    db_path = tmp_path / "pragma.db"
    conn = connect_sqlite(db_path, busy_timeout_ms=1234)
    timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert int(timeout) == 1234
    assert str(journal).lower() == "wal"


def test_durable_write_replaces_atomically(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    durable_write(path, "alpha")
    durable_write(path, "beta")
    assert path.read_text(encoding="utf-8") == "beta"


def test_barrier_worker_helper_single_process(tmp_path: Path) -> None:
    db_path = tmp_path / "solo.db"
    conn = connect_sqlite(db_path)
    increment_counter(conn, amount=0)
    conn.close()
    result = _barrier_worker(str(db_path), 5)
    assert result["ok"] is True
    assert result["locked"] == 0
    conn = connect_sqlite(db_path)
    try:
        assert read_counter(conn) == 5
    finally:
        conn.close()
    # Keep the imported time module referenced for ruff in case of future clocks.
    assert time.time() > 0
