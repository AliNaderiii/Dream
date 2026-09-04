"""SEC-10: bounded, deterministic tests for the sidecar transport and framing.

Every test here drives ``BridgeServer`` through injectable in-memory
transports or a real ``python -m dream.bridge`` subprocess over pipes. There is
no network access, no arbitrary sleep for coordination (all waits are on
events, pipes, or bounded ``communicate``/``wait`` timeouts), no reliance on
test order, and no mutation of the process environment outside an explicit
``monkeypatch``/``env=`` copy.
"""

from __future__ import annotations

import asyncio
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import threading
from typing import Any

import pytest

from dream.bridge.errors import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    PROVIDER_ERROR,
    BridgeError,
    serialise_error,
)
from dream.bridge.methods import BridgeMethods
from dream.bridge.server import (
    DEFAULT_MAX_LINE_BYTES,
    MAX_ECHOED_METHOD_CHARS,
    PROTOCOL_HEADER,
    BridgeServer,
    ListLineReader,
    MemoryLineWriter,
    OversizedLine,
    StdinLineReader,
    StdoutLineWriter,
    read_bounded_lines,
)
from dream.memory import MemoryStore

HEADER = PROTOCOL_HEADER
#: Upper bound for any single subprocess interaction in this module.
SUBPROCESS_TIMEOUT = 30


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #


def make_methods(tmp_path) -> BridgeMethods:
    return BridgeMethods(
        MemoryStore(":memory:"),
        sessions_path=str(tmp_path / "sessions.json"),
        providers_path=str(tmp_path / "providers.json"),
        default_provider="echo",
    )


def req(id_: Any, method: str, params: Any = None, **extra: Any) -> str:
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        body["params"] = params
    body.update(extra)
    return json.dumps(body)


def run_server(lines, methods, **kwargs):
    reader = ListLineReader(lines)
    writer = MemoryLineWriter()
    server = BridgeServer(methods, reader=reader, writer=writer, **kwargs)
    asyncio.run(server.serve())
    return [json.loads(raw) for raw in writer.lines if raw != HEADER]


def errors_with_code(out, code):
    return [m for m in out if m.get("error", {}).get("code") == code]


def sidecar_env(tmp_path, **extra: str) -> dict[str, str]:
    """A copy of the environment pointed at throwaway data files."""
    env = dict(os.environ)
    import dream

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(dream.__file__)))
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    env["DREAM_DB"] = str(tmp_path / "dream.db")
    env["DREAM_BACKEND"] = "echo"
    env["DREAM_SESSIONS_PATH"] = str(tmp_path / "sessions.json")
    env["DREAM_PROVIDERS_PATH"] = str(tmp_path / "providers.json")
    env.pop("DREAM_DEV", None)
    env.update(extra)
    return env


