"""MEM Stage B — the session index under contention.

The index is written from the CLI, the scheduler daemon, and the gateway, so
writers and searchers coexist in one process (thread lock) and writers
coexist across processes (SQLite write lock).  Searchers must only ever see
complete documents: an upsert is one transaction, so a hit's body is either
the old or the new full text, never a half-written blend.
"""

from __future__ import annotations

import threading

import pytest

from dream.session_search import SessionSearchIndex


@pytest.fixture()
def index(tmp_path):
    idx = SessionSearchIndex(str(tmp_path / "sessions.db"))
    yield idx
    idx.close()


def _spawn(targets):
    threads = [threading.Thread(target=target) for target in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def test_searchers_see_only_complete_documents_while_a_writer_indexes(index):
    errors: list[str] = []
    anomalies: list[str] = []
    stop = threading.Event()

    def writer() -> None:
        try:
            for i in range(150):
                index.index_session(
                    f"sess-{i}",
                    f"session {i} title",
                    [f"writer-{i}: message body with the needle word and context {i}"],
                )
        except Exception as exc:  # pragma: no cover - failure evidence
            errors.append(repr(exc))

    def searcher() -> None:
        while not stop.is_set():
            hits = index.search("needle", limit=200)
            for hit in hits:
                if not hit.session_id.startswith("sess-"):
                    anomalies.append(f"foreign session: {hit.session_id}")
                if "[" not in hit.snippet and "needle" not in hit.snippet:
                    anomalies.append(f"snippet without match: {hit.snippet!r}")

    writer_thread = threading.Thread(target=writer)
    searchers = [threading.Thread(target=searcher) for _ in range(3)]
    writer_thread.start()
    for s in searchers:
        s.start()
    writer_thread.join(timeout=60)
    stop.set()
    for s in searchers:
        s.join(timeout=10)

    assert errors == []
    assert anomalies == []
    final = index.search("needle", limit=200)
    assert len(final) == 150
    # Every final document carries exactly its own message.
    for hit in final:
        sid = int(hit.session_id.split("-")[1])
        assert f"writer-{sid}:" in hit.snippet


def test_concurrent_appends_to_one_session_keep_every_message_in_order(index):
    appended = [f"message number {i:03d} about topic" for i in range(60)]

    def appender(chunk) -> None:
        for i in chunk:
            index.append_message("chat", f"message number {i:03d} about topic")

    chunks = [range(0, 20), range(20, 40), range(40, 60)]
    _spawn([lambda chunk=chunk: appender(chunk) for chunk in chunks])

    row = index.conn.execute(
        "SELECT body_orig FROM session_docs WHERE session_id = 'chat'"
    ).fetchone()
    lines = str(row["body_orig"]).splitlines()
    assert sorted(lines) == sorted(appended)
    assert index.doc_count() == 1
    hits = index.search("topic")
    assert len(hits) == 1 and hits[0].session_id == "chat"


def test_concurrent_same_session_upserts_serialize_last_write_wins(index):
    def upserter(n: int) -> None:
        for i in range(20):
            index.index_session(
                "shared", f"title {n}-{i}", [f"body {n}-{i} with the probe word"]
            )

    _spawn([lambda n=n: upserter(n) for n in range(4)])
    assert index.doc_count() == 1
    hits = index.search("probe")
    assert len(hits) == 1
    # The winning title/body pair is internally consistent.
    assert hits[0].title.startswith("title ")
    assert "body " in hits[0].snippet
    row = index.conn.execute(
        "SELECT title_orig, body_orig FROM session_docs WHERE session_id = 'shared'"
    ).fetchone()
    assert str(row["title_orig"]).startswith("title ")
    assert str(row["body_orig"]).startswith("body ")


def test_rebuild_while_searching_never_yields_a_broken_result(index):
    for i in range(40):
        index.index_session(f"s{i}", f"log {i}", [f"entry {i} with the marker word"])
    anomalies: list[str] = []

    def rebuilder() -> None:
        for _ in range(10):
            index.rebuild()

    def searcher() -> None:
        for _ in range(100):
            hits = index.search("marker", limit=200)
            if len(hits) != 40:
                anomalies.append(f"expected 40 hits during rebuild, saw {len(hits)}")

    _spawn([rebuilder, searcher])
    assert anomalies == []
