"""Fail-closed proof: no host-execution fallback for model-generated code.

MASTER-P0 decision **D1** removed both escape hatches that let model-generated
analysis code run on the host:

1. the ``DREAM_DATA_LOCAL_EXEC=1`` opt-in that selected
   ``LocalPythonExecutor`` (a ``python -I`` host subprocess), and
2. the silent ``ImportError`` fallback in
   ``DataScienceRuntime._default_executor`` that did the same thing when
   ``dream.docker_sandbox`` could not be imported.

The tests below prove the removal *behaviourally* — with a subprocess recorder
and an import blockade — rather than by reading the diff:

* the environment variable is inert, in both directions;
* a failed ``DockerSandbox`` import yields a typed ``unavailable`` result, and
  nothing is spawned;
* the bridge reports that as ``UNAVAILABLE`` (-32010) instead of flattening it
  into ``INVALID_PARAMS``;
* the research CodeAct path raises ``ContainerUnavailableError`` *before* it
  writes a parameter file or reaches a runner;
* status reporting never labels a local process as Docker-sandboxed.

The fakes here prove **policy**: that nothing local is invoked. They say nothing
about a container's isolation, which needs a live Docker daemon (see
``docs/security/code-execution.md`` §7).
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

from dream.bridge.errors import UNAVAILABLE, BridgeError
from dream.bridge.methods import BridgeMethods
from dream.research.errors import ResearchError
from dream.research.executor import CodeActExecutor, ContainerUnavailableError, validate_code
from dream.skills.data_science import (
    UNAVAILABLE_EXIT_CODE,
    DataScienceError,
    DataScienceRuntime,
    DataScienceUnavailableError,
    DatasetManager,
    SandboxCodeExecutor,
    UnavailableCodeExecutor,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


class _SpawnRecorder:
    """Record every process creation, and refuse the ones that are not allowed.

    ``allow_programs`` exists because the container executor legitimately starts
    the ``docker`` *client*; what must never happen is the payload being handed
    to a host interpreter. Anything not on the allow-list raises, and every
    attempt is recorded so a test can assert on the whole set.
    """

    def __init__(self, allow_programs: tuple[str, ...] = ()) -> None:
        self.allow_programs = allow_programs
        self.calls: list[tuple[str, str]] = []
        self._real: dict[str, object] = {}

    def install(self, monkeypatch) -> None:
        for name in ("run", "Popen", "call", "check_call", "check_output"):
            self._real[name] = getattr(subprocess, name)
            monkeypatch.setattr(subprocess, name, self._make(name, False))
        for name in ("create_subprocess_exec", "create_subprocess_shell"):
            self._real[name] = getattr(asyncio, name)
            monkeypatch.setattr(asyncio, name, self._make(name, True))
        self._real["os.system"] = sys.modules["os"].system
        monkeypatch.setattr("os.system", self._make("os.system", False))
        # os.exec*/os.spawn* are the other ways out of the process.
        for name in ("execv", "execve", "execvp", "execl", "spawnv", "posix_spawn"):
            if hasattr(sys.modules["os"], name):
                self._real[f"os.{name}"] = getattr(sys.modules["os"], name)
                monkeypatch.setattr(sys.modules["os"], name, self._make(f"os.{name}", False))

    def _make(self, name: str, coroutine: bool):
        if coroutine:

            async def _arecorder(*args, **kwargs):  # noqa: ANN002, ANN003
                self._check(name, args)
                return await self._real[name](*args, **kwargs)

            return _arecorder

        def _recorder(*args, **kwargs):  # noqa: ANN002, ANN003
            self._check(name, args)
            return self._real[name](*args, **kwargs)

        return _recorder

    @staticmethod
    def _argv0(args: tuple) -> str:
        """The program name, whether the call takes an argv or an argv list.

        ``subprocess.Popen`` receives the whole vector as one argument, and
        ``asyncio``'s helper delegates to it, so both shapes must resolve to the
        same name.
        """
        if not args:
            return ""
        first = args[0]
        if isinstance(first, (list, tuple)):
            return Path(str(first[0])).name if first else ""
        return Path(str(first)).name

    def _check(self, name: str, args: tuple) -> None:
        program = self._argv0(args)
        self.calls.append((name, program))
        if program and program in self.allow_programs:
            return
        raise AssertionError(f"a host process was spawned through {name}: {args[:1]!r}")

    @property
    def programs(self) -> list[str]:
        return sorted({program for _, program in self.calls})


@pytest.fixture()
def no_spawn(monkeypatch) -> _SpawnRecorder:
    """Nothing may be spawned at all."""
    recorder = _SpawnRecorder()
    recorder.install(monkeypatch)
    return recorder


@pytest.fixture()
def docker_only(monkeypatch) -> _SpawnRecorder:
    """Only the docker client may be started — never a host interpreter."""
    recorder = _SpawnRecorder(allow_programs=("docker",))
    recorder.install(monkeypatch)
    return recorder


def _block_docker_import(monkeypatch) -> None:
    """Make ``import dream.docker_sandbox`` fail, as on a broken install."""
    import builtins
    import importlib

    real_import = builtins.__import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        if name == "dream.docker_sandbox" or (
            name in {"docker_sandbox", "dream"} and fromlist and "docker_sandbox" in fromlist
        ):
            raise ImportError("simulated: dream.docker_sandbox is not importable")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.delitem(sys.modules, "dream.docker_sandbox", raising=False)
    importlib.invalidate_caches()


# --------------------------------------------------------------------------- #
# 1. The host executor is gone from the product
# --------------------------------------------------------------------------- #


def test_product_module_ships_no_host_python_executor() -> None:
    """The class name that ran scripts locally no longer exists in ``dream/``."""
    from dream.skills import data_science

    assert not hasattr(data_science, "LocalPythonExecutor")
    assert "LocalPythonExecutor" not in data_science.__all__

    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "dream").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "class LocalPythonExecutor" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_the_product_data_science_module_spawns_no_host_process() -> None:
    """A structural pin: the module has no subprocess entry point at all.

    ``dream/skills/data_science.py`` used to launch the host interpreter. It now
    defers every script to the container, so a process-spawning call anywhere in
    this file is a regression by construction.
    """
    source = (REPO_ROOT / "dream" / "skills" / "data_science.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned_attributes = {
        ("subprocess", "run"),
        ("subprocess", "Popen"),
        ("subprocess", "call"),
        ("subprocess", "check_output"),
        ("os", "system"),
        ("sys", "executable"),
    }
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if (node.value.id, node.attr) in banned_attributes:
                found.append(f"line {node.lineno}: {node.value.id}.{node.attr}")
    assert found == []


# --------------------------------------------------------------------------- #
# 2. The environment variable is inert (both directions)
# --------------------------------------------------------------------------- #


def test_the_env_var_no_longer_selects_a_local_executor(monkeypatch, tmp_path, no_spawn) -> None:
    """``DREAM_DATA_LOCAL_EXEC=1`` changes nothing and spawns nothing."""
    monkeypatch.setenv("DREAM_DATA_LOCAL_EXEC", "1")
    monkeypatch.setenv("DREAM_SANDBOX_ROOT", str(tmp_path / "sandbox"))

    executor = DataScienceRuntime._default_executor()

    assert isinstance(executor, SandboxCodeExecutor)
    assert executor.backend == "docker"
    # The recorder raises on any spawn; reaching here proves none happened.
    assert no_spawn.calls == []


def test_the_container_executor_reports_unavailable_without_docker(docker_only, tmp_path) -> None:
    """On a machine with no daemon the result is typed, not a host run.

    This test doubles as the regression for the search path: before D1 the
    runtime answered this exact situation by running the script locally. The
    only process the container path may start is the ``docker`` client — a
    missing binary reaches the same refusal.
    """
    executor = DataScienceRuntime._default_executor()
    result = executor.run("print('never runs')", Path(tmp_path))

    assert result.available is False
    assert result.unavailable is True
    assert result.return_code == UNAVAILABLE_EXIT_CODE
    assert result.error_code == "docker_unavailable"
    assert result.stdout == ""
    assert "host" in result.stderr
    # The payload was never handed to a host interpreter, and the script the
    # container would have run was cleaned up.
    assert docker_only.programs in ([], ["docker"])
    assert Path(tmp_path, "_script.py").exists() is False
    assert Path(tmp_path, "script.py").exists() is False


def test_a_container_that_dies_before_running_is_pointed_at_the_runtime(
    monkeypatch, tmp_path, no_spawn
) -> None:
    """The runtime's own failures arrive as ``unavailable``, not as a result.

    A container that starts and then fails must not be reported as "the script
    ran and returned this".
    """
    from dream.docker_sandbox import DockerSandbox, DockerUnavailableError

    async def _check_docker(self):  # noqa: ANN001
        del self
        raise DockerUnavailableError("daemon went away")

    async def _ensure_image(self, image):  # noqa: ANN001
        del self, image

    async def _exec_in_container(self, **kwargs):  # noqa: ANN003
        del self, kwargs
        raise DockerUnavailableError("daemon went away")

    monkeypatch.setattr(DockerSandbox, "check_docker", _check_docker)
    monkeypatch.setattr(DockerSandbox, "_ensure_image", _ensure_image)
    monkeypatch.setattr(DockerSandbox, "_exec_in_container", _exec_in_container)

    executor = DataScienceRuntime._default_executor()
    result = executor.run("print('never runs')", Path(tmp_path))

    assert result.available is False
    assert result.return_code == UNAVAILABLE_EXIT_CODE
    assert result.error_code == "docker_unavailable"
    assert no_spawn.calls == []


# --------------------------------------------------------------------------- #
# 3. A failed sandbox import fails closed
# --------------------------------------------------------------------------- #


def test_import_failure_selects_a_refusing_stub(monkeypatch, no_spawn) -> None:
    """The old ``ImportError`` fallback is replaced by an explicit refusal."""
    _block_docker_import(monkeypatch)

    executor = DataScienceRuntime._default_executor()

    assert isinstance(executor, UnavailableCodeExecutor)
    assert executor.available is False
    assert executor.backend == "unavailable"
    assert no_spawn.calls == []


def test_the_refusing_stub_never_executes_anything(no_spawn, tmp_path) -> None:
    result = UnavailableCodeExecutor().run("import os; os.system('true')", Path(tmp_path))

    assert result.available is False
    assert result.return_code == UNAVAILABLE_EXIT_CODE
    assert result.error_code == "docker_unavailable"
    assert result.timed_out is False
    assert no_spawn.calls == []
    # It must not even leave a script behind.
    assert list(Path(tmp_path).iterdir()) == []


def test_every_write_to_the_workspace_is_skipped_when_unavailable(no_spawn, tmp_path) -> None:
    """The refusal happens before the payload is written to disk."""
    runtime = DataScienceRuntime(DatasetManager(tmp_path / "datasets"), UnavailableCodeExecutor())
    csv = tmp_path / "sales.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")

    with pytest.raises(DataScienceUnavailableError):
        runtime.load_data(str(csv), "sales")

    # The runtime rolled the registry back, so a retry starts clean.
    assert runtime.list_datasets() == []
    assert no_spawn.calls == []


# --------------------------------------------------------------------------- #
# 4. The unavailability is typed, and the bridge keeps it typed
# --------------------------------------------------------------------------- #


def test_unavailable_is_a_distinct_type_from_a_validation_error() -> None:
    assert issubclass(DataScienceUnavailableError, DataScienceError)
    assert DataScienceUnavailableError.code == "docker_unavailable"
    # A validation failure must not be mistaken for an unavailable runtime.
    assert not issubclass(DataScienceError, DataScienceUnavailableError)


def test_typed_unavailable_error_carries_a_bilingual_reason() -> None:
    message = str(DataScienceUnavailableError())
    assert "unavailable" in message
    assert "میزبان" in message  # Persian: "host"


def _bridge(tmp_path: Path) -> BridgeMethods:
    return BridgeMethods(
        sessions_path=str(tmp_path / "s.json"),
        projects_path=str(tmp_path / "p.json"),
        disabled_skills_path=str(tmp_path / "d.json"),
        providers_path=str(tmp_path / "pr.json"),
        provenance_dir=str(tmp_path / "prov"),
        mcp_config_path=str(tmp_path / "m.json"),
        acp_config_path=str(tmp_path / "a.json"),
    )


def test_the_bridge_answers_unavailable_not_invalid_params(tmp_path, no_spawn) -> None:
    """``data.*`` reports an unavailable runtime as ``UNAVAILABLE`` (-32010)."""
    bridge = _bridge(tmp_path)
    runtime = DataScienceRuntime(DatasetManager(tmp_path / "datasets"), UnavailableCodeExecutor())
    bridge._data_runtime = runtime
    csv = tmp_path / "sales.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")

    with pytest.raises(BridgeError) as caught:
        asyncio.run(bridge._data_call(runtime.load_data, str(csv), "sales"))

    assert caught.value.code == UNAVAILABLE
    assert caught.value.data == {"code": "docker_unavailable", "status": "unavailable"}
    assert no_spawn.calls == []


# --------------------------------------------------------------------------- #
# 5. Research CodeAct refuses before it touches anything
# --------------------------------------------------------------------------- #


def test_research_refuses_before_writing_anything(tmp_path, no_spawn) -> None:
    runtime = DataScienceRuntime(DatasetManager(tmp_path / "datasets"), UnavailableCodeExecutor())
    executor = CodeActExecutor(runtime)

    assert executor.backend == "unavailable"
    assert executor.backend_available is False
    with pytest.raises(ContainerUnavailableError):
        executor.run("d1", "print(1)")

    assert no_spawn.calls == []


def test_container_unavailable_error_is_a_research_error() -> None:
    """So the session's state machine turns it into a controlled FAILED."""
    assert issubclass(ContainerUnavailableError, ResearchError)