def start_sidecar(tmp_path, *, text: bool = True, env: dict[str, str] | None = None):
    return subprocess.Popen(
        [sys.executable, "-m", "dream.bridge"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        env=env or sidecar_env(tmp_path),
        cwd=tempfile.mkdtemp(dir=tmp_path),
    )


def communicate(proc, payload, timeout: float = SUBPROCESS_TIMEOUT):
    try:
        return proc.communicate(input=payload, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        pytest.fail("sidecar did not exit within the bounded window")


def parse_stdout(stdout: str) -> list[dict[str, Any]]:
    lines = stdout.splitlines()
    assert lines and lines[0] == HEADER, f"missing header: {lines[:1]!r}"
    return [json.loads(line) for line in lines[1:] if line.strip()]


# --------------------------------------------------------------------------- #
# Bounded stdin framing (read_bounded_lines / StdinLineReader).
# --------------------------------------------------------------------------- #


class ChunkedStream(io.RawIOBase):
    """A binary stream that hands out at most ``chunk`` bytes per ``read``.

    ``BufferedReader.readline`` therefore has to reassemble every line from
    several partial reads — the "fragmented frame" case.
    """

    def __init__(self, data: bytes, chunk: int) -> None:
        self._buf = io.BytesIO(data)
        self._chunk = chunk

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:  # type: ignore[override]
        piece = self._buf.read(min(len(b), self._chunk))
        b[: len(piece)] = piece
        return len(piece)


def bounded(data: bytes, limit: int, chunk: int = 3) -> list[Any]:
    stream = io.BufferedReader(ChunkedStream(data, chunk), buffer_size=4)
    return list(read_bounded_lines(stream, limit))


def test_fragmented_frames_are_reassembled_across_partial_reads():
    data = b'{"a":1}\n{"b":22}\n{"c":333}\n'
    assert bounded(data, limit=64, chunk=2) == ['{"a":1}', '{"b":22}', '{"c":333}']


def test_multiple_frames_in_one_read_are_split():
    data = b'{"a":1}\n{"b":2}\n'
    assert bounded(data, limit=64, chunk=1024) == ['{"a":1}', '{"b":2}']


def test_final_frame_without_newline_is_delivered():
    assert bounded(b'{"a":1}\n{"b":2}', limit=64) == ['{"a":1}', '{"b":2}']


def test_crlf_and_blank_lines_are_normalised():
    assert bounded(b'{"a":1}\r\n\r\n{"b":2}\r\n', limit=64) == ['{"a":1}', "", '{"b":2}']


def test_line_exactly_at_the_bound_is_accepted():
    payload = b"x" * 10
    out = bounded(payload + b"\n" + b'{"ok":1}\n', limit=10)
    assert out == ["x" * 10, '{"ok":1}']


def test_oversized_line_is_discarded_without_buffering_and_reported():
    big = b"x" * 1000
    out = bounded(big + b"\n" + b'{"a":1}\n', limit=10)
    assert isinstance(out[0], OversizedLine)
    assert out[0].size == 1001  # bytes consumed, newline included
    assert out[1] == '{"a":1}'  # the stream stays in sync


def test_oversized_final_line_at_eof_is_reported():
    out = bounded(b"y" * 50, limit=10)
    assert len(out) == 1 and isinstance(out[0], OversizedLine) and out[0].size == 50


def test_invalid_utf8_is_replaced_not_fatal():
    out = bounded(b'{"m":"\xff\xfe"}\n{"ok":1}\n', limit=64)
    assert out[0].startswith('{"m":"') and "\ufffd" in out[0]
    assert out[1] == '{"ok":1}'


def test_stdin_line_reader_streams_markers_and_eof(tmp_path):
    """The production reader thread: partial reads, an oversize line, EOF."""
    data = b'{"a":1}\n' + b"z" * 100 + b"\n" + b'{"b":2}\n'
    stream = io.BufferedReader(ChunkedStream(data, 5), buffer_size=8)
    reader = StdinLineReader(maxsize=2, max_line_bytes=16, stream=stream)

    async def collect() -> list[Any]:
        reader.start(asyncio.get_running_loop())
        got: list[Any] = []
        async for item in reader:
            got.append(item)
        return got

    got = asyncio.run(collect())
    assert got[0] == '{"a":1}'
    assert isinstance(got[1], OversizedLine) and got[1].size == 101
    assert got[2] == '{"b":2}'
    assert len(got) == 3  # EOF sentinel terminated the iteration


def test_server_reports_oversized_marker_as_invalid_request(tmp_path):
    methods = make_methods(tmp_path)
    out = run_server([OversizedLine(123), req(1, "health.check")], methods)
    err = errors_with_code(out, INVALID_REQUEST)
    assert err and err[0]["id"] is None and "too large" in err[0]["error"]["message"]
    assert any(m.get("id") == 1 and "result" in m for m in out)


def test_server_size_guard_still_applies_to_unbounded_readers(tmp_path):
    methods = make_methods(tmp_path)
    out = run_server(["x" * 200, req(1, "health.check")], methods, max_line_bytes=64)
    assert errors_with_code(out, INVALID_REQUEST)
    assert any(m.get("id") == 1 for m in out)


def test_default_bound_is_ten_mib():
    assert DEFAULT_MAX_LINE_BYTES == 10 * 1024 * 1024


# --------------------------------------------------------------------------- #
# Envelope validation.
# --------------------------------------------------------------------------- #


def test_malformed_json_variants_keep_the_loop_alive(tmp_path):
    methods = make_methods(tmp_path)
    bad = ["{", "]", "{'single': 1}", "\x00", "{\"jsonrpc\":", "nul", "\ufeff{}"]
    out = run_server([*bad, req(1, "health.check")], methods)
    parse_errors = errors_with_code(out, PARSE_ERROR)
    # Every unparseable line gets exactly one PARSE_ERROR with a null id.
    assert len(parse_errors) >= len(bad) - 1  # "\ufeff{}" may parse as {} → invalid request
    assert all(e["id"] is None for e in parse_errors)
    assert any(m.get("id") == 1 and "result" in m for m in out)


def test_non_object_json_is_invalid_request(tmp_path):
    methods = make_methods(tmp_path)
    out = run_server(["[]", "42", '"str"', "null", "true"], methods)
    assert len(errors_with_code(out, INVALID_REQUEST)) == 5


def test_invalid_jsonrpc_version_is_rejected_with_id(tmp_path):
    methods = make_methods(tmp_path)
    out = run_server(
        [req(7, "health.check", jsonrpc="1.0"), req(8, "health.check", jsonrpc=2)], methods
    )
    errs = errors_with_code(out, INVALID_REQUEST)
    assert {e["id"] for e in errs} == {7, 8}
    assert all("2.0" in e["error"]["message"] for e in errs)


def test_missing_jsonrpc_field_is_tolerated(tmp_path):
    methods = make_methods(tmp_path)
    out = run_server([json.dumps({"id": 1, "method": "health.check"})], methods)
    assert any(m.get("id") == 1 and "result" in m for m in out)


def test_missing_or_invalid_method_is_invalid_request(tmp_path):
    methods = make_methods(tmp_path)
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": ""}),
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": 5}),
        json.dumps({"jsonrpc": "2.0", "id": 4, "method": None}),
    ]
    out = run_server(lines, methods)
    errs = errors_with_code(out, INVALID_REQUEST)
    assert sorted(e["id"] for e in errs) == [1, 2, 3, 4]


def test_invalid_params_rejected_before_dispatch(tmp_path):
    methods = make_methods(tmp_path)
    calls: list[Any] = []
    methods.handlers["probe.spy"] = lambda params: calls.append(params) or {"ok": True}
    lines = [
        req(1, "probe.spy", [1, 2]),
        req(2, "probe.spy", "str"),
        req(3, "probe.spy", 5),
        req(4, "probe.spy", None),  # null → {} (allowed)
        req(5, "probe.spy"),  # omitted → {}
    ]
    out = run_server(lines, methods)
    errs = errors_with_code(out, INVALID_PARAMS)
    assert sorted(e["id"] for e in errs) == [1, 2, 3]
    assert calls == [{}, {}]
    assert {m["id"] for m in out if "result" in m} == {4, 5}


@pytest.mark.parametrize(
    "bad_id",
    [True, False, 1.5, {"o": 1}, [1], float("nan")],
    ids=["true", "false", "float", "object", "array", "nan"],
)
def test_invalid_id_shapes_are_rejected_deterministically(tmp_path, bad_id):
    methods = make_methods(tmp_path)
    line = json.dumps({"jsonrpc": "2.0", "id": bad_id, "method": "health.check"})
    out = run_server([line], methods)
    assert len(out) == 1
    assert out[0]["id"] is None
    assert out[0]["error"]["code"] == INVALID_REQUEST
    assert "id must be" in out[0]["error"]["message"]


def test_negative_zero_and_huge_integer_ids_round_trip(tmp_path):
    methods = make_methods(tmp_path)
    ids = [-1, 0, 2**63, 2**64 + 1, -(2**70)]
    out = run_server([req(i, "health.check") for i in ids], methods)
    assert sorted(m["id"] for m in out if "result" in m) == sorted(ids)


def test_string_and_null_ids_are_accepted(tmp_path):
    methods = make_methods(tmp_path)
    out = run_server([req("s-1", "health.check"), req(None, "health.check")], methods)
    assert any(m.get("id") == "s-1" and "result" in m for m in out)
    # An explicit ``"id": null`` is still a request per JSON-RPC (answered with null id).
    assert any(m.get("id") is None and "result" in m for m in out)


def test_duplicate_request_ids_each_get_a_response(tmp_path):
    methods = make_methods(tmp_path)
    out = run_server([req(9, "health.check"), req(9, "health.check")], methods)
    assert [m["id"] for m in out if "result" in m] == [9, 9]


def test_unknown_method_name_is_truncated_in_the_error(tmp_path):
    methods = make_methods(tmp_path)
    long_name = "x." + "a" * 5000
    out = run_server([req(1, long_name)], methods)
    err = errors_with_code(out, METHOD_NOT_FOUND)[0]
    assert len(err["error"]["data"]["method"]) == MAX_ECHOED_METHOD_CHARS
    assert len(err["error"]["message"]) < MAX_ECHOED_METHOD_CHARS + 32


def test_notification_for_unknown_method_is_silent(tmp_path):
    methods = make_methods(tmp_path)
    out = run_server([json.dumps({"jsonrpc": "2.0", "method": "nope.nothing"})], methods)
    assert out == []


# --------------------------------------------------------------------------- #
# Handler outcomes: exceptions, cancellation, non-serialisable results.
# --------------------------------------------------------------------------- #


def test_handler_exception_is_typed_and_scoped_to_its_request(tmp_path):
    methods = make_methods(tmp_path)

    def boom(params):
        raise RuntimeError("kaboom")

    async def aboom(params):
        raise TimeoutError("provider took too long")

    methods.handlers["t.boom"] = boom
    methods.handlers["t.aboom"] = aboom
    out = run_server([req(1, "t.boom"), req(2, "t.aboom"), req(3, "health.check")], methods)
    by_id = {m["id"]: m for m in out}
    assert by_id[1]["error"]["code"] == INTERNAL_ERROR
    assert "traceback" not in by_id[1]["error"].get("data", {})  # prod: no traceback
    assert by_id[2]["error"]["code"] == PROVIDER_ERROR  # distinguishable from transport
    assert "result" in by_id[3]


def test_nan_result_becomes_a_typed_error_instead_of_invalid_json(tmp_path):
    methods = make_methods(tmp_path)
    methods.handlers["t.nan"] = lambda p: {"value": math.nan}
    methods.handlers["t.inf"] = lambda p: {"value": math.inf}
    methods.handlers["t.obj"] = lambda p: {"value": object()}
    writer = MemoryLineWriter()
    server = BridgeServer(
        methods, reader=ListLineReader([req(1, "t.nan"), req(2, "t.inf"), req(3, "t.obj")]),
        writer=writer,
    )
    asyncio.run(server.serve())
    for raw in writer.lines[1:]:
        msg = json.loads(raw)  # every emitted line is strictly parseable
        assert msg["error"]["code"] == INTERNAL_ERROR
        assert "serialisable" in msg["error"]["message"]
    assert sorted(json.loads(r)["id"] for r in writer.lines[1:]) == [1, 2, 3]


def test_streaming_failure_emits_end_then_error(tmp_path):
    from dream.bridge.streams import Stream

    methods = make_methods(tmp_path)

    async def chunks():
        yield {"token": "a"}
        raise ValueError("mid-stream")

    async def handler(params):
        return Stream(final={"never": True}, chunks=chunks())

    methods.handlers["t.stream"] = handler
    out = run_server([req(4, "t.stream")], methods)
    seq = [m.get("method") or ("error" if "error" in m else "result") for m in out]
    assert seq == ["stream.start", "stream.chunk", "stream.end", "error"]
    assert out[-1]["error"]["code"] == INVALID_PARAMS


def test_repeated_cancellation_is_idempotent(tmp_path):
    methods = make_methods(tmp_path)
    sid = methods.session_create({})["session_id"]
    out = run_server(
        [req(1, "conversation.stop", {"session_id": sid})] * 3
        + [req(9, "conversation.send", {"session_id": sid, "message": "hi"})],
        methods,
        concurrency=1,
    )
    stops = [m for m in out if m.get("id") == 1]
    assert len(stops) == 3 and all(m["result"]["stopped"] is True for m in stops)
    # The send that follows runs normally: stop clears its own flag on entry.
    final = next(m for m in out if m.get("id") == 9 and "result" in m)
    assert final["result"]["reply"] == "Echo: hi"


def test_drain_is_bounded_and_cancels_stragglers(tmp_path):
    """EOF with a handler that never finishes: serve() returns within the bound."""
    methods = make_methods(tmp_path)
    started = asyncio.Event()
    cancelled = threading.Event()

    async def hang(params):
        started.set()
        try:
            await asyncio.Event().wait()  # never set
        except asyncio.CancelledError:
            cancelled.set()
            raise

    methods.handlers["t.hang"] = hang
    writer = MemoryLineWriter()
    server = BridgeServer(
        methods, reader=ListLineReader([req(1, "t.hang")]), writer=writer, drain_seconds=0.05
    )

    async def scenario():
        await asyncio.wait_for(server.serve(), timeout=5)

    asyncio.run(scenario())
    assert cancelled.is_set()
    # No response is fabricated for a cancelled request; only the header was written.
    assert writer.lines == [HEADER]


def test_concurrent_requests_complete_independently(tmp_path):
    methods = make_methods(tmp_path)
    gate = asyncio.Event()

    async def slow(params):
        await gate.wait()
        return {"slow": params["n"]}

    async def release(params):
        gate.set()
        return {"released": True}

    methods.handlers["t.slow"] = slow
    methods.handlers["t.release"] = release
    lines = [req(i, "t.slow", {"n": i}) for i in range(5)] + [req(99, "t.release")]
    out = run_server(lines, methods, concurrency=8)
    assert sorted(m["result"]["slow"] for m in out if "slow" in m.get("result", {})) == [
        0, 1, 2, 3, 4,
    ]
    assert any(m.get("id") == 99 for m in out)


def test_blocking_tool_does_not_block_the_loop(tmp_path):
    """A ``tool.execute`` running a slow tool must not stall ``health.check``."""
    methods = make_methods(tmp_path)
    release = threading.Event()
    entered = threading.Event()

    from dream import tools as tools_module

    def fake_execute(name, arguments, approved=False):
        entered.set()
        assert release.wait(timeout=10), "tool never released"
        return json.dumps({"status": "ok", "result": name})

    original = tools_module.execute
    tools_module.execute = fake_execute  # patched for this test only
    try:
        order: list[Any] = []

        class OrderWriter(MemoryLineWriter):
            async def write(self, line: str) -> None:
                await super().write(line)
                if line != HEADER:
                    order.append(json.loads(line).get("id"))
                    if json.loads(line).get("id") == 2:
                        release.set()  # health answered while the tool is still running

        writer = OrderWriter()
        lines = [
            req(1, "tool.execute", {"name": "calculate", "arguments": {"expression": "1"}}),
            req(2, "health.check"),
        ]
        server = BridgeServer(methods, reader=ListLineReader(lines), writer=writer)

        async def scenario():
            await asyncio.wait_for(server.serve(), timeout=15)

        asyncio.run(scenario())
    finally:
        tools_module.execute = original
    assert entered.is_set()
    assert order == [2, 1], order


def test_writer_failure_shuts_the_server_down_without_raising(tmp_path):
    methods = make_methods(tmp_path)

    class BrokenWriter:
        def __init__(self) -> None:
            self.calls = 0

        async def write(self, line: str) -> None:
            self.calls += 1
            raise BrokenPipeError(32, "Broken pipe")

    writer = BrokenWriter()
    server = BridgeServer(
        methods,
        reader=ListLineReader([req(1, "health.check"), req(2, "health.check")]),
        writer=writer,  # type: ignore[arg-type]
    )
    asyncio.run(asyncio.wait_for(server.serve(), timeout=5))
    # First write (the header) failed; nothing further was attempted.
    assert writer.calls == 1


def test_reader_failure_is_reported_as_eof_not_a_crash():
    class ExplodingStream:
        def __init__(self) -> None:
            self.reads = 0

        def readline(self, limit: int = -1) -> bytes:
            self.reads += 1
            if self.reads == 1:
                return b'{"jsonrpc":"2.0","id":1,"method":"health.check"}\n'
            raise OSError("read error")

    reader = StdinLineReader(stream=ExplodingStream())

    async def collect():
        reader.start(asyncio.get_running_loop())
        return [item async for item in reader]

    got = asyncio.run(asyncio.wait_for(collect(), timeout=5))
    assert len(got) == 1  # the good line, then a clean EOF sentinel


def test_stdout_writer_serialises_and_flushes_lines():
    buf = io.StringIO()
    writer = StdoutLineWriter(stream=buf)

    async def scenario():
        await asyncio.gather(*(writer.write(f"l{i}") for i in range(20)))

    asyncio.run(scenario())
    writer.close()
    lines = buf.getvalue().splitlines()
    assert sorted(lines) == sorted(f"l{i}" for i in range(20))
    assert all("\n" not in line for line in lines)


# --------------------------------------------------------------------------- #
# Secret-safe error formatting.
# --------------------------------------------------------------------------- #


def test_serialised_errors_never_carry_credentials(monkeypatch):
    monkeypatch.delenv("DREAM_DEV", raising=False)
    key = "sk-live-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    cases = [
        RuntimeError(f"request failed: Authorization: Bearer {key}"),
        ValueError(f"api_key={key} rejected"),
        ConnectionError(f"https://api.example.com/v1?token={key}"),
        BridgeError(PROVIDER_ERROR, f"password: {key}"),
    ]
    for exc in cases:
        payload = json.dumps(serialise_error(exc, 1))
        assert key not in payload, payload
        assert "data" not in serialise_error(exc, 1)["error"] or "traceback" not in json.dumps(
            serialise_error(exc, 1)["error"]["data"]
        )


