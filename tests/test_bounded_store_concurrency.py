"""SEC-08 — BoundedStore concurrency stress tests (100 threads, repeated).

Design:

* Every race starts on a ``threading.Barrier`` (no sleeps) and every worker
  is reaped through ``concurrent.futures.wait`` with one hard deadline, so a
  deadlock fails the test in bounded time instead of hanging the suite.
* Each stress test repeats its whole race ``REPEATS`` times on fresh
  stores, so a scheduling-dependent slip is hit many times per pytest
  invocation — no external repeat plugin.
* Invariants checked on the final store state — and, where noted, on every
  in-flight snapshot: ``used_chars <= capacity``, no lost write, no
  duplicated row, per-writer ordering, snapshot detachment.
* Each race body lives in a ``_race_*`` helper so the worker closures bind
  plain function locals (ruff B023), and the test functions stay readable
  loops over ``REPEATS``.
"""

from __future__ import annotations

import dataclasses
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path

import pytest

from dream.memory_stores import (
    TARGET_MEMORY,
    BoundedMemory,
    BoundedStore,
    StoreCapacityError,
)

#: Whole races repeated per stress test (the brief's "10 iterations").
REPEATS = 10
#: Hard per-race deadline; a worker still running after this is a deadlock.
DEADLINE_SECONDS = 120.0


def _drain(futures: Sequence[Future[None]], deadline: float) -> None:
    """Join futures under one hard deadline; fail the test on timeout.

    ``wait`` gives a single global deadline for the whole race, so one stuck
    worker fails the test in bounded time instead of hanging the suite.
    Worker exceptions (bugs in the test itself) are re-raised here.
    """
    done, not_done = wait(list(futures), timeout=deadline)
    if not_done:
        for future in not_done:
            future.cancel()
        pytest.fail(
            f"{len(not_done)} workers still running after {deadline:.0f}s — possible deadlock"
        )
    for future in done:
        future.result()


def _run_race(workers: list[Callable[[], None]], deadline: float) -> None:
    """Run *workers* concurrently, join under a hard deadline, and clean up.

    ``shutdown(wait=False, cancel_futures=True)`` guarantees the test never
    blocks on a stuck worker: the deadline already failed it above, and
    every worker self-terminates within its own barrier-wait timeout.
    """
    pool = ThreadPoolExecutor(max_workers=len(workers))
    futures = [pool.submit(worker) for worker in workers]
    try:
        _drain(futures, deadline)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


# ---------------------------------------------------------------------------
# 100 threads adding unique values
# ---------------------------------------------------------------------------


def _race_hundred_unique_adds() -> None:
    """100 threads × 10 unique adds: every write lands exactly once, in order."""
    per_thread = 10
    total = 100 * per_thread
    # "t99-009" is 8 chars → 1,000 entries + 999 separators = 8,999 ≤ capacity.
    capacity = 10_000
    store = BoundedStore(TARGET_MEMORY, capacity, path=":memory:")
    barrier = threading.Barrier(100)
    errors: list[str] = []
    errors_lock = threading.Lock()

    def worker(writer: int) -> None:
        try:
            barrier.wait(timeout=DEADLINE_SECONDS)
            for i in range(per_thread):
                store.add(f"t{writer:02d}-{i:03d}")
        except Exception as exc:
            with errors_lock:
                errors.append(f"writer {writer}: {exc!r}")

    _run_race([lambda w=w: worker(w) for w in range(100)], DEADLINE_SECONDS)
    snapshot = store.snapshot()
    store.close()
    assert errors == []
    entries = list(snapshot.entries)
    assert len(entries) == total, "lost adds under contention"
    assert len(set(entries)) == total, "duplicated rows under contention"
    expected = {f"t{w:02d}-{i:03d}" for w in range(100) for i in range(per_thread)}
    assert set(entries) == expected
    # Per-writer subsequence order is that writer's own order.
    for w in range(100):
        mine = [e for e in entries if e.startswith(f"t{w:02d}-")]
        assert mine == [f"t{w:02d}-{i:03d}" for i in range(per_thread)]
    assert snapshot.used_chars <= capacity


