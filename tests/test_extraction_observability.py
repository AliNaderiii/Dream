"""SEC-04 observability tests for the extraction pass.

Covers the thread-safe metrics registry and the typed status/log/metric hooks
Dream's agent adds around extraction: every pass records a status, every
failure path increments the matching metric, storage failures surface on the
turn, and log records never carry user content or secrets.
"""

from __future__ import annotations

import logging
import sqlite3
import threading

import pytest

from dream.agent import Dream
from dream.extraction import (
    STATUS_ABANDONED,
    STATUS_DISABLED,
    STATUS_ERROR,
    STATUS_FACTS_FOUND,
    STATUS_UNPARSEABLE,
)
from dream.memory import MemoryStore
from dream.metrics import (
    METRIC_EXTRACTION_ABANDONED,
    METRIC_EXTRACTION_ERROR,
    METRIC_EXTRACTION_PARSE_ERROR,
    METRIC_EXTRACTION_SKIPPED,
    METRIC_EXTRACTION_STORE_ERROR,
    METRIC_EXTRACTION_SUCCESS,
    Metrics,
    metrics,
)

_SECRET = "super-secret-token-9f3a"

_STORE_MSG = "من علی هستم و روی استارتاپ کار می‌کنم"
_FACT = '[{"content": "کاربر علی نام دارد", "kind": "semantic", "importance": 0.9}]'


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "dream.db"))
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _isolate_metrics():
    """Reset the process-wide registry around each test so test order never
    leaks counts between assertions."""
    metrics.clear()
    yield
    metrics.clear()


class _TurnBackend:
    """Mock backend: an instant conversation reply plus a scripted extraction
    response (text, dict, or a raised exception)."""

    def __init__(self, conv_reply: str, ext_response: str | dict | Exception) -> None:
        self.conv_reply = conv_reply
        self.ext_response = ext_response
        self.ext_calls = 0

    def chat(self, messages, tools=None):
        if tools is not None:
            return {"content": self.conv_reply, "tool_calls": []}
        self.ext_calls += 1
        if isinstance(self.ext_response, Exception):
            raise self.ext_response
        if isinstance(self.ext_response, dict):
            return self.ext_response
        return {"content": str(self.ext_response), "tool_calls": []}


