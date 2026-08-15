"""Unit + integration tests for the bridge server: framing, dispatch, streaming.

These exercise the server end-to-end through injectable in-memory transport
(``ListLineReader`` + ``MemoryLineWriter``), so they run fast and need no real
stdin/stdout or Python subprocess.
"""

from __future__ import annotations

import asyncio
import json
import tempfile

import pytest

from dream.bridge.errors import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    RESOURCE_EXHAUSTED,
)
from dream.bridge.methods import BridgeMethods
from dream.bridge.server import (
    DEFAULT_QUEUE_CAP,
    PROTOCOL_HEADER,
    BridgeServer,
    ListLineReader,
    MemoryLineWriter,
)
from dream.memory import MemoryStore


def make_methods() -> BridgeMethods:
    return BridgeMethods(
        MemoryStore(":memory:"),
        sessions_path=tempfile.mktemp(suffix=".json"),
        providers_path=tempfile.mktemp(suffix=".json"),
        default_provider="echo",
    )


def run_server(lines, *, methods=None, **kwargs):
    """Feed *lines* through a fresh server and return parsed output messages."""
    methods = methods or make_methods()
    reader = ListLineReader(lines)
    writer = MemoryLineWriter()
    server = BridgeServer(methods, reader=reader, writer=writer, **kwargs)

    asyncio.run(server.serve())

    parsed = []
    for raw in writer.lines:
        if raw == PROTOCOL_HEADER:
            parsed.append({"__header__": raw})
            continue
        parsed.append(json.loads(raw))
    return parsed, methods


