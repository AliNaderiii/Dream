"""MEM Stage A — bounded stores across real OS processes.

The in-process ``RLock`` cannot prove cross-process serialization; SQLite's
file lock must. Two child processes meet at a ``Barrier`` and race an
``add`` that only one can fit: exactly one wins, the loser receives a clean
:class:`StoreCapacityError`, and the budget holds. This mirrors the
``test_concurrent_processes.py`` evidence pattern (threads hide the defect;
real processes reproduce it).
"""

from __future__ import annotations

import multiprocessing

from dream.memory_stores import (
    NOTES_CAPACITY_CHARS,
    TARGET_MEMORY,
    BoundedStore,
)


def _racing_add_worker(db_path: str, barrier, result_queue) -> None:
    """Open a fresh store, wait, then try to add an oversized-together entry."""
    store = BoundedStore(TARGET_MEMORY, NOTES_CAPACITY_CHARS, path=db_path)
    try:
        barrier.wait()
        try:
            snapshot = store.add("racer-process-entry")
            result_queue.put(("ok", snapshot.used_chars, snapshot.entries))
        except Exception as exc:
            result_queue.put(("error", type(exc).__name__, str(exc)[:80]))
    finally:
        store.close()


def test_two_processes_racing_the_capacity_budget_serialize(tmp_path):
    db_path = str(tmp_path / "race.db")
    # Seed the store so only ONE 23-char entry fits: 2,200 - 2,177 = 23.
    seeder = BoundedStore(TARGET_MEMORY, NOTES_CAPACITY_CHARS, path=db_path)
    seeder.add("s" * 2_177)
    seeder.close()

    barrier = multiprocessing.Barrier(2)
    result_queue: multiprocessing.Queue = multiprocessing.Queue()
    children = [
        multiprocessing.Process(
            target=_racing_add_worker, args=(db_path, barrier, result_queue)
        )
        for _ in range(2)
    ]
    for child in children:
        child.start()
    for child in children:
        child.join(timeout=30)
    assert all(child.exitcode == 0 for child in children), "a child crashed"

    results = [result_queue.get(timeout=5) for _ in range(2)]
    oks = [r for r in results if r[0] == "ok"]
    errors = [r for r in results if r[0] == "error"]
    # Exactly one add landed; the other was refused cleanly as capacity.
    assert len(oks) == 1, results
    assert len(errors) == 1 and errors[0][1] == "StoreCapacityError", results
    assert oks[0][1] <= NOTES_CAPACITY_CHARS

    verifier = BoundedStore(TARGET_MEMORY, NOTES_CAPACITY_CHARS, path=db_path)
    try:
        snapshot = verifier.snapshot()
        assert snapshot.entries == ("s" * 2_177, "racer-process-entry")
        assert snapshot.used_chars == 2_177 + 1 + len("racer-process-entry")
    finally:
        verifier.close()


def _add_many_worker(db_path: str, worker_id: int, barrier, result_queue) -> None:
    store = BoundedStore(TARGET_MEMORY, NOTES_CAPACITY_CHARS, path=db_path)
    try:
        barrier.wait()
        added = 0
        errors = 0
        for i in range(60):
            try:
                store.add(f"proc-{worker_id}-{i:03d}")
                added += 1
            except Exception:
                errors += 1
        result_queue.put((worker_id, added, errors))
    finally:
        store.close()


def test_four_processes_adding_concurrently_keep_the_budget(tmp_path):
    db_path = str(tmp_path / "many.db")
    barrier = multiprocessing.Barrier(4)
    result_queue: multiprocessing.Queue = multiprocessing.Queue()
    children = [
        multiprocessing.Process(
            target=_add_many_worker, args=(db_path, worker_id, barrier, result_queue)
        )
        for worker_id in range(4)
    ]
    for child in children:
        child.start()
    for child in children:
        child.join(timeout=60)
    assert all(child.exitcode == 0 for child in children), "a child crashed"

    totals = [result_queue.get(timeout=5) for _ in range(4)]
    total_added = sum(added for _, added, _ in totals)
    assert total_added > 0
    # "proc-N-iii" is 10 chars; the budget bounds the batch.
    assert total_added * (len("proc-0-000") + 1) - 1 <= NOTES_CAPACITY_CHARS

    verifier = BoundedStore(TARGET_MEMORY, NOTES_CAPACITY_CHARS, path=db_path)
    try:
        snapshot = verifier.snapshot()
        assert len(snapshot.entries) == total_added
        assert snapshot.used_chars <= NOTES_CAPACITY_CHARS
        # No duplicate rows, no lost rows.
        assert len(set(snapshot.entries)) == total_added
    finally:
        verifier.close()