class _BlockingExtractionBackend:
    """Conversation replies instantly; extraction blocks until released."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.started = threading.Event()

    def chat(self, messages, tools=None):
        if tools is not None:
            return {"content": "سلام", "tool_calls": []}
        self.started.set()
        self.release.wait(timeout=30)
        return {"content": "[]", "tool_calls": []}


# ---------------------------------------------------------------------------
# Metrics registry unit tests
# ---------------------------------------------------------------------------


def test_metrics_increments_and_get():
    m = Metrics()
    assert m.get("nope") == 0
    m.incr("a")
    m.incr("a", 3)
    assert m.get("a") == 4


def test_metrics_snapshot_is_a_defensive_copy():
    m = Metrics()
    m.incr("a", 2)
    snap = m.snapshot()
    snap["a"] = 99
    snap["b"] = 1
    assert m.snapshot() == {"a": 2}
    # Mutating the returned dict must not change the registry.
    assert m.get("a") == 2
    assert m.get("b") == 0


def test_metrics_are_thread_safe_under_concurrent_increments():
    m = Metrics()
    threads = 8
    per_thread = 2000
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(per_thread):
                m.incr("count")
                m.incr("other", 2)
        except BaseException as exc:  # pragma: no cover - failure capture
            errors.append(exc)

    pool = [threading.Thread(target=worker) for _ in range(threads)]
    for t in pool:
        t.start()
    for t in pool:
        t.join()
    assert errors == []
    assert m.get("count") == threads * per_thread
    assert m.get("other") == threads * per_thread * 2


# ---------------------------------------------------------------------------
# Extraction status -> metric mapping on full turns
# ---------------------------------------------------------------------------


def test_successful_extraction_sets_ok_and_counts_success(store):
    backend = _TurnBackend("سلام", _FACT)
    turn = Dream(store, backend).run(_STORE_MSG)
    assert turn.extraction.status == STATUS_FACTS_FOUND
    assert metrics.get(METRIC_EXTRACTION_SUCCESS) == 1
    assert metrics.get(METRIC_EXTRACTION_ERROR) == 0


def test_parse_failure_sets_unparseable_and_counts_parse_error(store):
    backend = _TurnBackend("سلام", "This is not JSON at all.")
    turn = Dream(store, backend).run(_STORE_MSG)
    assert turn.extraction.status == STATUS_UNPARSEABLE
    assert metrics.get(METRIC_EXTRACTION_PARSE_ERROR) == 1
    assert metrics.get(METRIC_EXTRACTION_SUCCESS) == 0


def test_backend_exception_sets_error_and_counts_error(store):
    backend = _TurnBackend("سلام", RuntimeError("extraction down"))
    turn = Dream(store, backend).run(_STORE_MSG)
    assert turn.extraction.status == STATUS_ERROR
    assert metrics.get(METRIC_EXTRACTION_ERROR) == 1


def test_disabled_extraction_sets_skipped(store, monkeypatch):
    monkeypatch.setenv("DREAM_EXTRACTION", "off")
    backend = _TurnBackend("سلام", "[]")
    turn = Dream(store, backend).run(_STORE_MSG)
    assert turn.extraction.status == STATUS_DISABLED
    assert metrics.get(METRIC_EXTRACTION_SKIPPED) == 1


def test_store_failure_sets_store_error_metric_not_silent(store, monkeypatch):
    backend = _TurnBackend("سلام", _FACT)

    def _locked_remember(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(MemoryStore, "remember", _locked_remember)
    turn = Dream(store, backend).run(_STORE_MSG)

    # Extraction itself succeeded; only the durable write failed.
    assert turn.extraction.status == STATUS_FACTS_FOUND
    assert turn.memory_errors == ["OperationalError: database is locked"]
    assert metrics.get(METRIC_EXTRACTION_STORE_ERROR) == 1
    assert metrics.get(METRIC_EXTRACTION_SUCCESS) == 1


def test_abandoned_extraction_sets_abandoned(store, monkeypatch):
    monkeypatch.setenv("DREAM_EXTRACTION_TIMEOUT_SECONDS", "0.1")
    backend = _BlockingExtractionBackend()
    try:
        turn = Dream(store, backend).run(_STORE_MSG)
        assert turn.extraction.status == STATUS_ABANDONED
        assert metrics.get(METRIC_EXTRACTION_ABANDONED) == 1
        assert metrics.get(METRIC_EXTRACTION_SUCCESS) == 0
    finally:
        backend.release.set()


# ---------------------------------------------------------------------------
# Logging: safe metadata only, no user content or secrets
# ---------------------------------------------------------------------------


def _log_records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "dream.agent"]


def test_store_failure_logs_redacted_warning(store, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="dream.agent")
    backend = _TurnBackend("سلام", _FACT)

    def _locked_remember(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(MemoryStore, "remember", _locked_remember)
    Dream(store, backend).run(_STORE_MSG)

    records = _log_records(caplog)
    assert any(r.getMessage().startswith("extraction store failure") for r in records)
    store_warns = [r for r in records if r.getMessage().startswith("extraction store failure")]
    assert store_warns
    # Safe metadata present.
    assert store_warns[0].__dict__["extraction_status"] == "store_error"
    assert store_warns[0].__dict__["exception_type"] == "OperationalError"
    # No user content, secrets, or database paths leak into any record.
    assert not any(_SECRET in (r.getMessage() or "") for r in records)
    assert not any("Ali" in (r.getMessage() or "") for r in records)
    assert not any(".db" in (r.getMessage() or "") for r in records)


def test_failure_logs_never_contain_user_content(store, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="dream.agent")
    message = f"اسم کامل من علیرضا نادری است {_SECRET}"
    backend = _TurnBackend("سلام", RuntimeError(f"boom for {_SECRET}"))
    Dream(store, backend).run(message)

    records = _log_records(caplog)
    assert any(r.getMessage().startswith("extraction pass failed") for r in records)
    joined = "\n".join(r.getMessage() for r in records)
    assert _SECRET not in joined
    assert "نادری" not in joined