def test_research_session_fails_closed_before_the_generic_handler(tmp_path) -> None:
    """The explicit branch must precede ``except Exception`` in ``start``.

    Structural rather than behavioural on purpose: driving a full session needs
    pandas, and a skipped test proves nothing. The ordering is what matters —
    a generic handler first would still stop the run, but it would report the
    failure as an internal error instead of a missing sandbox.
    """
    source = (
        REPO_ROOT / "dream" / "research" / "session.py"
    ).read_text(encoding="utf-8")
    body = source[source.index("def start(") :]
    body = body[: body.index("def _prepare_data(")]
    unavailable_at = body.index("except ContainerUnavailableError")
    generic_at = body.index("except Exception as exc:")
    assert unavailable_at < generic_at


def test_research_source_never_mentions_a_local_backend() -> None:
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "dream" / "research").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for needle in ("local-subprocess", "DREAM_DATA_LOCAL_EXEC"):
            if needle in text and "no longer" not in text:
                offenders.append(f"{path.name}: {needle}")
    assert offenders == []


def test_docker_available_reports_the_configured_executor_not_an_import() -> None:
    """It used to answer ``True`` on a machine with no daemon."""
    from types import SimpleNamespace

    healthy = SimpleNamespace(executor=SimpleNamespace(available=True))
    broken = SimpleNamespace(executor=SimpleNamespace(available=False))
    bare = SimpleNamespace()

    assert CodeActExecutor.docker_available(healthy) is True
    assert CodeActExecutor.docker_available(broken) is False
    assert CodeActExecutor.docker_available(bare) is False


