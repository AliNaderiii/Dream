"""MEM Stage A — bounded stores under thread contention.

Gate A requires a concurrency test for the one-writer-per-store contract:
concurrent ``add``/``replace``/``remove``/``snapshot`` calls must serialize
safely — every accepted write is present, every rejected write carries a
clean domain error, the capacity budget is never exceeded, and the entry
order is exactly the order the accepted writes landed in.
"""

from __future__ import annotations

import threading

import pytest

from dream.memory_stores import (
    TARGET_MEMORY,
    TARGET_USER,
    AmbiguousEntryError,
    BoundedMemory,
    BoundedStore,
    EntryNotFoundError,
    StoreCapacityError,
)

CAPACITY = 600


@pytest.fixture()
def store(tmp_path):
    s = BoundedStore(TARGET_MEMORY, CAPACITY, path=str(tmp_path / "b.db"))
    yield s
    s.close()


def _spawn(targets):
    threads = [threading.Thread(target=target) for target in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def test_eight_writer_threads_never_lose_an_accepted_add(store):
    accepted: list[str] = []
    accepted_lock = threading.Lock()
    errors: list[str] = []
    per_thread_accepted_counts: list[int] = [0] * 8

    def writer(n: int) -> None:
        for i in range(25):
            text = f"writer-{n:02d}-entry-{i:02d}"
            try:
                snapshot = store.add(text)
            except StoreCapacityError:
                continue
            except Exception as exc:  # unexpected failure under contention
                errors.append(repr(exc))
                continue
            with accepted_lock:
                accepted.append(text)
                per_thread_accepted_counts[n] += 1
            assert snapshot.used_chars <= CAPACITY

    _spawn([lambda n=n: writer(n) for n in range(8)])
    assert errors == []
    snapshot = store.snapshot()
    assert snapshot.used_chars <= CAPACITY
    # Every thread's accepted entries survive, in that thread's order.
    for n in range(8):
        expected = [
            f"writer-{n:02d}-entry-{i:02d}"
            for i in range(per_thread_accepted_counts[n])
        ]
        got = [e for e in snapshot.entries if e.startswith(f"writer-{n:02d}-")]
        assert got == expected
    expected_used = sum(len(e) for e in snapshot.entries) + len(snapshot.entries) - 1
    assert snapshot.used_chars == expected_used
    assert set(snapshot.entries) == set(accepted)


def test_capacity_is_never_breached_when_two_threads_race_the_last_slot(store):
    """Two 590-char entries race for a 600-char store: at most one fits."""
    store.add("seed-xxxx")  # 8 chars used
    outcomes: list[bool] = []
    outcomes_lock = threading.Lock()
    barrier = threading.Barrier(2)

    def racer() -> None:
        barrier.wait()
        try:
            store.add("r" * 590)
            ok = True
        except StoreCapacityError:
            ok = False
        with outcomes_lock:
            outcomes.append(ok)

    _spawn([racer, racer])
    assert outcomes.count(True) == 1, "both racers' writes must not both land"
    snapshot = store.snapshot()
    assert snapshot.used_chars <= CAPACITY
    assert len(snapshot.entries) == 2  # seed + exactly one racer


def test_readers_see_a_consistent_snapshot_while_writers_write(store):
    for i in range(10):
        store.add(f"seed-entry-{i:02d}")
    anomalies: list[str] = []

    def reader() -> None:
        for _ in range(200):
            snapshot = store.snapshot()
            if snapshot.used_chars > CAPACITY:
                anomalies.append(f"over capacity: {snapshot.used_chars}")
            if len(snapshot.entries) > 210:
                anomalies.append(f"too many entries: {len(snapshot.entries)}")

    def writer(n: int) -> None:
        for i in range(100):
            try:
                store.add(f"w{n}-{i:03d}")
            except StoreCapacityError:
                continue

    _spawn(
        [reader, reader]
        + [lambda n=n: writer(n) for n in range(4)]
    )
    assert anomalies == []


def test_mixed_mutations_and_both_stores_serialize(tmp_path):
    """Concurrent tool-shaped traffic across both targets of one file."""
    with BoundedMemory(path=str(tmp_path / "b.db")) as memory:
        errors: list[str] = []

        def notes_worker() -> None:
            for i in range(40):
                try:
                    if i % 4 == 3:
                        memory.notes.remove(f"note-{i - 1:02d}")
                    else:
                        memory.notes.add(f"note-{i:02d}")
                except (StoreCapacityError, EntryNotFoundError, AmbiguousEntryError):
                    continue
                except Exception as exc:
                    errors.append(repr(exc))

        def profile_worker() -> None:
            for i in range(40):
                try:
                    if i % 4 == 3:
                        memory.profile.replace(
                            f"fact-{i - 1:02d}", f"fact-{i - 1:02d}-v2"
                        )
                    else:
                        memory.profile.add(f"fact-{i:02d}")
                except (StoreCapacityError, EntryNotFoundError, AmbiguousEntryError):
                    continue
                except Exception as exc:
                    errors.append(repr(exc))

        _spawn([notes_worker, profile_worker])
        assert errors == []
        notes_snapshot = memory.notes.snapshot()
        profile_snapshot = memory.profile.snapshot()
        assert notes_snapshot.target == TARGET_MEMORY
        assert profile_snapshot.target == TARGET_USER
        assert notes_snapshot.used_chars <= notes_snapshot.capacity
        assert profile_snapshot.used_chars <= profile_snapshot.capacity
        # Every surviving notes entry is a well-formed note token.
        for entry in notes_snapshot.entries:
            assert entry.startswith("note-")


def test_nested_lock_use_does_not_deadlock(store):
    """add() builds its return snapshot while holding the write lock."""
    store.add("outer")
    done = threading.Event()

    def worker() -> None:
        for i in range(20):
            try:
                store.add(f"nested-{i}")
            except StoreCapacityError:
                continue
        done.set()

    thread = threading.Thread(target=worker)
    thread.start()
    assert done.wait(timeout=10), "nested store calls deadlocked"
    thread.join()