def test_hundred_threads_add_unique_values_exactly_once() -> None:
    for _iteration in range(REPEATS):
        _race_hundred_unique_adds()


# ---------------------------------------------------------------------------
# 100 concurrent snapshot readers
# ---------------------------------------------------------------------------


def _race_readers_against_writers() -> None:
    """100 readers × 150 snapshots race 10 writers; every snapshot is consistent."""
    writers = 10
    per_writer = 20
    total_writes = writers * per_writer
    # "w09-019" is 8 chars → all 200 adds fit: 8*200 + 199 = 1,799.
    capacity = 10_000
    store = BoundedStore(TARGET_MEMORY, capacity, path=":memory:")
    barrier = threading.Barrier(100 + writers)
    violations: list[str] = []
    violations_lock = threading.Lock()

    def _record(message: str) -> None:
        with violations_lock:
            violations.append(message)

    def reader(reader_id: int) -> None:
        try:
            barrier.wait(timeout=DEADLINE_SECONDS)
        except Exception as exc:
            _record(f"reader {reader_id} barrier failed: {exc!r}")
            return
        for step in range(150):
            try:
                snapshot = store.snapshot()
            except Exception as exc:
                _record(f"reader {reader_id} snapshot raised: {exc!r}")
                continue
            # Cheap invariants on every snapshot…
            if snapshot.used_chars > snapshot.capacity:
                _record(f"reader {reader_id} over capacity: {snapshot.used_chars}")
                continue
            if len(set(snapshot.entries)) != len(snapshot.entries):
                _record(f"reader {reader_id} duplicated entries in one snapshot")
                continue
            if len(snapshot.entries) > total_writes:
                _record(f"reader {reader_id} phantom entries: {len(snapshot.entries)}")
                continue
            # …and the full ordering law on a sampled cadence (the heavy
            # per-entry walk is what keeps 100 readers cheap to sustain).
            if step % 20 != 0:
                continue
            # Per-writer prefix law: an add is atomic and appends at the
            # tail, so in one snapshot each writer's visible indices must
            # be exactly {0..k-1} — a torn or out-of-order write breaks it.
            last_index: dict[int, int] = {}
            counts: dict[int, int] = {}
            for entry in snapshot.entries:
                writer_part, _, index_part = entry.rpartition("-")
                writer_num = int(writer_part[1:])
                counts[writer_num] = counts.get(writer_num, 0) + 1
                last_index[writer_num] = max(last_index.get(writer_num, -1), int(index_part))
            for writer_num, highest in last_index.items():
                if highest + 1 != counts[writer_num]:
                    _record(
                        f"reader {reader_id} torn writer {writer_num}: "
                        f"highest {highest} vs {counts[writer_num]} entries"
                    )
                    break

    def writer(writer_id: int) -> None:
        try:
            barrier.wait(timeout=DEADLINE_SECONDS)
            for i in range(per_writer):
                store.add(f"w{writer_id:02d}-{i:03d}")
        except Exception as exc:
            _record(f"writer {writer_id} failed: {exc!r}")

    _run_race(
        [lambda r=r: reader(r) for r in range(100)]
        + [lambda w=w: writer(w) for w in range(writers)],
        DEADLINE_SECONDS,
    )
    snapshot = store.snapshot()
    store.close()
    assert violations == []
    assert len(snapshot.entries) == total_writes
    assert snapshot.used_chars <= capacity


def test_hundred_readers_see_only_consistent_snapshots_while_writers_add() -> None:
    for _iteration in range(REPEATS):
        _race_readers_against_writers()


# ---------------------------------------------------------------------------
# Concurrent add and replace
# ---------------------------------------------------------------------------