def test_the_code_gate_still_runs_before_availability_is_checked(tmp_path) -> None:
    """Order matters: a refused snippet is refused for the right reason.

    The gate is not the boundary — the container is — but a hostile snippet must
    still be reported as ``ResearchSecurityError`` rather than as a missing
    sandbox, because the two need different user action.
    """
    from dream.research.errors import ResearchSecurityError

    runtime = DataScienceRuntime(DatasetManager(tmp_path / "datasets"), UnavailableCodeExecutor())
    executor = CodeActExecutor(runtime)

    with pytest.raises(ResearchSecurityError):
        executor.run("d1", "import os\nos.system('true')")
    with pytest.raises(ContainerUnavailableError):
        executor.run("d1", validate_code("print(1)"))


# --------------------------------------------------------------------------- #
# 6. Test-only local execution stays test-only
# --------------------------------------------------------------------------- #


def test_the_test_executor_is_not_reachable_from_product_code() -> None:
    """The fixture that may run locally lives under ``tests/`` and is not shipped."""
    assert (REPO_ROOT / "tests" / "_data_science_helpers.py").is_file()
    importers: list[str] = []
    for path in sorted((REPO_ROOT / "dream").rglob("*.py")):
        if "_data_science_helpers" in path.read_text(encoding="utf-8"):
            importers.append(str(path.relative_to(REPO_ROOT)))
    assert importers == []


def test_the_test_executor_declares_itself_a_test_double() -> None:
    """It must never be described — in code or docstring — as a sandbox."""
    from tests._data_science_helpers import LocalTestExecutor, test_executor

    assert LocalTestExecutor.backend == "test-local"
    doc = inspect.getdoc(LocalTestExecutor) or ""
    assert "test-only" in doc.lower()
    assert "not" in doc.lower() and "sandbox" in doc.lower()
    assert isinstance(test_executor(), LocalTestExecutor)