# --------------------------------------------------------------------------- #
# Offline / local-only behaviour.
# --------------------------------------------------------------------------- #


def test_local_ollama_configuration_does_not_probe_the_network(tmp_path, monkeypatch):
    """Creating/selecting an Ollama provider builds a backend without any I/O."""
    import socket
    import urllib.request

    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted during local provider configuration")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(urllib.request, "urlopen", refuse)

    methods = make_methods(tmp_path)
    created = methods.provider_create(
        {
            "provider": {
                "kind": "ollama",
                "name": "local",
                "endpoint": "http://127.0.0.1:11434",
                "model": "llama3",
            }
        }
    )
    pid = created["id"]
    sid = methods.session_create({"provider": pid})["session_id"]
    assert methods.session_get({"session_id": sid})["provider"] == pid
    # Selecting it as the session backend builds an OllamaBackend, no probe.
    assert methods.provider_get({"id": pid})["provider"]["kind"] == "ollama"


def test_echo_provider_round_trip_offline(tmp_path, monkeypatch):
    import socket

    monkeypatch.setattr(
        socket, "create_connection",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")),
    )
    methods = make_methods(tmp_path)
    sid = methods.session_create({})["session_id"]
    out = run_server(
        [req(1, "conversation.send", {"session_id": sid, "message": "سلام"})], methods
    )
    final = next(m for m in out if m.get("id") == 1 and "result" in m)
    assert final["result"]["reply"] == "Echo: سلام"