def req(id_, method, params=None):
    return json.dumps({"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})


# --------------------------------------------------------------------------- #
# Framing & protocol-level errors.
# --------------------------------------------------------------------------- #


def test_header_is_emitted_first():
    out, _ = run_server([req(1, "health.check")])
    assert out[0] == {"__header__": PROTOCOL_HEADER}


def test_successful_round_trip():
    out, _ = run_server([req(1, "health.check")])
    response = next(m for m in out if m.get("id") == 1)
    assert response["jsonrpc"] == "2.0"
    assert response["result"]["status"] == "ok"


def test_parse_error_keeps_connection_alive():
    out, _ = run_server(["not json", req(1, "health.check")])
    parse_err = next(m for m in out if m.get("error", {}).get("code") == PARSE_ERROR)
    assert parse_err["id"] is None
    # The subsequent valid request still gets a response.
    assert any(m.get("id") == 1 for m in out)


def test_method_not_found():
    out, _ = run_server([req(5, "bogus.method")])
    err = next(m for m in out if m.get("id") == 5)
    assert err["error"]["code"] == METHOD_NOT_FOUND
    assert err["error"]["data"]["method"] == "bogus.method"


def test_invalid_params_from_handler():
    out, _ = run_server([req(2, "session.get", {"session_id": "nope"})])
    err = next(m for m in out if m.get("id") == 2)
    assert err["error"]["code"] == INVALID_PARAMS


def test_params_not_object_rejected():
    out, _ = run_server(
        [json.dumps({"jsonrpc": "2.0", "id": 9, "method": "health.check", "params": [1, 2]})]
    )
    err = next(m for m in out if m.get("id") == 9)
    assert err["error"]["code"] == INVALID_PARAMS or err["error"]["code"] == INVALID_REQUEST


def test_payload_too_large_rejected():
    out, _ = run_server(["x" * 100], max_line_bytes=10)
    err = next(m for m in out if m.get("error"))
    assert err["error"]["code"] == INVALID_REQUEST
    assert "too large" in err["error"]["message"]


def test_notification_without_id_gets_no_response():
    # A notification (no id) is handled but elicits no response message.
    out, _ = run_server([json.dumps({"jsonrpc": "2.0", "method": "health.check"})])
    # Only the header; no response object.
    assert all(m.get("id") is None or "__header__" in m for m in out)


# --------------------------------------------------------------------------- #
# Streaming.
# --------------------------------------------------------------------------- #


def test_conversation_send_emits_stream_events_then_result():
    # Create a session first, then stream a message into it.
    methods = make_methods()
    sid = methods.session_create({})["session_id"]
    out, _ = run_server(
        [req(1, "conversation.send", {"session_id": sid, "message": "hello there"})], methods=methods
    )
    ids = [m for m in out if m.get("id") == 1 or m.get("params", {}).get("id") == 1]
    methods_seen = [m["method"] for m in ids if "method" in m]
    assert methods_seen[0] == "stream.start"
    assert "stream.chunk" in methods_seen
    assert methods_seen[-1] == "stream.end"
    chunks = [m for m in ids if m.get("method") == "stream.chunk"]
    rejoined = "".join(c["params"]["token"] for c in chunks)
    final = next(m for m in out if m.get("id") == 1 and "result" in m)
    assert rejoined == final["result"]["reply"] == "Echo: hello there"
    # Every chunk carries the request id for routing.
    assert all(c["params"]["id"] == 1 for c in chunks)


def test_streaming_error_before_start_is_error_only():
    # An error raised before the handler returns a Stream (here: invalid
    # session) produces only an error response — no stream.start/end bracket —
    # per protocol §5.1 ("errors before stream.start → only error response").
    methods = make_methods()
    out, _ = run_server(
        [req(1, "conversation.send", {"session_id": "missing", "message": "hi"})], methods=methods
    )
    assert not any(m.get("method") == "stream.start" for m in out)
    err = next(m for m in out if m.get("id") == 1 and "error" in m)
    assert err["error"]["code"] == INVALID_PARAMS


# --------------------------------------------------------------------------- #
# Concurrency & backpressure.
# --------------------------------------------------------------------------- #


def test_concurrent_requests_all_complete():
    methods = make_methods()
    sids = [methods.session_create({})["session_id"] for _ in range(5)]
    lines = [req(i, "conversation.send", {"session_id": sids[i], "message": f"msg {i}"}) for i in range(5)]
    out, _ = run_server(lines, methods=methods, concurrency=5)
    results = [m for m in out if "result" in m and "reply" in (m.get("result") or {})]
    assert len(results) == 5
    replies = sorted(r["result"]["reply"] for r in results)
    assert replies == [f"Echo: msg {i}" for i in range(5)]


def test_queue_cap_rejects_excess_with_resource_exhausted():
    methods = make_methods()
    sid = methods.session_create({})["session_id"]
    # queue_cap=1, concurrency=1: the first request occupies the single slot
    # (suspended in its worker-thread turn); the next lines arrive before it
    # completes, so they are rejected with RESOURCE_EXHAUSTED.
    lines = [
        req(1, "conversation.send", {"session_id": sid, "message": "a"}),
        req(2, "conversation.send", {"session_id": sid, "message": "b"}),
        req(3, "conversation.send", {"session_id": sid, "message": "c"}),
    ]
    out, _ = run_server(lines, methods=methods, concurrency=1, queue_cap=1)
    rejected = [m for m in out if m.get("error", {}).get("code") == RESOURCE_EXHAUSTED]
    assert len(rejected) >= 1


def test_default_queue_cap_is_128():
    assert DEFAULT_QUEUE_CAP == 128


# --------------------------------------------------------------------------- #
# Lifecycle.
# --------------------------------------------------------------------------- #


def test_shutdown_persists_session_index(tmp_path):
    spath = str(tmp_path / "sessions.json")
    ppath = str(tmp_path / "providers.json")
    methods = BridgeMethods(MemoryStore(":memory:"), sessions_path=spath, providers_path=ppath)
    methods.session_create({"title": "persisted"})
    methods.shutdown()
    # The file exists and round-trips.
    import json as _json

    with open(spath, encoding="utf-8") as fh:
        rows = _json.load(fh)
    assert any(r["title"] == "persisted" for r in rows)


def test_id_echo_supports_strings():
    out, _ = run_server([req("abc-123", "health.check")])
    resp = next(m for m in out if m.get("id") == "abc-123")
    assert resp["result"]["status"] == "ok"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