def _race_add_and_replace() -> None:
    """25 replacers swap their own items while 10 adders append, at the barrier."""
    items = 100
    replacers = 25
    adders = 10
    per_adder = 20
    capacity = 20_000
    store = BoundedStore(TARGET_MEMORY, capacity, path=":memory:")
    for i in range(items):
        store.add(f"item-{i:03d}")
    barrier = threading.Barrier(replacers + adders)
    errors: list[str] = []
    errors_lock = threading.Lock()

    def _record(message: str) -> None:
        with errors_lock:
            errors.append(message)

    def replacer(replacer_id: int) -> None:
        try:
            barrier.wait(timeout=DEADLINE_SECONDS)
            # Each replacer owns a disjoint, unique item fragment.
            for i in range(replacer_id, items, replacers):
                store.replace(f"item-{i:03d}", f"done-{i:03d}")
        except Exception as exc:
            _record(f"replacer {replacer_id} failed: {exc!r}")

    def adder(adder_id: int) -> None:
        try:
            barrier.wait(timeout=DEADLINE_SECONDS)
            for i in range(per_adder):
                store.add(f"add-{adder_id:02d}-{i:03d}")
        except Exception as exc:
            _record(f"adder {adder_id} failed: {exc!r}")

    _run_race(
        [lambda r=r: replacer(r) for r in range(replacers)]
        + [lambda a=a: adder(a) for a in range(adders)],
        DEADLINE_SECONDS,
    )
    snapshot = store.snapshot()
    store.close()
    assert errors == []
    expected = {f"done-{i:03d}" for i in range(items)} | {
        f"add-{a:02d}-{i:03d}" for a in range(adders) for i in range(per_adder)
    }
    assert set(snapshot.entries) == expected
    assert len(snapshot.entries) == len(expected), "duplicated rows under contention"
    assert not any(e.startswith("item-") for e in snapshot.entries)
    assert snapshot.used_chars <= capacity


def test_concurrent_add_and_replace_never_lose_or_duplicate() -> None:
    for _iteration in range(REPEATS):
        _race_add_and_replace()


# ---------------------------------------------------------------------------
# Duplicate adds from many threads
# ---------------------------------------------------------------------------


def _race_duplicate_adds() -> None:
    """Same value from 100 threads × 3: no dedup, no loss, no duplicated rows.

    The contract has no value-level deduplication — every accepted ``add``
    appends a row, so 300 identical values are 300 entries, all present.
    """
    per_thread = 3
    total = 100 * per_thread
    capacity = 10_000
    store = BoundedStore(TARGET_MEMORY, capacity, path=":memory:")
    barrier = threading.Barrier(100)
    errors: list[str] = []
    errors_lock = threading.Lock()

    def worker(writer: int) -> None:
        try:
            barrier.wait(timeout=DEADLINE_SECONDS)
            for _ in range(per_thread):
                store.add("dup")
        except Exception as exc:
            with errors_lock:
                errors.append(f"writer {writer}: {exc!r}")

    _run_race([lambda w=w: worker(w) for w in range(100)], DEADLINE_SECONDS)
    snapshot = store.snapshot()
    store.close()
    assert errors == []
    assert list(snapshot.entries) == ["dup"] * total
    assert snapshot.used_chars == len("dup") * total + (total - 1)
    assert snapshot.used_chars <= capacity


def test_duplicate_adds_from_hundred_threads_all_land() -> None:
    for _iteration in range(REPEATS):
        _race_duplicate_adds()


# ---------------------------------------------------------------------------
# Capacity race: 100 threads for exactly one last slot
# ---------------------------------------------------------------------------


def _race_last_slot() -> None:
    """Seed to leave room for exactly one 399-char entry; 100 threads race it."""
    capacity = 600
    store = BoundedStore(TARGET_MEMORY, capacity, path=":memory:")
    store.add("s" * 200)  # 200 used; 200 + 1 + 399 == 600 → exactly one fits
    barrier = threading.Barrier(100)
    wins: list[int] = []
    wins_lock = threading.Lock()
    errors: list[str] = []
    errors_lock = threading.Lock()

    def racer(racer_id: int) -> None:
        try:
            barrier.wait(timeout=DEADLINE_SECONDS)
            try:
                store.add("r" * 399)
                with wins_lock:
                    wins.append(racer_id)
            except StoreCapacityError:
                pass  # the designed overflow policy: clean error, no write
        except Exception as exc:
            with errors_lock:
                errors.append(f"racer {racer_id}: {exc!r}")

    _run_race([lambda r=r: racer(r) for r in range(100)], DEADLINE_SECONDS)
    snapshot = store.snapshot()
    store.close()
    assert errors == []
    assert len(wins) == 1, f"capacity breached or write lost: {len(wins)} winners"
    assert snapshot.entries == ("s" * 200, "r" * 399)
    assert snapshot.used_chars == capacity