# --------------------------------------------------------------------------- #
# Real subprocess over pipes: partial writes, oversize, EOF, crash-free.
# --------------------------------------------------------------------------- #


def test_subprocess_handles_partial_writes_and_multiple_frames(tmp_path):
    proc = start_sidecar(tmp_path)
    assert proc.stdin is not None and proc.stdout is not None
    line = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "health.check"}) + "\n"
    # Partial write: the frame arrives in three flushes.
    for piece in (line[:10], line[10:25], line[25:]):
        proc.stdin.write(piece)
        proc.stdin.flush()
    # Two frames in one write.
    proc.stdin.write(
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "health.check"}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 3, "method": "sidecar.version"}) + "\n"
    )
    proc.stdin.flush()
    stdout, _stderr = communicate(proc, "")
    assert proc.returncode == 0
    out = parse_stdout(stdout)
    assert sorted(m["id"] for m in out if "result" in m) == [1, 2, 3]


def test_subprocess_rejects_oversized_frame_without_dying(tmp_path):
    """A 12 MiB line (> 10 MiB bound) yields one bounded error; the next request works."""
    proc = start_sidecar(tmp_path, text=False)
    big = b'{"jsonrpc":"2.0","id":1,"method":"health.check","params":{"pad":"'
    big += b"p" * (12 * 1024 * 1024) + b'"}}\n'
    follow = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "health.check"}).encode() + b"\n"
    stdout, stderr = communicate(proc, big + follow, timeout=60)
    assert proc.returncode == 0, stderr.decode("utf-8", "replace")
    out = parse_stdout(stdout.decode("utf-8"))
    too_large = [m for m in out if m.get("error", {}).get("code") == INVALID_REQUEST]
    assert len(too_large) == 1 and "too large" in too_large[0]["error"]["message"]
    assert too_large[0]["id"] is None
    assert any(m.get("id") == 2 and "result" in m for m in out)


