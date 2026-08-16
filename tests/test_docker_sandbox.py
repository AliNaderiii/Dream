"""Tests for dream.docker_sandbox — Docker sandbox module.

These tests verify the module's structure and error handling logic without
requiring Docker. Methods that contact a Docker daemon are tested for correct
error behaviour when Docker is unavailable.
"""

from __future__ import annotations

import pytest


def test_docker_sandbox_import():
    """Verify the module imports cleanly and exposes the expected API."""
    from dream.docker_sandbox import (
        DockerSandbox,
        DockerUnavailableError,
        Kernel,
        Language,
        ResourceLimits,
        SandboxExecutionError,
        SandboxResult,
        SandboxTimeoutError,
    )

    assert DockerSandbox is not None
    assert DockerUnavailableError is not None
    assert issubclass(DockerUnavailableError, RuntimeError)
    assert issubclass(SandboxTimeoutError, RuntimeError)
    assert issubclass(SandboxExecutionError, RuntimeError)

    # Enum values.
    assert Language.PYTHON.value == "python"
    assert Language.R.value == "r"
    assert Language.BASH.value == "bash"
    assert Kernel.PYTHON3.value == "python3"
    assert Kernel.IR.value == "ir"

    # Dataclass defaults.
    result = SandboxResult()
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.return_code == -1
    assert result.timed_out is False

    limits = ResourceLimits()
    assert limits.cpu_count == 1.0
    assert limits.memory_mb == 2048
    assert limits.timeout_seconds == 60
    assert limits.network_enabled is False
    assert limits.pids_limit == 100


def test_docker_sandbox_initialisation():
    """Creating a DockerSandbox does not raise, even without Docker."""
    from dream.docker_sandbox import DockerSandbox

    sandbox = DockerSandbox()
    assert sandbox is not None
    assert sandbox._data_dir is not None
    assert sandbox._auto_pull is True
    assert sandbox._keep_containers is False


def test_check_available_returns_false_without_docker():
    """When Docker is not installed, check_available returns False."""
    import subprocess
    from unittest.mock import patch

    from dream.docker_sandbox import DockerSandbox

    sandbox = DockerSandbox()

    # The check runs 'docker info' — mock it to fail.
    with patch.object(sandbox, "_run_docker_cmd", side_effect=FileNotFoundError("No docker")):
        import asyncio
        result = asyncio.run(sandbox.check_available())
        assert result is False


def test_check_docker_raises_without_docker():
    """When Docker is not installed, check_docker raises DockerUnavailableError."""
    from dream.docker_sandbox import DockerSandbox, DockerUnavailableError

    sandbox = DockerSandbox()

    import asyncio
    with pytest.raises(DockerUnavailableError):
        asyncio.run(sandbox.check_docker())


def test_sandbox_result_fields():
    """SandboxResult dataclass fields can all be set."""
    from dream.docker_sandbox import SandboxResult

    result = SandboxResult(
        stdout="hello",
        stderr="world",
        return_code=0,
        timed_out=False,
        output_files=["/tmp/test.png"],
        elapsed_seconds=0.5,
    )
    assert result.stdout == "hello"
    assert result.stderr == "world"
    assert result.return_code == 0
    assert result.timed_out is False
    assert result.output_files == ["/tmp/test.png"]
    assert result.elapsed_seconds == 0.5
    assert result.error is None


def test_resource_limits_override():
    """Resource limits can be overridden."""
    from dream.docker_sandbox import ResourceLimits

    limits = ResourceLimits(cpu_count=2.0, memory_mb=4096, timeout_seconds=120, network_enabled=True)
    assert limits.cpu_count == 2.0
    assert limits.memory_mb == 4096
    assert limits.timeout_seconds == 120
    assert limits.network_enabled is True


def test_code_filename():
    """Language maps to correct filename."""
    from dream.docker_sandbox import DockerSandbox, Language

    assert DockerSandbox._code_filename(Language.PYTHON) == "script.py"
    assert DockerSandbox._code_filename(Language.R) == "script.R"
    assert DockerSandbox._code_filename(Language.BASH) == "script.sh"


def test_run_command():
    """Language maps to correct execution command."""
    from dream.docker_sandbox import DockerSandbox, Language

    assert DockerSandbox._run_command(Language.PYTHON, "test.py") == ["python3", "test.py"]
    assert DockerSandbox._run_command(Language.R, "test.R") == ["Rscript", "test.R"]
    assert DockerSandbox._run_command(Language.BASH, "test.sh") == ["/bin/bash", "test.sh"]


def test_seccomp_profile_generation():
    """Seccomp profile is a valid dict with required structure."""
    from dream.docker_sandbox import DockerSandbox

    profile = DockerSandbox._build_seccomp_profile()
    assert isinstance(profile, dict)
    assert profile["defaultAction"] == "SCMP_ACT_ERRNO"
    assert "architectures" in profile
    assert "syscalls" in profile
    assert len(profile["syscalls"]) == 1
    assert profile["syscalls"][0]["action"] == "SCMP_ACT_ALLOW"
    assert "accept" in profile["syscalls"][0]["names"]
    assert "write" in profile["syscalls"][0]["names"]
    assert "writev" in profile["syscalls"][0]["names"]


def test_docker_unavailable_error_message():
    """DockerUnavailableError has a meaningful message."""
    from dream.docker_sandbox import DockerUnavailableError

    err = DockerUnavailableError("Docker not found")
    assert str(err) == "Docker not found"


def test_docker_sandbox_package_exports():
    """The bridge's __init__ re-exports sandbox types when available."""
    try:
        from dream.bridge import DockerSandbox, DockerUnavailableError, ResourceLimits, SandboxResult
        assert DockerSandbox is not None
        assert DockerUnavailableError is not None
    except ImportError:
        pass  # OK if docker not installed


def test_install_packages_raises_without_docker():
    """install_packages raises DockerUnavailableError when Docker is absent."""
    from dream.docker_sandbox import DockerSandbox

    sandbox = DockerSandbox()
    import asyncio
    with pytest.raises((ImportError, RuntimeError, FileNotFoundError)):
        asyncio.run(sandbox.install_packages(["numpy"], language="python"))


def test_run_notebook_requires_existing_file():
    """run_notebook raises FileNotFoundError for nonexistent notebook."""
    from dream.docker_sandbox import DockerSandbox

    sandbox = DockerSandbox()
    import asyncio
    with pytest.raises(FileNotFoundError):
        asyncio.run(sandbox.run_notebook("/nonexistent/notebook.ipynb"))