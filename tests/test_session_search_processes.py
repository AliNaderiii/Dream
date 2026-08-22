"""MEM Stage B — the session index across real OS processes.

The CLI, the scheduler daemon, and the gateway are separate writers against
one index file. Two child processes meet at a ``Barrier`` and index
concurrently (overlapping the same session once); the verifier then checks
document count, uniqueness, and search integrity — the Gate A evidence
pattern: threads cannot prove cross-process serialization, processes can.
"""

from __future__ import annotations

import multiprocessing

from dream.session_search import SessionSearchIndex


def _writer_worker(db_path: str, worker_id: int, barrier, result_queue) -> None:
    index = SessionSearchIndex(db_path)
    try:
        barrier.wait(timeout=30)
        errors = 0
        for i in range(50):
            session_id = (
                f"shared-{i:02d}" if (i % 10 == 0) else f"w{worker_id}-{i:02d}"
            )
            try:
                index.index_session(
                    session_id,
                    f"title {session_id}",
                    [f"message {session_id} with the probe word"],
                )
            except Exception:
                errors += 1
        result_queue.put((worker_id, errors))
    finally:
        index.close()


def test_two_writer_processes_serialize_without_loss(tmp_path):
    db_path = str(tmp_path / "sessions.db")
    barrier = multiprocessing.Barrier(2)
    result_queue: multiprocessing.Queue = multiprocessing.Queue()
    children = [
        multiprocessing.Process(
            target=_writer_worker, args=(db_path, worker_id, barrier, result_queue)
        )
        for worker_id in range(2)
    ]
    for child in children:
        child.start()
    for child in children:
        child.join(timeout=120)
    assert all(child.exitcode == 0 for child in children), "a writer crashed"

    results = [result_queue.get(timeout=5) for _ in range(2)]
    assert [errors for _, errors in results] == [0, 0], results

    with SessionSearchIndex(db_path) as verifier:
        # 2×50 writes; both workers hit the same 5 shared ids (i % 10 == 0),
        # so 100 writes land on 95 unique documents.
        assert verifier.doc_count() == 95
        hits = verifier.search("probe", limit=200)
        assert len(hits) == 95
        session_ids = [hit.session_id for hit in hits]
        assert len(set(session_ids)) == 95  # no duplicated documents
        # A shared session's surviving document is internally consistent:
        # its title and body name the same session.
        row = verifier.conn.execute(
            "SELECT title_orig, body_orig FROM session_docs"
            " WHERE session_id = 'shared-00'"
        ).fetchone()
        assert row is not None
        assert "shared-00" in str(row["title_orig"])
        assert "shared-00" in str(row["body_orig"])