def test_subprocess_survives_invalid_utf8_and_malformed_lines(tmp_path):
    proc = start_sidecar(tmp_path, text=False)
    payload = (
        b"\xff\xfe\xfa not json\n"
        + b'{"jsonrpc":"2.0","id":"\xc3\x28","method":"health.check"}\n'
        + json.dumps({"jsonrpc": "2.0", "id": 5, "method": "health.check"}).encode() + b"\n"
    )
    stdout, stderr = communicate(proc, payload)
    assert proc.returncode == 0, stderr.decode("utf-8", "replace")
    out = parse_stdout(stdout.decode("utf-8"))
    assert any(m.get("error", {}).get("code") == PARSE_ERROR for m in out)
    assert any(m.get("id") == 5 and "result" in m for m in out)


def test_subprocess_exits_cleanly_on_stdin_eof_with_no_input(tmp_path):
    proc = start_sidecar(tmp_path)
    stdout, stderr = communicate(proc, "")
    assert proc.returncode == 0, stderr
    assert stdout.splitlines() == [HEADER]


def test_subprocess_error_payloads_do_not_leak_secrets(tmp_path):
    """An auth-shaped failure from a handler crosses the pipe redacted."""
    key = "sk-test-ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ"
    proc = start_sidecar(tmp_path)
    # provider.create with a bogus kind raises a ValueError mentioning inputs;
    # the credential must never appear in the error line.
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "provider.create",
            "params": {"kind": "no-such-kind", "name": "x", "credential": key},
        }
    ) + "\n"
    stdout, stderr = communicate(proc, payload)
    assert proc.returncode == 0, stderr
    assert key not in stdout
    assert key not in stderr
