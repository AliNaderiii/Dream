"""Containment: no reachable route executes code on the host (MASTER-P0).

The mission is to prove *absence*. Each test below targets one historical or
plausible route by which a model-authored or user-pasted program could reach a
host ``eval``/``exec``/subprocess instead of the container, and asserts the
route cannot be taken today:

1. ``sandbox.run_code`` — exactly one definition, and it is the container one.
2. ``sandbox_execute_python`` — the old host interpreter's tool wrapper refuses.
3. ``dream.sandbox.executor`` — no ``eval``/``exec``/``compile`` call site left.
4. ``dream.sandbox.isolation`` — no host interpreter left, and not reachable.
5. ``tool.execute`` — the host-exec tool is absent from the model's tool registry.
6. ``workspace.shell_execute`` — approval-bound, and not a code-execution route.
7. AST-gate bypasses cannot reach a runner, because the gate is not the boundary.
8. The whole ``dream/`` package — not just the sandbox subpackage — has no bare
   ``eval()`` / ``exec()`` / ``compile()`` call site.

These are structural assertions plus behavioural ones. A structural test is
worth having here precisely because the failure mode being defended against is
"someone re-adds the convenient path".
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path

import pytest

from dream.bridge.methods import BridgeMethods

REPO_ROOT = Path(__file__).resolve().parent.parent


def build_bridge(tmp_path: Path) -> BridgeMethods:
    return BridgeMethods(
        sessions_path=str(tmp_path / "s.json"),
        projects_path=str(tmp_path / "p.json"),
        disabled_skills_path=str(tmp_path / "d.json"),
        providers_path=str(tmp_path / "pr.json"),
        provenance_dir=str(tmp_path / "prov"),
        mcp_config_path=str(tmp_path / "m.json"),
        acp_config_path=str(tmp_path / "a.json"),
    )


# --------------------------------------------------------------------------- #
# 1. One definition of sandbox.run_code, and it is the container one
# --------------------------------------------------------------------------- #


def test_sandbox_run_code_resolves_to_the_container_handler(tmp_path) -> None:
    bridge = build_bridge(tmp_path)
    handler = bridge.handlers["sandbox.run_code"]

    assert handler.__module__ == "dream.bridge.methods"
    assert handler.__qualname__.endswith("BridgeMethods.sandbox_run_code")
    source = inspect.getsource(handler)
    # It goes through the contract, and the contract only ever calls a runner
    # whose own implementation shells out to `docker`.
    assert "CodeExecutionRequest" in source
    assert "runtime.run(request)" in source


def test_no_extension_module_declares_sandbox_run_code() -> None:
    """A second definition would be dropped as a collision — the old accident."""
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "dream" / "bridge").glob("methods_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "sandbox.run_code":
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], f"sandbox.run_code is declared in {offenders}"


def test_no_extension_module_registers_a_host_interpreter() -> None:
    """No bridge extension may name the removed host-executor entry points."""
    banned = {"sandbox_execute_python", "sandbox_wasm_execute", "sandbox_isolate_execute"}
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "dream" / "bridge").glob("methods_*.py")):
        text = path.read_text(encoding="utf-8")
        for name in banned:
            if name in text:
                offenders.append(f"{path.name}: {name}")
    assert offenders == [], f"host-execution entry points wired into the bridge: {offenders}"


# --------------------------------------------------------------------------- #
# 2. The old host interpreter refuses, and its wrapper reports it
# --------------------------------------------------------------------------- #


def test_sandbox_executor_refuses_to_run_code() -> None:
    from dream.sandbox import ExecutionStatus, SandboxExecutor

    executor = SandboxExecutor(workspace_dir="/tmp/dream-p0-does-not-matter")
    result = executor.execute_python("print(2 + 2)")

    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.stdout == ""
    assert result.exit_code == -1
    assert "no longer runs code on the host" in result.stderr


def test_sandbox_executor_has_no_eval_or_exec_call_site() -> None:
    source = (REPO_ROOT / "dream" / "sandbox" / "executor.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "eval" not in calls
    assert "exec" not in calls
    assert "compile" not in calls
    assert "__import__" not in calls


def test_llm_tool_wrapper_reports_unavailable(tmp_path, monkeypatch) -> None:
    from dream.sandbox import tools as sandbox_tools

    monkeypatch.setattr(sandbox_tools, "_GLOBAL_SANDBOX_ENGINE", None)
    payload = sandbox_tools.sandbox_execute_python("print('should not run')")

    assert payload["success"] is False
    assert payload["available"] is False
    assert payload["reason"] == "host_execution_removed"
    assert payload["result"]["status"] == "unavailable"


def test_slash_command_reports_the_refusal_not_a_fake_result() -> None:
    from dream.sandbox import handle_sandbox_slash_command, reset_global_sandbox_engine

    reset_global_sandbox_engine()
    try:
        out = handle_sandbox_slash_command("/code print('hello')")
    finally:
        reset_global_sandbox_engine()

    assert "hello" not in out
    assert "fail-closed" in out


# --------------------------------------------------------------------------- #
# 3. The isolation subsystem no longer hosts an interpreter
# --------------------------------------------------------------------------- #


def test_no_host_exec_call_site_in_the_sandbox_package() -> None:
    """``dream/sandbox/**`` must contain no ``eval``/``exec``/``compile`` call."""
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "dream" / "sandbox").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name in {"eval", "exec", "compile"}:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    assert offenders == [], f"host interpreter calls remain in the sandbox package: {offenders}"


def test_wasm_micro_sandbox_refuses_and_declares_itself_unavailable() -> None:
    from dream.sandbox.isolation import WasmMicroSandbox

    sandbox = WasmMicroSandbox()
    assert sandbox.available is False

    exit_code, stdout, stderr, _ = sandbox.execute_pure_computation("print('nope')")
    assert exit_code == 126
    assert stdout == ""
    assert "does not execute code" in stderr


def test_isolation_engine_reports_unavailable_not_success() -> None:
    from dream.sandbox.isolation import IsolatedExecutionEngine

    engine = IsolatedExecutionEngine()
    result = engine.execute_isolated("total = sum(range(100))\nprint(total)")

    assert result.success is False
    assert result.exit_code == 126
    assert "does not execute code" in result.stderr
    stats = engine.get_security_stats()
    assert stats["execution_available"] is False
    assert stats["static_audit_only"] is True


def test_isolation_slash_command_says_so() -> None:
    from dream.sandbox.isolation import handle_isolation_slash_command

    out = handle_isolation_slash_command("/isolate print(42)")
    assert "42" not in out
    assert "fail-closed" in out


def test_static_audit_still_detects_a_hostile_payload() -> None:
    """The audit itself is real: it still classifies, it just cannot run."""
    from dream.sandbox.isolation import sandbox_isolate_execute

    payload = sandbox_isolate_execute("import subprocess\nsubprocess.run(['ls'])")
    assert payload["available"] is False
    assert payload["blocked"] is True
    assert payload["result"]["security_violations"]


# --------------------------------------------------------------------------- #
# 4. The model's tool registry has no execution-shaped tool
# --------------------------------------------------------------------------- #


def test_host_execution_tools_are_absent_from_the_model_registry() -> None:
    """``filter_tools`` intersects toolset names with ``REGISTRY``; a toolset
    entry alone must never be enough to hand a tool to the model."""
    from dream.tools.base import REGISTRY

    banned = {
        "sandbox_execute_python",
        "sandbox_analyze_dataset",
        "sandbox_reset_session",
        "sandbox_list_artifacts",
        "sandbox_get_status",
        "sandbox_isolate_execute",
        "sandbox_wasm_execute",
        "sandbox_get_isolation_status",
        "sandbox_export_security_report",
        "sandbox_reset_isolation",
    }
    assert banned & set(REGISTRY) == set()


def test_tool_execute_cannot_be_pointed_at_a_host_interpreter(tmp_path) -> None:
    """``tool.execute`` resolves through ``REGISTRY``, so an unregistered name
    is refused outright — it cannot become a host interpreter."""
    from dream.bridge.errors import INVALID_PARAMS, BridgeError

    bridge = build_bridge(tmp_path)
    with pytest.raises(BridgeError) as caught:
        asyncio.run(bridge.tool_execute({"name": "sandbox_execute_python", "arguments": {}}))
    assert caught.value.code == INVALID_PARAMS
    assert "unknown tool" in str(caught.value)


# --------------------------------------------------------------------------- #
# 5. Shell execution is approval-bound and is not a code route
# --------------------------------------------------------------------------- #


def test_workspace_shell_execute_requires_an_approval_id(tmp_path) -> None:
    """There is no `command` parameter: the RPC can only run what was proposed
    and approved earlier, so it is not an arbitrary-execution route."""
    from dream.bridge import methods_workspace

    source = inspect.getsource(methods_workspace.workspace_shell_execute)
    assert "approval_id" in source
    assert "command" not in source.replace("# ", "")


def test_shell_propose_is_not_a_code_runner(tmp_path) -> None:
    from dream.bridge import methods_workspace

    source = inspect.getsource(methods_workspace.workspace_shell_propose)
    # It only queues a proposal; execution lives behind the approval gate.
    assert "shell_propose" in source
    assert "shell_execute" not in source


# --------------------------------------------------------------------------- #
# 6. The AST gate is defence in depth, not the boundary
# --------------------------------------------------------------------------- #


def test_agentcode_never_evaluates_a_payload() -> None:
    """``preflight_code`` parses; it must contain no evaluation call site."""
    source = (REPO_ROOT / "dream" / "security" / "agentcode.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {
        getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert not ({"eval", "exec", "runpy"} & calls)


def test_a_program_that_defeats_the_gate_still_has_no_runner(tmp_path) -> None:
    """Even if a payload slips the static gate, the only runner is the container:
    with no daemon reachable the answer is `unavailable` and nothing runs."""
    from dream.security import codeexec
    from dream.security.agentcode import preflight_code

    payload = "import os\nprint(os.getcwd())"
    assert preflight_code(payload) is not None  # the gate refuses this

    runtime = codeexec.CodeExecutionRuntime(
        None, root=tmp_path / "root", sandbox_factory=lambda: None
    )
    codeexec.reset_code_execution_runtime(runtime)
    try:
        bridge = build_bridge(tmp_path)
        response = asyncio.run(bridge.sandbox_run_code({"code": "print('x')"}))
    finally:
        codeexec.reset_code_execution_runtime()

    assert response["status"] == "unavailable"
    assert response["result"]["stdout"] == ""


# --------------------------------------------------------------------------- #
# 8. Package-wide: no bare eval/exec/compile anywhere in dream/
# --------------------------------------------------------------------------- #


def _bare_interpreter_calls(path: Path) -> list[str]:
    """``eval(x)`` / ``exec(x)`` / ``compile(x)`` — a *name*, not an attribute.

    ``re.compile``, ``ast.literal_eval`` and friends are attribute calls on
    module objects and are not this pattern, which is why the check looks at
    ``ast.Name`` rather than the attribute text.
    """
    hits: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "compile"}:
                try:
                    label = str(path.relative_to(REPO_ROOT))
                except ValueError:  # a temp file outside the repo (the detector test)
                    label = str(path)
                hits.append(f"{label}:{node.lineno} {node.func.id}()")
    return hits


def test_no_bare_eval_exec_or_compile_anywhere_in_the_package() -> None:
    """A package-wide sweep, not just ``dream/sandbox/**``.

    The container is the boundary, so a stray ``exec`` would not by itself be an
    escape — but the Code surface exists precisely because someone once wrote
    one and pointed a UI at it. An empty list here is cheap to keep and the
    regression it catches is expensive.
    """
    hits: list[str] = []
    for path in sorted((REPO_ROOT / "dream").rglob("*.py")):
        hits.extend(_bare_interpreter_calls(path))
    assert hits == [], "bare interpreter call sites:\n" + "\n".join(hits)


def test_the_package_wide_sweep_would_catch_a_reintroduced_call_site(tmp_path) -> None:
    """Prove the detector fires, so a green sweep means something."""
    planted = tmp_path / "planted.py"
    planted.write_text("def run(payload):\n    exec(payload)\n", encoding="utf-8")
    hits = _bare_interpreter_calls(planted)
    assert len(hits) == 1
    assert "exec()" in hits[0]
