"""The authoritative Code-execution contract: validation, isolation, fail-closed.

Everything here is exercised through the *registered bridge handler*
(``BridgeMethods.sandbox_run_code`` — the method the dispatch table actually
resolves for ``"sandbox.run_code"``), not through a helper, so a change that
disconnects the UI from the core fails a test.

The container itself is not available in CI: every test therefore injects a
fake runner. The fake proves **policy** — what the backend refuses, what it
clamps, what it reports when there is no runtime. It cannot and does not prove
kernel isolation; that claim is made nowhere in this file. The argv the real
runner would build is asserted separately in
``tests/test_docker_sandbox_hardening.py``.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.methods import BridgeMethods
from dream.security import codeexec
from dream.security.codeexec import (
    MAX_CODE_BYTES,
    MAX_TIMEOUT_SECONDS,
    CodeExecutionLimits,
    CodeExecutionRequest,
    CodeExecutionRuntime,
)

# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #


class FakeResult:
    """Stands in for ``dream.docker_sandbox.SandboxResult``."""

    def __init__(
        self,
        *,
        stdout: str = "",
        stderr: str = "",
        return_code: int = 0,
        timed_out: bool = False,
        cancelled: bool = False,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.return_code = return_code
        self.timed_out = timed_out
        self.cancelled = cancelled
        self.output_files: list[str] = []
        self.container_name = ""


class FakeRunner:
    """A container runner double: available, records its calls, returns a script."""

    def __init__(
        self,
        result: FakeResult | None = None,
        *,
        available: bool = True,
        side_effect: Exception | None = None,
        writes: dict[str, str] | None = None,
    ) -> None:
        self.available = available
        self.result = result or FakeResult(return_code=0)
        self.side_effect = side_effect
        self.writes = writes or {}
        self.calls: list[dict[str, Any]] = []
        self.killed: list[str] = []

    async def check_available(self) -> bool:
        return self.available

    async def run_code(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.side_effect is not None:
            raise self.side_effect
        workspace = Path(kwargs["workspace_path"])
        for name, text in self.writes.items():
            (workspace / name).write_text(text, encoding="utf-8")
        return self.result

    async def force_remove_container(self, container_name: str) -> bool:
        self.killed.append(container_name)
        return True


class HangingRunner(FakeRunner):
    """Never returns — used for the timeout and cancellation paths."""

    async def run_code(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")


def sandbox_root(tmp_path: Path) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir(parents=True, exist_ok=True)
    return root


def build_bridge(tmp_path: Path, runner: Any) -> BridgeMethods:
    """A real :class:`BridgeMethods` whose sandbox runtime uses *runner*."""
    runtime = CodeExecutionRuntime(runner, root=sandbox_root(tmp_path))
    codeexec.reset_code_execution_runtime(runtime)
    return BridgeMethods(
        sessions_path=str(tmp_path / "sessions.json"),
        projects_path=str(tmp_path / "projects.json"),
        disabled_skills_path=str(tmp_path / "disabled.json"),
        providers_path=str(tmp_path / "providers.json"),
        provenance_dir=str(tmp_path / "provenance"),
        mcp_config_path=str(tmp_path / "mcp.json"),
        acp_config_path=str(tmp_path / "acp.json"),
    )


@pytest.fixture(autouse=True)
def _reset_runtime():
    yield
    codeexec.reset_code_execution_runtime()


def run(bridge: BridgeMethods, params: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(bridge.sandbox_run_code(params))


# --------------------------------------------------------------------------- #
# 1. The registered handler is the one the contract describes
# --------------------------------------------------------------------------- #


def test_registered_dispatch_of_sandbox_run_code_is_the_container_handler(tmp_path) -> None:
    """``sandbox.run_code`` resolves to the built-in handler — exactly once."""
    bridge = build_bridge(tmp_path, FakeRunner())
    handler = bridge.handlers["sandbox.run_code"]
    assert handler == bridge.sandbox_run_code

    # ...and no extension module re-declares it. A second definition would be
    # silently dropped as a collision, which is precisely the accident that hid
    # the host interpreter behind the container handler before MASTER-P0.
    from dream.bridge import methods_sandbox
    from dream.bridge.extensions import Registry

    assert "sandbox.run_code" not in methods_sandbox.HANDLERS
    assert "sandbox.run_code" not in Registry.merged_handlers()


def test_cancel_method_is_registered(tmp_path) -> None:
    bridge = build_bridge(tmp_path, FakeRunner())
    assert bridge.handlers["sandbox.cancel"] == bridge.sandbox_cancel


# --------------------------------------------------------------------------- #
# 2. Success: the exact response shape the UI renders
# --------------------------------------------------------------------------- #


def test_success_response_matches_the_ui_contract(tmp_path) -> None:
    runner = FakeRunner(FakeResult(stdout="hello\n", return_code=0))
    bridge = build_bridge(tmp_path, runner)

    payload = run(bridge, {"code": "print('hello')"})

    # Envelope.
    assert payload["status"] == "success"
    assert isinstance(payload["execution_id"], str) and payload["execution_id"]

    # Detail — every field code.js reads must be present and correct.
    detail = payload["result"]
    assert detail["status"] == payload["status"]
    assert detail["stdout"] == "hello\n"
    assert detail["stderr"] == ""
    assert detail["exit_code"] == 0
    assert isinstance(detail["duration_ms"], (int, float))
    assert detail["timed_out"] is False
    assert detail["truncated"] is False
    assert detail["artifacts"] == []
    assert detail["error"] is None
    assert detail["error_message"] == ""
    assert detail["variables_updated"] == []
    assert detail["isolation"]["network"] == "none"
    assert detail["isolation"]["rootfs"] == "read-only"
    assert detail["isolation"]["capabilities"] == "drop-all"
    assert detail["limits"]["network_enabled"] is False


def test_success_artifacts_and_isolation_are_reported(tmp_path) -> None:
    runner = FakeRunner(FakeResult(stdout="ok\n"), writes={"chart.png": "PNGDATA"})
    bridge = build_bridge(tmp_path, runner)

    payload = run(bridge, {"code": "open('chart.png','w').write('x')"})

    artifacts = payload["result"]["artifacts"]
    assert [a["name"] for a in artifacts] == ["chart.png"]
    assert artifacts[0]["mime_type"] == "image/png"
    assert artifacts[0]["size_bytes"] == len("PNGDATA")
    # The artifact path stays inside the sandbox root.
    assert str(tmp_path) in artifacts[0]["file_path"]


def test_nonzero_exit_is_an_error_status(tmp_path) -> None:
    bridge = build_bridge(tmp_path, FakeRunner(FakeResult(stderr="boom\n", return_code=1)))
    payload = run(bridge, {"code": "raise SystemExit(1)"})
    assert payload["status"] == "error"
    assert payload["result"]["exit_code"] == 1
    assert payload["result"]["stderr"] == "boom\n"
    assert payload["result"]["error"]["code"] == "nonzero_exit"


# --------------------------------------------------------------------------- #
# 3. Request validation (mismatched / malformed schema)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "params,expected_code",
    [
        ({"code": ""}, "code_empty"),
        ({"code": "   \n  "}, "code_empty"),
        ({}, "code_missing"),
        ({"code": 123}, "code_not_text"),
        ({"code": None}, "code_missing"),
        ({"code": "print(1)", "language": "bash"}, "unsupported_language"),
        ({"code": "print(1)", "language": "javascript"}, "unsupported_language"),
        ({"code": "print(1)", "timeout_seconds": 0}, "invalid_limit"),
        ({"code": "print(1)", "timeout_seconds": -5}, "invalid_limit"),
        ({"code": "print(1)", "timeout_seconds": True}, "invalid_limit"),
        ({"code": "print(1)", "timeout_seconds": "15"}, "invalid_limit"),
        ({"code": "print(1)", "memory_mb": 6}, "invalid_limit"),
        ({"code": "print(1)", "pids_limit": 0}, "invalid_limit"),
        ({"code": "print(1)", "cpu_count": 0}, "invalid_limit"),
        ({"code": "print(1)", "max_output_bytes": 1}, "invalid_limit"),
        ({"code": "print(1)", "execution_id": "bad id!"}, "invalid_execution_id"),
        ({"code": "print(1)", "surprise": True}, "unknown_field"),
    ],
)
def test_malformed_requests_are_denied_with_the_common_envelope(
    tmp_path, params: dict[str, Any], expected_code: str
) -> None:
    runner = FakeRunner()
    bridge = build_bridge(tmp_path, runner)

    payload = run(bridge, params)

    # Denied, not an exception: one shape for the UI to render.
    assert payload["status"] == "denied"
    assert payload["result"]["error"]["code"] == expected_code
    assert payload["result"]["error_message"]  # bilingual, human-readable
    # Nothing reached the runner.
    assert runner.calls == []


def test_oversized_payload_is_denied_before_the_runner(tmp_path) -> None:
    runner = FakeRunner()
    bridge = build_bridge(tmp_path, runner)
    payload = run(bridge, {"code": "#" * (MAX_CODE_BYTES + 1)})
    assert payload["status"] == "denied"
    assert payload["result"]["error"]["code"] == "code_too_large"
    assert runner.calls == []


@pytest.mark.parametrize(
    "removed",
    [
        "resource_limits",
        "network_enabled",
        "workspace_path",
        "mount_workspace_read_write",
        "env_vars",
        "docker_host",
    ],
)
def test_boundary_widening_fields_are_refused_by_name(tmp_path, removed: str) -> None:
    """A field that used to widen the sandbox must be refused, never ignored."""
    runner = FakeRunner()
    bridge = build_bridge(tmp_path, runner)

    payload = run(bridge, {"code": "print(1)", removed: {"anything": True}})

    assert payload["status"] == "denied"
    assert payload["result"]["error"]["code"] == "removed_field"
    assert removed in payload["result"]["error"]["detail"]
    assert runner.calls == []


def test_network_cannot_be_requested_even_nested(tmp_path) -> None:
    runner = FakeRunner()
    bridge = build_bridge(tmp_path, runner)
    payload = run(
        bridge,
        {"code": "print(1)", "resource_limits": {"network_enabled": True}},
    )
    assert payload["status"] == "denied"
    assert runner.calls == []


def test_limits_are_passed_to_the_runner_and_network_stays_off(tmp_path) -> None:
    runner = FakeRunner()
    bridge = build_bridge(tmp_path, runner)
    run(
        bridge,
        {
            "code": "print(1)",
            "timeout_seconds": 30,
            "memory_mb": 512,
            "cpu_count": 2,
            "pids_limit": 32,
        },
    )
    limits = runner.calls[0]["resource_limits"]
    assert limits.timeout_seconds == 30
    assert limits.memory_mb == 512
    assert limits.cpu_count == 2
    assert limits.pids_limit == 32
    assert limits.network_enabled is False
    assert runner.calls[0]["mount_workspace_read_write"] is True


def test_timeout_above_the_ceiling_is_denied(tmp_path) -> None:
    bridge = build_bridge(tmp_path, FakeRunner())
    payload = run(bridge, {"code": "print(1)", "timeout_seconds": MAX_TIMEOUT_SECONDS + 1})
    assert payload["status"] == "denied"
    assert payload["result"]["error"]["code"] == "invalid_limit"


def test_limits_dataclass_refuses_network_unconditionally() -> None:
    with pytest.raises(ValueError):
        CodeExecutionLimits(network_enabled=True)
    with pytest.raises(ValueError):
        CodeExecutionLimits(memory_mb=10_000)
    with pytest.raises(ValueError):
        CodeExecutionLimits(timeout_seconds=10_000)


# --------------------------------------------------------------------------- #
# 4. Workspace confinement: traversal, symlinks, absolute paths
# --------------------------------------------------------------------------- #


def test_absolute_workspace_outside_the_root_is_denied(tmp_path) -> None:
    bridge = build_bridge(tmp_path, FakeRunner())
    payload = run(bridge, {"code": "print(1)", "workspace": "/etc"})
    assert payload["status"] == "denied"
    assert payload["result"]["error"]["code"] == "workspace_outside_root"


def test_dotdot_traversal_is_denied(tmp_path) -> None:
    root = sandbox_root(tmp_path)
    bridge = build_bridge(tmp_path, FakeRunner())
    escape = root / "runs" / ".." / ".." / ".." / ".." / "etc"
    payload = run(bridge, {"code": "print(1)", "workspace": str(escape)})
    assert payload["status"] == "denied"
    assert payload["result"]["error"]["code"] == "workspace_outside_root"


def test_symlink_escape_is_denied(tmp_path) -> None:
    """A symlink *inside* the root that points outside it must not widen the mount."""
    root = sandbox_root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "link-out"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover - Windows without privilege
        pytest.skip("symlinks are not available on this platform")

    bridge = build_bridge(tmp_path, FakeRunner())
    payload = run(bridge, {"code": "print(1)", "workspace": str(link)})

    assert payload["status"] == "denied"
    assert payload["result"]["error"]["code"] == "workspace_outside_root"


def test_symlinked_parent_escape_is_denied(tmp_path) -> None:
    root = sandbox_root(tmp_path)
    outside = tmp_path / "elsewhere"
    (outside / "deep").mkdir(parents=True)
    link = root / "alias"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover
        pytest.skip("symlinks are not available on this platform")

    bridge = build_bridge(tmp_path, FakeRunner())
    payload = run(bridge, {"code": "print(1)", "workspace": str(link / "deep")})
    assert payload["status"] == "denied"


def test_default_workspace_is_a_fresh_directory_under_the_root(tmp_path) -> None:
    runner = FakeRunner()
    bridge = build_bridge(tmp_path, runner)
    payload = run(bridge, {"code": "print(1)"})
    assert payload["status"] == "success"
    workspace = Path(runner.calls[0]["workspace_path"]).resolve()
    assert workspace.is_relative_to(sandbox_root(tmp_path).resolve())
    # Named after the execution, so two runs never share a writable directory.
    assert payload["execution_id"] in str(workspace)


def test_a_requested_workspace_inside_the_root_is_honoured(tmp_path) -> None:
    root = sandbox_root(tmp_path)
    target = root / "runs" / "chosen"
    target.mkdir(parents=True)
    runner = FakeRunner()
    bridge = build_bridge(tmp_path, runner)
    payload = run(bridge, {"code": "print(1)", "workspace": str(target)})
    assert payload["status"] == "success"
    assert Path(runner.calls[0]["workspace_path"]).resolve() == target.resolve()


def test_artifacts_never_escape_the_root(tmp_path) -> None:
    """A run cannot turn an outside file into a reported artifact."""
    root = sandbox_root(tmp_path)
    secret = tmp_path / "outside-secret.txt"
    secret.write_text("nope", encoding="utf-8")
    runner = FakeRunner(FakeResult(stdout="ok\n"))
    bridge = build_bridge(tmp_path, runner)

    payload = run(bridge, {"code": "print(1)"})
    for artifact in payload["result"]["artifacts"]:
        assert Path(artifact["file_path"]).resolve().is_relative_to(root.resolve())
    assert str(secret) not in json.dumps(payload)


# --------------------------------------------------------------------------- #
# 5. Fail-closed: no runtime, dead runtime, crashed runner
# --------------------------------------------------------------------------- #


def test_missing_runner_is_unavailable_and_nothing_runs(tmp_path) -> None:
    runtime = CodeExecutionRuntime(None, root=sandbox_root(tmp_path), sandbox_factory=lambda: None)
    codeexec.reset_code_execution_runtime(runtime)
    bridge = BridgeMethods(
        sessions_path=str(tmp_path / "s.json"),
        projects_path=str(tmp_path / "p.json"),
        disabled_skills_path=str(tmp_path / "d.json"),
        providers_path=str(tmp_path / "pr.json"),
        provenance_dir=str(tmp_path / "prov"),
        mcp_config_path=str(tmp_path / "m.json"),
        acp_config_path=str(tmp_path / "a.json"),
    )

    payload = asyncio.run(bridge.sandbox_run_code({"code": "print(1)"}))

    assert payload["status"] == "unavailable"
    assert payload["result"]["error"]["code"] == "runner_missing"
    assert payload["result"]["stdout"] == ""
    assert payload["result"]["exit_code"] == -1


def test_unreachable_daemon_is_unavailable(tmp_path) -> None:
    bridge = build_bridge(tmp_path, FakeRunner(available=False))
    payload = run(bridge, {"code": "print(1)"})
    assert payload["status"] == "unavailable"
    assert payload["result"]["error"]["code"] == "docker_unavailable"


def test_daemon_probe_that_raises_is_unavailable(tmp_path) -> None:
    class ExplodingProbe(FakeRunner):
        async def check_available(self) -> bool:
            raise RuntimeError("daemon socket refused")

    bridge = build_bridge(tmp_path, ExplodingProbe())
    payload = run(bridge, {"code": "print(1)"})
    assert payload["status"] == "unavailable"


def test_runner_startup_failure_is_error_never_success(tmp_path) -> None:
    runner = FakeRunner(side_effect=RuntimeError("docker: command not found"))
    bridge = build_bridge(tmp_path, runner)
    payload = run(bridge, {"code": "print(1)"})
    assert payload["status"] == "error"
    assert payload["result"]["error"]["code"] == "runner_failure"
    assert payload["result"]["exit_code"] == -1
    # The host path is recorded nowhere.
    assert "Traceback" not in payload["result"]["error_message"]


def test_timeout_maps_to_timeout_and_the_container_is_terminated(tmp_path) -> None:
    runner = HangingRunner()
    bridge = build_bridge(tmp_path, runner)
    payload = run(bridge, {"code": "while True: pass", "timeout_seconds": 1})

    assert payload["status"] == "timeout"
    assert payload["result"]["timed_out"] is True
    assert payload["result"]["error"]["code"] == "timeout"
    # The whole container tree was killed, not merely abandoned.
    assert runner.killed, "the container must be terminated on timeout"
    assert runner.killed[0].startswith("dream-code-")


def test_cancellation_terminates_the_container(tmp_path) -> None:
    async def scenario() -> dict[str, Any]:
        runner = HangingRunner()
        runtime = CodeExecutionRuntime(runner, root=sandbox_root(tmp_path))
        codeexec.reset_code_execution_runtime(runtime)
        request = CodeExecutionRequest.from_params(
            {"code": "while True: pass", "execution_id": "exe-cancel-me"},
            sandbox_root=runtime.root,
        )
        task = asyncio.create_task(runtime.run(request))
        for _ in range(200):
            await asyncio.sleep(0.01)
            if "exe-cancel-me" in runtime._live:
                break
        result = await runtime.cancel("exe-cancel-me")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return result

    result = asyncio.run(scenario())
    assert result["status"] == "cancelled"
    assert result["container_killed"] is True


def test_explicit_cancellation_status_is_reported(tmp_path) -> None:
    runner = FakeRunner(FakeResult(cancelled=True, return_code=-1))
    bridge = build_bridge(tmp_path, runner)
    payload = run(bridge, {"code": "print(1)"})
    assert payload["status"] == "cancelled"
    assert payload["result"]["error"]["code"] == "cancelled"


# --------------------------------------------------------------------------- #
# 6. Output bounds and secret hygiene
# --------------------------------------------------------------------------- #


def test_stdout_is_truncated_to_the_budget_and_a_reference_is_kept(tmp_path) -> None:
    runner = FakeRunner(FakeResult(stdout="A" * 50_000))
    bridge = build_bridge(tmp_path, runner)
    payload = run(bridge, {"code": "print('A'*50000)", "max_output_bytes": 1_000})

    detail = payload["result"]
    assert detail["truncated"] is True
    assert len(detail["stdout"].encode("utf-8")) < 2_000
    assert "truncated by Dream" in detail["stdout"]
    assert detail["stdout_path"], "the full stream must still be reachable by path"
    assert Path(detail["stdout_path"]).is_file()


def test_stderr_is_bounded_too(tmp_path) -> None:
    runner = FakeRunner(FakeResult(return_code=1, stderr="E" * 50_000))
    bridge = build_bridge(tmp_path, runner)
    payload = run(bridge, {"code": "boom", "max_output_bytes": 1_000})
    assert payload["result"]["truncated"] is True
    assert len(payload["result"]["stderr"].encode("utf-8")) < 2_000


def test_secret_shaped_output_is_redacted(tmp_path) -> None:
    """A GitHub-shaped token in the output is replaced, not echoed back.

    The fixture is assembled from fragments instead of being written as one
    literal: the repository's own secret scanners (``tools/security_audit.py``
    and ``tests/test_security_secrets.py``) match ``ghp_`` followed by 30+
    characters in every *tracked* file, and this file is tracked. The scanners
    are the control being exercised here, so the fixture moves — the detection
    rule, the scanner, and the assertion all stay exactly as strict as before.
    """
    token = "ghp_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ" + "0123456789"
    runner = FakeRunner(FakeResult(stdout=f"token={token}\n"))
    bridge = build_bridge(tmp_path, runner)
    payload = run(bridge, {"code": "print(os.environ)"})
    assert token not in payload["result"]["stdout"]
    assert "[REDACTED:github-token]" in payload["result"]["stdout"]


def test_host_environment_is_not_forwarded_to_the_runner(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DREAM_TEST_SECRET", "super-secret-value")
    runner = FakeRunner()
    bridge = build_bridge(tmp_path, runner)
    run(bridge, {"code": "print(1)"})
    call = runner.calls[0]
    assert "env_vars" not in call or not call.get("env_vars")


# --------------------------------------------------------------------------- #
# 7. Status / reset / artifacts read the real runtime
# --------------------------------------------------------------------------- #


def test_status_reports_the_container_runtime_not_a_namespace(tmp_path) -> None:
    runner = FakeRunner(FakeResult(stdout="ok\n"), writes={"out.txt": "x"})
    bridge = build_bridge(tmp_path, runner)
    run(bridge, {"code": "print('ok')"})

    payload = asyncio.run(bridge.handlers["sandbox.get_status"]({}))

    assert payload["status"] == "healthy"
    assert payload["backend"] == "docker"
    assert payload["available"] is True
    assert payload["total_executions"] == 1
    assert payload["total_artifacts"] == 1
    assert payload["variables_count"] == 0
    assert payload["network"] == "disabled"
    assert "docker" in payload["statefulness"] or "container" in payload["statefulness"]
    assert Path(payload["sandbox_root"]).resolve() == sandbox_root(tmp_path).resolve()


def test_status_is_unavailable_when_the_daemon_is_not(tmp_path) -> None:
    bridge = build_bridge(tmp_path, FakeRunner(available=False))
    payload = asyncio.run(bridge.handlers["sandbox.get_status"]({}))
    assert payload["available"] is False


def test_artifacts_endpoint_lists_only_real_files(tmp_path) -> None:
    runner = FakeRunner(FakeResult(stdout="ok\n"), writes={"a.csv": "1,2\n"})
    bridge = build_bridge(tmp_path, runner)
    run(bridge, {"code": "print(1)"})

    payload = asyncio.run(bridge.handlers["sandbox.list_artifacts"]({}))
    assert payload["count"] == 1
    assert payload["artifacts"][0]["name"] == "a.csv"


def test_reset_clears_history_and_only_touches_the_sandbox_root(tmp_path) -> None:
    root = sandbox_root(tmp_path)
    bystander = tmp_path / "keep-me.txt"
    bystander.write_text("keep", encoding="utf-8")
    (root / "runs").mkdir()
    (root / "runs" / "stale").mkdir()
    (root / "runs" / "stale" / "junk.txt").write_text("x", encoding="utf-8")

    runner = FakeRunner(FakeResult(stdout="ok\n"))
    bridge = build_bridge(tmp_path, runner)
    run(bridge, {"code": "print(1)"})

    payload = asyncio.run(bridge.handlers["sandbox.reset"]({}))

    assert payload["status"] == "reset"
    assert payload["removed"] >= 1
    assert bystander.read_text(encoding="utf-8") == "keep"
    status = asyncio.run(bridge.handlers["sandbox.get_status"]({}))
    assert status["total_executions"] == 0


def test_reset_does_not_follow_a_symlink_out_of_the_root(tmp_path) -> None:
    root = sandbox_root(tmp_path)
    runs = root / "runs"
    runs.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "important.txt").write_text("do not delete", encoding="utf-8")
    try:
        (runs / "sneaky").symlink_to(victim, target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover
        pytest.skip("symlinks are not available on this platform")

    bridge = build_bridge(tmp_path, FakeRunner())
    asyncio.run(bridge.handlers["sandbox.reset"]({}))

    assert (victim / "important.txt").is_file()


# --------------------------------------------------------------------------- #
# 8. Serialization safety
# --------------------------------------------------------------------------- #


def test_response_is_json_serialisable(tmp_path) -> None:
    runner = FakeRunner(FakeResult(stdout="ok\n"), writes={"a.txt": "x"})
    bridge = build_bridge(tmp_path, runner)
    payload = run(bridge, {"code": "print(1)"})
    json.dumps(payload)  # must not raise


def test_params_that_are_not_an_object_are_a_bridge_error(tmp_path) -> None:
    bridge = build_bridge(tmp_path, FakeRunner())
    with pytest.raises(BridgeError):
        asyncio.run(bridge.sandbox_run_code(["not", "a", "dict"]))


def test_cancel_requires_an_execution_id(tmp_path) -> None:
    bridge = build_bridge(tmp_path, FakeRunner())
    with pytest.raises(BridgeError):
        asyncio.run(bridge.sandbox_cancel({}))
    result = asyncio.run(bridge.sandbox_cancel({"execution_id": "nothing-here"}))
    assert result["status"] == "not_running"


# --------------------------------------------------------------------------- #
# 9. The default sandbox root is not the home directory
# --------------------------------------------------------------------------- #


def test_default_root_is_a_dedicated_directory(monkeypatch) -> None:
    monkeypatch.delenv("DREAM_SANDBOX_ROOT", raising=False)
    monkeypatch.setenv("DREAM_DATA_DIR", "/tmp/dream-root-check")
    root = codeexec.default_sandbox_root()
    assert root == Path("/tmp/dream-root-check/sandbox")
    assert root != Path.home()


def test_default_root_is_overridable(monkeypatch) -> None:
    monkeypatch.setenv("DREAM_SANDBOX_ROOT", "/tmp/explicit-root")
    assert codeexec.default_sandbox_root() == Path("/tmp/explicit-root")


def test_sandbox_root_is_created_owner_only(tmp_path) -> None:
    runtime = CodeExecutionRuntime(FakeRunner(), root=tmp_path / "fresh")
    root = runtime.ensure_root()
    assert root.is_dir()
    # Mode bits are not meaningful on Windows; `posix or ...` keeps the
    # assertion unconditional so it can never be silently skipped.
    group_and_other = root.stat().st_mode & 0o077
    assert os.name != "posix" or group_and_other == 0
