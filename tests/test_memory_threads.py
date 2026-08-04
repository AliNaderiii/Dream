"""Tests for sharing one MemoryStore across threads.

The store opens its connection with ``check_same_thread=False`` and guards
every connection access with one re-entrant lock.  These tests prove the two
halves hold together: nothing raises under contention, no write is silently
lost, nested store calls cannot deadlock, and the lock is actually acquired
rather than merely created.  Everything runs against real on-disk databases
in tmp_path, so WAL mode is genuinely active.
"""

from __future__ import annotations

import threading

import pytest

from dream.memory import MemoryStore


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "dream.db"))
    yield s
    s.close()


def _spawn(targets):
    threads = [threading.Thread(target=target) for target in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def test_eight_threads_times_fifty_writes_store_all_400_rows(store):
    errors: list[str] = []

    def writer(n: int) -> None:
        try:
            for i in range(50):
                store.remember(f"user{n} fact {i}", kind="semantic")
        except Exception as exc:
            errors.append(repr(exc))

    _spawn([lambda n=n: writer(n) for n in range(8)])

    assert errors == []
    assert len(store.all(limit=1000)) == 400


def test_concurrent_readers_and_writers_raise_nothing(store):
    for i in range(30):
        store.remember(f"seed fact {i}")
    errors: list[str] = []

    def writer(n: int) -> None:
        try:
            for i in range(25):
                store.remember(f"writer{n} fact {i}")
                store.log("user", f"journal line {n}-{i}", session_id=f"s{n}")
        except Exception as exc:
            errors.append(repr(exc))

    def reader() -> None:
        try:
            for _ in range(40):
                # recall reinforces, so readers write as well as read.
                store.recall("seed fact")
                store.all(limit=5)
                store.recent_journal(limit=5)
                store.stats()
        except Exception as exc:
            errors.append(repr(exc))

    _spawn([*(lambda n=n: writer(n) for n in range(4)), *(reader for _ in range(4))])

    assert errors == []


def test_recall_while_another_thread_writes_returns_coherent_results(store):
    for i in range(20):
        store.remember(f"coffee preference fact {i}")
    errors: list[str] = []
    stop = threading.Event()

    def writer() -> None:
        count = 0
        try:
            while not stop.is_set():
                store.remember(f"background fact {count}")
                count += 1
        except Exception as exc:
            errors.append(repr(exc))

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        for _ in range(50):
            hits = store.recall("coffee preference")
            identities = [m.id for m in hits]
            assert len(identities) == len(set(identities)), "recall returned a row twice"
            scores = [m.score for m in hits]
            assert scores == sorted(scores, reverse=True), "recall returned unsorted rows"
    finally:
        stop.set()
        thread.join()

    assert errors == []


def test_nested_store_calls_do_not_deadlock(store):
    # remember() calls get() and recall() falls back into _like_scan(); both
    # take the store lock while it is already held.  With a non-reentrant
    # lock this would wedge, so the nest runs on a daemon thread that can
    # time out instead of hanging the test run.
    done = threading.Event()

    def work() -> None:
        store.remember("nested calls must not wedge the store")
        store.recall("nothing stored matches this query")
        done.set()

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    assert done.wait(timeout=10), "nested store call deadlocked: the store lock is not re-entrant"
    worker.join(timeout=1)
    assert store.all(), "the nested remember() must have completed"


def test_the_lock_is_held_during_a_write(store):
    # Teeth for the regression where the lock existed but was never taken:
    # if remember() never acquires it, the writer finishes while the main
    # thread still holds the lock and the first assertion fails.
    store._lock.acquire()
    done = threading.Event()
    errors: list[str] = []

    def writer() -> None:
        try:
            store.remember("this write must wait for the lock")
        except Exception as exc:
            errors.append(repr(exc))
        finally:
            done.set()

    worker = threading.Thread(target=writer, daemon=True)
    worker.start()
    try:
        assert not done.wait(0.3), "remember() completed without acquiring the store lock"
    finally:
        store._lock.release()

    worker.join(timeout=10)
    assert done.is_set()
    assert errors == []
    assert [m.content for m in store.all()] == ["this write must wait for the lock"]