def test_hundred_racers_for_one_last_slot_fit_exactly_one() -> None:
    for _iteration in range(REPEATS):
        _race_last_slot()


# ---------------------------------------------------------------------------
# Snapshot detachment
# ---------------------------------------------------------------------------


def _race_detached_snapshots() -> None:
    """A snapshot is a fresh immutable copy; later writes (or callers) cannot touch it."""
    store = BoundedStore(TARGET_MEMORY, 10_000, path=":memory:")
    try:
        frozen_empty = store.snapshot()
        assert frozen_empty.entries == ()
        store.add("first")
        first_a = store.snapshot()
        first_b = store.snapshot()
        assert first_a.entries == first_b.entries == ("first",)
        # Fresh copies: the live tuple is never shared between snapshots.
        assert first_a.entries is not first_b.entries
        store.replace("first", "second")
        store.add("third")
        assert frozen_empty.entries == ()
        assert first_a.entries == ("first",)
        assert first_a.text == "first"
        assert first_a.used_chars == len("first")
        # Frozen dataclass: a caller cannot write back through the snapshot.
        with pytest.raises((dataclasses.FrozenInstanceError, TypeError)):
            first_a.entries = ("hax",)  # type: ignore[misc]
        # Growth under contention never reaches back into earlier snapshots.
        barrier = threading.Barrier(50)
        errors: list[str] = []

        def grower(grower_id: int) -> None:
            try:
                barrier.wait(timeout=DEADLINE_SECONDS)
                for i in range(10):
                    store.add(f"g{grower_id:02d}-{i:02d}")
            except Exception as exc:
                errors.append(f"grower {grower_id}: {exc!r}")

        _run_race([lambda g=g: grower(g) for g in range(50)], DEADLINE_SECONDS)
        assert errors == []
        assert frozen_empty.entries == ()
        assert first_a.entries == ("first",)
        final = store.snapshot()
        assert final.used_chars <= 10_000
    finally:
        store.close()


def test_snapshots_are_detached_copies_not_live_views() -> None:
    for _iteration in range(REPEATS):
        _race_detached_snapshots()


# ---------------------------------------------------------------------------
# Cross-store traffic on one real file (two connections, one SQLite file)
# ---------------------------------------------------------------------------


