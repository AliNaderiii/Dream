"""Pin that two operating-system processes running the due check at the same
instant are never refused by the store.

M6 wrapped the due check in a single ``BEGIN IMMEDIATE`` transaction so two
callers cannot both fire and advance the same reminder. The original defect
hid for weeks because the store serialises its own work with an in-process
``RLock``: a threaded test always passed while two real processes still raised
``sqlite3.OperationalError: database is locked``. Before the transaction fix
this was measured at 29 of 30 barrier-synchronised trials raising the error;
after the fix, 0 of 30.

Threads cannot reproduce the defect — the in-process lock hides it — so the
test below forks real processes with the ``multiprocessing`` module and meets
them at a ``Barrier`` so both arrive at the check together. It also pins that
the two concurrent checks still fire the reminder exactly once between them,
now across processes rather than across threads.
"""

from __future__ import annotations

import multiprocessing
import sqlite3
import sys
import time

import pytest

from dream.memory import MemoryStore

# The measured evidence: 30 barrier-synchronised trials, 0 refused after the
# transaction fix (29 of 30 before it). Thirty is the floor the brief sets.
TRIALS = 30


def _due_check_worker(db_path, barrier, result_queue):
    """Open a fresh store, wait at the barrier, then run one due check.

    Runs in a child process. The barrier makes both children reach the
    ``check_due_reminders`` call at the same instant. The result lands on
    ``result_queue`` as ``("ok", fired_count)`` or ``("error", message)``.
    The store is closed in a ``finally`` so the child never leaks an open
    SQLite connection back to the parent.
    """
    store = MemoryStore(db_path)
    try:
        barrier.wait()
        try:
            fired = store.check_due_reminders()
            result_queue.put(("ok", len(fired)))
        except sqlite3.OperationalError as exc:
            result_queue.put(("error", str(exc)))
    finally:
        store.close()


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="fork start method exists only on Unix (multiprocessing.get_context('fork') not available on Windows)",  # noqa: E501
)
def test_two_real_processes_hitting_the_due_check_at_once_are_never_refused(tmp_path):
    """Thirty barrier trials: zero raises, and the reminder fires exactly once.

    Each trial seeds a fresh database with one overdue reminder, then forks two
    processes that wait at a barrier and run the due check at the same instant.
    A trial is healthy only if both processes return without
    ``OperationalError`` and exactly one of them fires the reminder.
    """
    ctx = multiprocessing.get_context("fork")
    raised = 0
    fired_total = 0
    problems: list[str] = []

    for trial in range(TRIALS):
        db_path = str(tmp_path / f"barrier-{trial}.db")
        # Seed the reminder from the parent, then close the connection so the
        # forked children inherit no open file descriptor for the database.
        with MemoryStore(db_path) as seeding:
            seeding.add_reminder("contended reminder", time.time() - 10)

        barrier = ctx.Barrier(2)
        result_queue = ctx.Queue()
        procs = [
            ctx.Process(
                target=_due_check_worker,
                args=(db_path, barrier, result_queue),
            )
            for _ in range(2)
        ]
        for proc in procs:
            proc.start()
        for proc in procs:
            proc.join(timeout=30)
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)
                problems.append(f"trial {trial}: a worker hung and was terminated")
            elif proc.exitcode:
                problems.append(f"trial {trial}: a worker exited with {proc.exitcode}")

        results: list[tuple[str, object]] = []
        while not result_queue.empty():
            results.append(result_queue.get_nowait())
        result_queue.close()
        if len(results) != 2:
            problems.append(
                f"trial {trial}: expected two worker results, got {len(results)}"
            )
        for kind, payload in results:
            if kind == "ok":
                fired_total += int(payload)  # type: ignore[arg-type]
            else:
                raised += 1
                problems.append(f"trial {trial}: refused with {payload!r}")

    assert not problems, (
        f"{TRIALS} barrier trials produced problems (raised={raised}): "
        f"{problems[:5]}"
    )
    # Never refused: no trial raised "database is locked".
    assert raised == 0
    # Fire exactly once across processes: one of the two checks fires each
    # trial, the other finds the reminder already delivered.
    assert fired_total == TRIALS
