"""Container hardening: the argv ``docker run`` actually receives.

The isolation boundary is the argv :meth:`DockerSandbox._exec_in_container`
builds. These tests capture that argv by replacing the process launcher, so a
regression that drops ``--cap-drop=ALL``, re-enables the network, mounts the
home directory, or forwards the host environment fails here instead of silently
softening the sandbox.

What this file **does** prove: the flags Dream requests.
What it **does not** prove: that a running kernel honours them. No Docker daemon
is available to CI, so no test here claims real isolation. That limitation is
stated again in ``docs/security/code-execution.md`` and must never be described
as verified.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from dream.docker_sandbox import (
    DockerSandbox,
    DockerUnavailableError,
    Language,
    ResourceLimits,
    SandboxResult,
)


class RecordingDocker:
    """Captures argv and answers like a successful ``docker run``."""

    def __init__(self, *, exit_code: int = 0, stdout: str = "ok\n", stderr: str = "") -> None:
        self.calls: list[list[str]] = []
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    async def __call__(self, cmd: list[str], timeout: int = 60, cwd: str | None = None):
        self.calls.append(list(cmd))
        if self.exit_code != 0 and cmd[0] == "run":
            raise subprocess.CalledProcessError(
                self.exit_code, cmd=" ".join(cmd), output=self.stdout, stderr=self.stderr
            )
        return self.stdout, self.stderr


def patch_launcher(monkeypatch, recorder: RecordingDocker) -> None:
    async def _fake(self, cmd, timeout=60, cwd=None):  # noqa: ANN001
        return await recorder(cmd, timeout, cwd)

    monkeypatch.setattr(DockerSandbox, "_run_docker_cmd_with_output", _fake)
    # Image pulls would shell out to docker too; skip them.
    async def _no_pull(self, image):  # noqa: ANN001
        return None

    monkeypatch.setattr(DockerSandbox, "_ensure_image", _no_pull)


def run_with_flags(
    monkeypatch,
    tmp_path: Path,
    *,
    limits: ResourceLimits | None = None,
    read_write: bool = True,
    recorder: RecordingDocker | None = None,
    container_name: str | None = "dream-code-test",
) -> tuple[SandboxResult, list[list[str]]]:
    recorder = recorder or RecordingDocker()
    patch_launcher(monkeypatch, recorder)
    sandbox = DockerSandbox(data_dir=str(tmp_path / "data"))
    workspace = tmp_path / "work"
    workspace.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(
        sandbox.run_code(
            code="print('hi')",
            language="python",
            workspace_path=workspace,
            resource_limits=limits or ResourceLimits(),
            mount_workspace_read_write=read_write,
            container_name=container_name,
        )
    )
    return result, recorder.calls


def run_argv(monkeypatch, tmp_path: Path, **kwargs) -> list[str]:
    """The argv of the ``docker run`` invocation (the first recorded call)."""
    _, calls = run_with_flags(monkeypatch, tmp_path, **kwargs)
    assert calls, "no docker invocation was recorded"
    return calls[0]


def value_after(argv: list[str], flag: str) -> str | None:
    """The single value following a two-token flag, or ``None``."""
    if flag in argv:
        index = argv.index(flag)
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


# --------------------------------------------------------------------------- #
# Privilege and capability containment
# --------------------------------------------------------------------------- #


def test_capabilities_are_dropped_and_privilege_cannot_be_regained(monkeypatch, tmp_path) -> None:
    argv = run_argv(monkeypatch, tmp_path)
    assert "--cap-drop=ALL" in argv
    assert "--security-opt=no-new-privileges:true" in argv
    assert "--privileged" not in argv
    assert "--cap-add" not in " ".join(argv)


def test_container_process_does_not_run_as_root(monkeypatch, tmp_path) -> None:
    argv = run_argv(monkeypatch, tmp_path)
    assert "--user" in argv
    assert value_after(argv, "--user") not in (None, "", "0", "0:0", "root")


def test_explicit_container_user_is_honoured(monkeypatch, tmp_path) -> None:
    argv = run_argv(monkeypatch, tmp_path, limits=ResourceLimits(user="65534:65534"))
    assert value_after(argv, "--user") == "65534:65534"


def test_userns_remap_is_opt_in_only(monkeypatch, tmp_path) -> None:
    """A daemon without ``userns-remap`` must not break the sandbox."""
    default_argv = run_argv(monkeypatch, tmp_path)
    assert not any(a.startswith("--userns") for a in default_argv)

    remapped = run_argv(monkeypatch, tmp_path, limits=ResourceLimits(userns_remap=True))
    assert "--userns=remap" in remapped


# --------------------------------------------------------------------------- #
# Filesystem containment
# --------------------------------------------------------------------------- #


def test_root_filesystem_is_read_only(monkeypatch, tmp_path) -> None:
    argv = run_argv(monkeypatch, tmp_path)
    assert "--read-only" in argv


def test_tmp_is_a_bounded_tmpfs_not_a_host_mount(monkeypatch, tmp_path) -> None:
    argv = run_argv(monkeypatch, tmp_path)
    assert "--tmpfs" in argv
    spec = value_after(argv, "--tmpfs")
    assert spec is not None and spec.startswith("/tmp:")


def test_workspace_is_the_only_bind_mount(monkeypatch, tmp_path) -> None:
    argv = run_argv(monkeypatch, tmp_path)
    mounts = [argv[i + 1] for i, token in enumerate(argv) if token == "-v"]
    assert len(mounts) == 1, f"expected exactly one bind mount, got {mounts}"
    source, container_path, mode = mounts[0].rsplit(":", 2)
    assert container_path == "/workspace"
    assert mode == "rw"
    assert Path(source).resolve() == (tmp_path / "work").resolve()


def test_home_directory_and_docker_socket_are_never_mounted(monkeypatch, tmp_path) -> None:
    argv = run_argv(monkeypatch, tmp_path)
    flat = " ".join(argv)
    home = str(Path.home())
    assert home not in flat or str(tmp_path) in home
    assert "docker.sock" not in flat
    assert ":/root" not in flat
    assert "--mount" not in argv


def test_read_only_workspace_when_not_asked_for_write(monkeypatch, tmp_path) -> None:
    argv = run_argv(monkeypatch, tmp_path, read_write=False)
    mounts = [argv[i + 1] for i, token in enumerate(argv) if token == "-v"]
    assert mounts[0].endswith(":ro")


# --------------------------------------------------------------------------- #
# Network containment
# --------------------------------------------------------------------------- #


def test_network_is_none_by_default(monkeypatch, tmp_path) -> None:
    argv = run_argv(monkeypatch, tmp_path)
    assert "--network=none" in argv


def test_network_only_leaves_none_when_explicitly_enabled(monkeypatch, tmp_path) -> None:
    """The low-level runner can opt in; the Code contract never does (see the
    contract tests, which refuse ``network_enabled`` by name)."""
    argv = run_argv(monkeypatch, tmp_path, limits=ResourceLimits(network_enabled=True))
    assert "--network=none" not in argv


def test_no_host_network_namespace(monkeypatch, tmp_path) -> None:
    argv = run_argv(monkeypatch, tmp_path)
    assert "--network=host" not in argv
    assert "--net=host" not in argv
    assert "--pid=host" not in argv
    assert "--ipc=host" not in argv
    assert "--uts=host" not in argv


# --------------------------------------------------------------------------- #
# Resource bounds
# --------------------------------------------------------------------------- #


def test_memory_cpu_pid_and_swap_bounds_are_requested(monkeypatch, tmp_path) -> None:
    limits = ResourceLimits(cpu_count=2, memory_mb=512, pids_limit=32, disk_mb=256)
    argv = run_argv(monkeypatch, tmp_path, limits=limits)
    assert "--cpus=2" in argv
    assert "--memory=512m" in argv
    assert "--pids-limit=32" in argv
    assert "--memory-swap=0" in argv  # swap cannot extend the memory cap


def test_seccomp_profile_is_applied(monkeypatch, tmp_path) -> None:
    argv = run_argv(monkeypatch, tmp_path)
    joined = " ".join(argv)
    assert "seccomp=" in joined
    profile_index = argv.index("seccomp=" + value_after(argv, "--security-opt").split("=", 1)[1])
    assert profile_index > 0
    # The profile file really was written and is valid JSON.
    import json

    profile_path = value_after(argv, "--security-opt").split("=", 1)[1]
    json.loads(Path(profile_path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Environment hygiene
# --------------------------------------------------------------------------- #


def test_environment_variables_are_all_literal_values(monkeypatch, tmp_path) -> None:
    """No ``--env-file`` and no bare ``-e NAME`` (which forwards a host var)."""
    argv = run_argv(monkeypatch, tmp_path)
    assert "--env-file" not in argv
    assert "-e" in argv
    bare = [
        argv[index + 1]
        for index, token in enumerate(argv)
        if token == "-e" and "=" not in argv[index + 1]
    ]
    assert bare == [], f"bare -e values would forward host variables: {bare}"


def test_home_points_at_the_writable_tmpfs(monkeypatch, tmp_path) -> None:
    argv = run_argv(monkeypatch, tmp_path)
    assert "HOME=/tmp" in argv
    assert "MPLCONFIGDIR=/tmp/mpl" in argv


def test_host_environment_is_never_forwarded(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DREAM_LEAK_CANARY", "do-not-forward")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-never-appear")
    argv = run_argv(monkeypatch, tmp_path)
    flat = " ".join(argv)
    assert "do-not-forward" not in flat
    assert "sk-should-never-appear" not in flat
    assert "DREAM_LEAK_CANARY" not in flat
    assert "OPENAI_API_KEY" not in flat


def test_caller_supplied_env_vars_are_the_only_additions(monkeypatch, tmp_path) -> None:
    _, calls = run_with_flags(monkeypatch, tmp_path)
    argv = calls[0]
    markers = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
    credential_shaped = [
        argv[index + 1].split("=", 1)[0].upper()
        for index, token in enumerate(argv)
        if token == "-e"
        and any(marker in argv[index + 1].split("=", 1)[0].upper() for marker in markers)
    ]
    assert credential_shaped == [], f"credential-shaped environment names: {credential_shaped}"


# --------------------------------------------------------------------------- #
# Container identity + teardown
# --------------------------------------------------------------------------- #


def test_the_caller_chosen_container_name_is_used(monkeypatch, tmp_path) -> None:
    result, calls = run_with_flags(monkeypatch, tmp_path, container_name="dream-code-abc")
    assert value_after(calls[0], "--name") == "dream-code-abc"
    assert result.container_name == "dream-code-abc"


def test_container_is_removed_on_timeout(monkeypatch, tmp_path) -> None:
    """A timed-out run must terminate the container, not abandon it."""

    class TimingOut(RecordingDocker):
        async def __call__(self, cmd, timeout=60, cwd=None):
            self.calls.append(list(cmd))
            if cmd[0] == "run":
                raise subprocess.TimeoutExpired(cmd="docker run", timeout=timeout)
            return "", ""

    recorder = TimingOut()
    result, calls = run_with_flags(monkeypatch, tmp_path, recorder=recorder)

    assert result.timed_out is True
    removals = [c for c in calls if c[:2] == ["rm", "-f"]]
    assert removals, "the container was left running after a timeout"
    assert removals[0][2] == "dream-code-test"


def test_container_is_removed_when_the_client_is_cancelled(monkeypatch, tmp_path) -> None:
    """Cancellation has to reach the container as well as the awaiting task."""

    class Cancelled(RecordingDocker):
        async def __call__(self, cmd, timeout=60, cwd=None):
            self.calls.append(list(cmd))
            if cmd[0] == "run":
                raise asyncio.CancelledError()
            return "", ""

    recorder = Cancelled()
    patch_launcher(monkeypatch, recorder)
    sandbox = DockerSandbox(data_dir=str(tmp_path / "data"))
    workspace = tmp_path / "work"
    workspace.mkdir(parents=True, exist_ok=True)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            sandbox.run_code(
                code="print('hi')",
                workspace_path=workspace,
                container_name="dream-code-cancel",
            )
        )

    removals = [c for c in recorder.calls if c[:2] == ["rm", "-f"]]
    assert removals, "the container survived cancellation"
    assert removals[0][2] == "dream-code-cancel"


def test_force_remove_container_is_best_effort(monkeypatch, tmp_path) -> None:
    sandbox = DockerSandbox(data_dir=str(tmp_path / "data"))

    async def _boom(self, sub_cmd, args, timeout=60):  # noqa: ANN001
        raise subprocess.CalledProcessError(1, cmd="docker rm")

    monkeypatch.setattr(DockerSandbox, "_run_docker_cmd", _boom)
    assert asyncio.run(sandbox.force_remove_container("ghost")) is False
    assert asyncio.run(sandbox.force_remove_container("")) is False


def test_missing_docker_binary_is_an_unavailable_error(monkeypatch, tmp_path) -> None:
    async def _missing(self, cmd, timeout=60, cwd=None):  # noqa: ANN001
        raise FileNotFoundError("docker")

    monkeypatch.setattr(DockerSandbox, "_run_docker_cmd_with_output", _missing)

    async def _no_pull(self, image):  # noqa: ANN001
        return None

    monkeypatch.setattr(DockerSandbox, "_ensure_image", _no_pull)
    sandbox = DockerSandbox(data_dir=str(tmp_path / "data"))
    workspace = tmp_path / "work"
    workspace.mkdir(parents=True, exist_ok=True)

    with pytest.raises(DockerUnavailableError):
        asyncio.run(sandbox.run_code(code="print(1)", workspace_path=workspace))


def test_nonzero_container_exit_is_reported_as_a_failure(monkeypatch, tmp_path) -> None:
    recorder = RecordingDocker(exit_code=3, stdout="", stderr="traceback\n")
    result, _ = run_with_flags(monkeypatch, tmp_path, recorder=recorder)

    assert result.return_code == 3
    assert result.timed_out is False
    # A non-zero exit is never a success, and the container's own stderr is
    # preserved instead of being reported as an internal runner failure
    # (regression: ``CalledProcessError(stdout=...)`` used to raise TypeError).
    assert result.return_code != 0
    assert "traceback" in result.stderr


def test_language_command_selection_is_unchanged() -> None:
    assert DockerSandbox._run_command(Language.PYTHON, "script.py") == ["python3", "script.py"]
    assert DockerSandbox._run_command(Language.R, "script.R") == ["Rscript", "script.R"]
    assert DockerSandbox._run_command(Language.BASH, "script.sh") == ["/bin/bash", "script.sh"]


# --------------------------------------------------------------------------- #
# Image selection
# --------------------------------------------------------------------------- #


def test_default_image_is_used_when_no_override_is_set(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DREAM_SANDBOX_IMAGE", raising=False)
    sandbox = DockerSandbox(data_dir=str(tmp_path / "data"))
    assert sandbox._image_for(Language.PYTHON) == DockerSandbox.DEFAULT_IMAGES[Language.PYTHON]


def test_image_override_applies_to_python_only(monkeypatch, tmp_path) -> None:
    """An operator can pin (and digest-lock) the Code surface's image without
    silently redirecting R or Bash runs to it."""
    monkeypatch.setenv(
        "DREAM_SANDBOX_IMAGE", "registry.example/dream-sandbox@sha256:" + "0" * 64
    )
    sandbox = DockerSandbox(data_dir=str(tmp_path / "data"))

    pinned = sandbox._image_for(Language.PYTHON)
    assert pinned.startswith("registry.example/dream-sandbox@sha256:")
    assert sandbox._image_for(Language.R) == DockerSandbox.DEFAULT_IMAGES[Language.R]
    assert sandbox._image_for(Language.BASH) == DockerSandbox.DEFAULT_IMAGES[Language.BASH]


def test_the_requested_image_reaches_the_argv(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DREAM_SANDBOX_IMAGE", "dream-sandbox-pinned:1")
    argv = run_argv(monkeypatch, tmp_path)
    assert "dream-sandbox-pinned:1" in argv
