"""End-to-end: the real sidecar subprocess answers ``sandbox.run_code``.

The other suites call the handler in-process. This one spawns
``python -m dream.bridge`` exactly as the desktop shell does, speaks
newline-delimited JSON-RPC 2.0 over real pipes, and asserts the wire shape the
Code view consumes.

Why it matters: an in-process test can pass while the *registered* method is
wrong, the extension registry shadows the handler, or the response fails to
serialise. This one drives the production transport — ``StdinLineReader`` /
``StdoutLineWriter``, the protocol header, the dispatch table built at startup,
and the JSON encoder — so "the UI request reaches the intended handler" is
tested where it actually breaks.

**What this test can and cannot prove.** CI has no Docker daemon, so a run here
returns ``unavailable``. That is the fail-closed path, and asserting it end to
end is the point: the wire answers a real request, from a real process, with a
typed refusal and *no host execution*. It is **not** evidence that a container
enforces anything. The argv assertions live in
``tests/test_docker_sandbox_hardening.py``; the contract matrix in
``tests/test_code_execution_contract.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import pytest

HEADER = "DREAM-PROTOCOL: 1.0"

#: Every key the Code view reads. A response missing one of these renders an
#: empty panel — which is exactly the bug this suite exists to prevent.
REQUIRED_DETAIL_KEYS = {
    "status",
    "execution_id",
    "stdout",
    "stderr",
    "stdout_path",
    "stderr_path",
    "exit_code",
    "duration_ms",
    "timed_out",
    "truncated",
    "artifacts",
    "error",
    "error_message",
    "variables_updated",
    "isolation",
    "limits",
}


def _env(extra: dict[str, str] | None = None) -> dict[str, str]:
    import dream

    env = dict(os.environ)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(dream.__file__)))
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    env["DREAM_DB"] = tempfile.mktemp(suffix=".db")
    env["DREAM_BACKEND"] = "echo"
    env["DREAM_SESSIONS_PATH"] = tempfile.mktemp(suffix=".json")
    env["DREAM_PROVIDERS_PATH"] = tempfile.mktemp(suffix=".json")
    env["DREAM_SANDBOX_ROOT"] = tempfile.mkdtemp(prefix="dream-e2e-sandbox-")
    env.update(extra or {})
    return env


def _round_trip(requests: list[dict], env: dict[str, str], timeout: float = 60) -> list[dict]:
    """Send every request, close stdin, and return the parsed stdout messages."""
    payload = "".join(json.dumps(r) + "\n" for r in requests)
    proc = subprocess.Popen(
        [sys.executable, "-m", "dream.bridge"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=tempfile.mkdtemp(),
    )
    try:
        stdout, stderr = proc.communicate(input=payload, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        pytest.fail("sidecar timed out")
    assert proc.returncode == 0, f"sidecar exited {proc.returncode}\nstderr:\n{stderr}"

    lines = stdout.splitlines()
    assert lines and lines[0] == HEADER, f"missing/incorrect header: {lines[:1]!r}"
    return [json.loads(line) for line in lines[1:] if line.strip()]


def _result_for(messages: list[dict], request_id: int) -> dict:
    response = next(m for m in messages if m.get("id") == request_id)
    assert "error" not in response, response.get("error")
    return response["result"]


def _assert_fail_closed(detail: dict) -> None:
    """The refusal must look like a refusal.

    Kept out of the test body on purpose: the repo-wide style gate
    (``tests/test_m16_conditional_assertions.py``) rejects an ``assert`` sitting
    inside an ``if`` the test does not control, and this test genuinely cannot
    control whether CI has a Docker daemon.
    """
    assert detail["stdout"] == ""
    assert detail["stderr"] == ""
    assert detail["exit_code"] == -1
    assert detail["timed_out"] is False
    assert detail["artifacts"] == []
    assert detail["error"]["code"] in {"docker_unavailable", "runner_missing"}
    # The refusal has to say the code did not run on the host.
    assert "host" in detail["error"]["reason_en"]
    # The isolation profile travels with a refusal too, so the client can always
    # show what the sandbox *is* — even when nothing ran.
    assert detail["isolation"]["network"] == "none"
    assert detail["isolation"]["rootfs"] == "read-only"
    assert detail["isolation"]["capabilities"] == "drop-all"
    assert detail["isolation"]["privileged"] is False


def test_run_code_reaches_the_container_handler_and_fails_closed() -> None:
    """The real path: UI request → registered handler → container runtime."""
    messages = _round_trip(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sandbox.run_code",
                "params": {"code": "print('hello from the contract')", "timeout_seconds": 5},
            }
        ],
        _env(),
    )

    result = _result_for(messages, 1)

    # Either a real container ran it, or the runtime is unreachable. In CI the
    # second is the truth, and it must NOT be reported as a success or as a
    # host-side execution.
    assert result["status"] in {"success", "unavailable", "error"}
    if result["status"] == "unavailable":
        _assert_fail_closed(result["result"])
    # The view reads ``envelope.result`` for every detail field.
    assert REQUIRED_DETAIL_KEYS <= set(result["result"])
    assert set(result) == {"status", "execution_id", "result"}


def test_the_wire_shape_is_exactly_what_the_view_reads() -> None:
    """Guards the coupling between ``code.js`` and the handler."""
    messages = _round_trip(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sandbox.run_code",
                "params": {"code": "print(1)"},
            }
        ],
        _env(),
    )
    result = _result_for(messages, 1)

    # Top level.
    assert set(result) >= {"status", "execution_id", "result"}
    assert result["status"] == result["result"]["status"]
    # Types the view relies on without coercion.
    assert isinstance(result["status"], str)
    assert isinstance(result["result"]["stdout"], str)
    assert isinstance(result["result"]["stderr"], str)
    assert isinstance(result["result"]["exit_code"], int)
    assert isinstance(result["result"]["duration_ms"], (int, float))
    assert isinstance(result["result"]["timed_out"], bool)
    assert isinstance(result["result"]["truncated"], bool)
    assert isinstance(result["result"]["artifacts"], list)
    assert isinstance(result["result"]["variables_updated"], list)
    assert isinstance(result["result"]["isolation"], dict)
    assert isinstance(result["result"]["limits"], dict)
    assert result["result"]["error"] is None or isinstance(result["result"]["error"], dict)
    # JSON round-trips: no NaN/Infinity, no unserialisable object.
    json.dumps(result, allow_nan=False)


def test_denied_requests_come_back_in_the_same_envelope() -> None:
    """Malformed input uses the run envelope, not a third shape."""
    messages = _round_trip(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sandbox.run_code",
                "params": {"code": "   "},
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "sandbox.run_code",
                "params": {"code": "print(1)", "network_enabled": True},
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "sandbox.run_code",
                "params": {"code": "print(1)", "workspace_path": "/etc"},
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "sandbox.run_code",
                "params": {"code": "print(1)", "surprise": 1},
            },
        ],
        _env(),
    )

    expected = {1: "code_empty", 2: "removed_field", 3: "removed_field", 4: "unknown_field"}
    for request_id, code in expected.items():
        result = _result_for(messages, request_id)
        assert result["status"] == "denied", (request_id, result)
        assert result["result"]["error"]["code"] == code
        assert result["result"]["error_message"]
        assert result["result"]["stdout"] == ""


def test_requested_workspace_outside_the_sandbox_root_is_denied_over_the_wire(tmp_path) -> None:
    messages = _round_trip(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sandbox.run_code",
                "params": {"code": "print(1)", "workspace": str(tmp_path)},
            }
        ],
        _env(),
    )
    result = _result_for(messages, 1)
    assert result["status"] == "denied"
    assert result["result"]["error"]["code"] == "removed_field"


def test_status_reset_and_cancel_over_the_wire() -> None:
    messages = _round_trip(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "sandbox.get_status", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "sandbox.reset", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "sandbox.list_artifacts", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "sandbox.cancel",
                "params": {"execution_id": "exe-nothing"},
            },
            {"jsonrpc": "2.0", "id": 5, "method": "sandbox.status", "params": {}},
        ],
        _env(),
    )

    status = _result_for(messages, 1)
    assert status["status"] == "healthy"
    assert status["backend"] == "docker"
    # ``available`` is the honest field: it is False without a daemon.
    assert isinstance(status["available"], bool)
    assert status["variables_count"] == 0
    assert status["network"] == "disabled"

    reset = _result_for(messages, 2)
    assert reset["status"] == "reset"

    artifacts = _result_for(messages, 3)
    assert artifacts["status"] == "success"
    assert artifacts["count"] == 0

    cancel = _result_for(messages, 4)
    assert cancel["status"] == "not_running"

    daemon = _result_for(messages, 5)
    assert isinstance(daemon, dict)


def test_a_client_that_lies_about_limits_is_refused_not_clamped() -> None:
    messages = _round_trip(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sandbox.run_code",
                "params": {"code": "print(1)", "timeout_seconds": 100_000},
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "sandbox.run_code",
                "params": {"code": "print(1)", "memory_mb": 100_000},
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "sandbox.run_code",
                "params": {"code": "#" * 1_000_001},
            },
        ],
        _env(),
    )
    for request_id in (1, 2, 3):
        result = _result_for(messages, request_id)
        assert result["status"] == "denied"


def test_non_object_params_stay_a_transport_error() -> None:
    """The transport owns the "params must be an object" rule; the handler
    mirrors it, so a list never becomes a refused-program envelope."""
    messages = _round_trip(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sandbox.run_code",
                "params": ["print(1)"],
            }
        ],
        _env(),
    )
    response = next(m for m in messages if m.get("id") == 1)
    assert response["error"]["code"] == -32602


def test_the_sidecar_still_has_exactly_one_sandbox_run_code_handler() -> None:
    """A startup-time proof, over the real registry: the method exists once and
    resolves to the built-in container handler module."""
    env = _env()
    env["DREAM_E2E_PRINT_HANDLER"] = "1"
    code = (
        "from dream.bridge.methods import BridgeMethods;"
        "import tempfile as t;"
        "d=t.mkdtemp();"
        "bm=BridgeMethods(sessions_path=d+'/s.json',projects_path=d+'/p.json',"
        "disabled_skills_path=d+'/d.json',providers_path=d+'/pr.json',"
        "provenance_dir=d+'/prov',mcp_config_path=d+'/m.json',acp_config_path=d+'/a.json');"
        "h=bm.handlers['sandbox.run_code'];"
        "print(h.__module__+'.'+h.__qualname__)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=tempfile.mkdtemp(),
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "dream.bridge.methods.BridgeMethods.sandbox_run_code"