def _race_cross_store(db_path: str) -> None:
    """Notes and profile race each other (and 50 readers) through one file.

    Each store has its own connection and its own lock, so cross-store
    writers serialize on SQLite's file lock (``BEGIN IMMEDIATE`` +
    ``busy_timeout``), not on an in-process lock.
    """
    notes_writers = 25
    profile_writers = 25
    readers = 50
    per_writer = 8
    # "n24-07" is 8 chars → 200 notes entries: 8*200 + 199 = 1,799 ≤ 2,200.
    # "p247" is 4 chars → 200 profile entries: 4*200 + 199 = 999 ≤ 1,375.
    memory = BoundedMemory(path=db_path)
    barrier = threading.Barrier(notes_writers + profile_writers + readers)
    errors: list[str] = []
    errors_lock = threading.Lock()
    accepted_notes: list[str] = []
    accepted_notes_lock = threading.Lock()
    accepted_profile: list[str] = []
    accepted_profile_lock = threading.Lock()

    def _record(message: str) -> None:
        with errors_lock:
            errors.append(message)

    def notes_writer(writer_id: int) -> None:
        try:
            barrier.wait(timeout=DEADLINE_SECONDS)
            for i in range(per_writer):
                text = f"n{writer_id:02d}-{i:02d}"
                memory.notes.add(text)
                with accepted_notes_lock:
                    accepted_notes.append(text)
        except StoreCapacityError:
            _record(f"notes writer {writer_id} hit capacity (should not fit)")
        except Exception as exc:
            _record(f"notes writer {writer_id} failed: {exc!r}")

    def profile_writer(writer_id: int) -> None:
        try:
            barrier.wait(timeout=DEADLINE_SECONDS)
            for i in range(per_writer):
                text = f"p{writer_id:02d}{i}"
                memory.profile.add(text)
                with accepted_profile_lock:
                    accepted_profile.append(text)
        except StoreCapacityError:
            _record(f"profile writer {writer_id} hit capacity (should not fit)")
        except Exception as exc:
            _record(f"profile writer {writer_id} failed: {exc!r}")

    def reader(reader_id: int) -> None:
        try:
            barrier.wait(timeout=DEADLINE_SECONDS)
            for _ in range(50):
                notes_snapshot = memory.notes.snapshot()
                profile_snapshot = memory.profile.snapshot()
                if notes_snapshot.used_chars > notes_snapshot.capacity:
                    _record(f"reader {reader_id} notes over capacity")
                if profile_snapshot.used_chars > profile_snapshot.capacity:
                    _record(f"reader {reader_id} profile over capacity")
        except Exception as exc:
            _record(f"reader {reader_id} failed: {exc!r}")

    _run_race(
        [lambda w=w: notes_writer(w) for w in range(notes_writers)]
        + [lambda w=w: profile_writer(w) for w in range(profile_writers)]
        + [lambda r=r: reader(r) for r in range(readers)],
        DEADLINE_SECONDS,
    )
    notes_snapshot = memory.notes.snapshot()
    profile_snapshot = memory.profile.snapshot()
    memory.close()
    assert errors == []
    assert set(notes_snapshot.entries) == set(accepted_notes)
    assert len(notes_snapshot.entries) == len(accepted_notes)
    assert notes_snapshot.used_chars <= notes_snapshot.capacity
    assert set(profile_snapshot.entries) == set(accepted_profile)
    assert len(profile_snapshot.entries) == len(accepted_profile)
    assert profile_snapshot.used_chars <= profile_snapshot.capacity


def test_both_stores_hold_their_budgets_under_cross_store_traffic(tmp_path: Path) -> None:
    for iteration in range(REPEATS):
        _race_cross_store(str(tmp_path / f"race-{iteration}.db"))


# ---------------------------------------------------------------------------
# Interrupt discipline: no leaked transaction after a Ctrl-C inside a write
# ---------------------------------------------------------------------------


def test_interrupt_inside_the_write_unit_leaves_no_open_transaction() -> None:
    """A keyboard interrupt inside the write unit must roll the transaction back.

    A real SIGINT raises ``KeyboardInterrupt`` from whatever bytecode the
    main thread is executing; this simulation raises it from inside the
    write unit, which is exactly that path. The baseline code caught only
    ``Exception`` here, leaked the ``BEGIN IMMEDIATE`` transaction, and
    bricked every later write with ``OperationalError: cannot start a
    transaction within a transaction`` (reproduced at the base commit; see
    SEC-08-AUDIT.md).
    """
    store = BoundedStore(TARGET_MEMORY, 10_000, path=":memory:")
    try:
        with pytest.raises(KeyboardInterrupt):
            with store._locked_write():
                raise KeyboardInterrupt
        assert store._conn.in_transaction is False
        snapshot = store.add("after")
        assert snapshot.entries == ("after",)
        # Same discipline through the public entry points: a domain error
        # mid-unit leaves no transaction behind either.
        small = BoundedStore(TARGET_MEMORY, 100, path=":memory:")
        try:
            with pytest.raises(StoreCapacityError):
                small.add("x" * 200)
            assert small._conn.in_transaction is False
            assert small.snapshot().entries == ()
        finally:
            small.close()
    finally:
        store.close()
