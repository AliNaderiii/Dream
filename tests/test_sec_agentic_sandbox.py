"""P6 L9-A — the agentic code-execution sandbox policy.

The property these tests defend is narrow and absolute: **the host never
runs model-generated code.** Everything else here (import allowlist, path
confinement, bounds, truncation, cancel) exists so that when the container
boundary is unavailable, Dream refuses instead of quietly moving the
execution onto the owner's machine.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dream.docker_sandbox import DockerUnavailableError, ResourceLimits
from dream.security.agentcode import (
    ALLOWED_IMPORTS,
    AgentCodeResult,
    SandboxPolicy,
    confine_path,
    preflight_code,
    run_agent_code,
    truncate_output,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class RecordingSandbox:
    """A stand-in for :class:`DockerSandbox` that records what it was asked."""

    def __init__(
        self,
        *,
        available: bool = True,
        stdout: str = "",
        stderr: str = "",
        return_code: int = 0,
        timed_out: bool = False,
        raises: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self.available = available
        self._stdout = stdout
        self._stderr = stderr
        self._return_code = return_code
        self._timed_out = timed_out
        self._raises = raises
        self._delay = delay
        self.calls: list[dict[str, object]] = []

    async def check_available(self) -> bool:
        return self.available

    async def run_code(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._raises is not None:
            raise self._raises

        class _Result:
            stdout = self._stdout
            stderr = self._stderr
            return_code = self._return_code
            timed_out = self._timed_out
            elapsed_seconds = 0.01
            output_files: list[str] = []

        return _Result()


# --------------------------------------------------------------------------- #
# Policy bounds
# --------------------------------------------------------------------------- #


def test_network_is_off_and_cannot_be_switched_on() -> None:
    limits = SandboxPolicy().resource_limits()
    assert isinstance(limits, ResourceLimits)
    assert limits.network_enabled is False
    with pytest.raises(ValueError):
        SandboxPolicy(network_enabled=True)


def test_resource_bounds_are_validated() -> None:
    for kwargs in (
        {"timeout_seconds": 0},
        {"timeout_seconds": 10_000},
        {"memory_mb": 8},
        {"memory_mb": 99_999},
        {"cpu_count": 0},
        {"cpu_count": 64},
        {"pids_limit": 0},
        {"max_output_bytes": 10},
    ):
        with pytest.raises(ValueError):
            SandboxPolicy(**kwargs)  # type: ignore[arg-type]


def test_limits_reach_the_sandbox_unchanged() -> None:
    policy = SandboxPolicy(timeout_seconds=12, memory_mb=256, cpu_count=0.5, pids_limit=16)
    sandbox = RecordingSandbox()
    asyncio.run(
        run_agent_code("print(1)", workdir=REPO_ROOT, policy=policy, sandbox=sandbox)
    )
    limits = sandbox.calls[0]["resource_limits"]
    assert limits.timeout_seconds == 12
    assert limits.memory_mb == 256
    assert limits.cpu_count == 0.5
    assert limits.pids_limit == 16
    assert limits.network_enabled is False
    # A read-write mount is never requested by the policy layer.
    assert sandbox.calls[0]["mount_workspace_read_write"] is False


# --------------------------------------------------------------------------- #
# Import allowlist
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "code",
    [
        "import os",
        "import sys",
        "import socket",
        "import subprocess",
        "import requests",
        "import urllib.request",
        "import ctypes",
        "import shutil",
        "import pickle",
        "from os import system",
        "from subprocess import Popen",
        "from . import sibling",
        "import pandas, socket",
    ],
)
def test_denied_imports_are_refused(code: str) -> None:
    refusal = preflight_code(code)
    assert refusal is not None
    assert refusal.code == "denied_import"


@pytest.mark.parametrize(
    "code",
    [
        "import pandas as pd",
        "import numpy as np",
        "import matplotlib.pyplot as plt",
        "from statistics import mean",
        "import json\nimport re\n",
        "import pandas as pd\nprint(pd.DataFrame({'a': [1]}).sum())",
    ],
)
def test_allowlisted_analysis_imports_pass(code: str) -> None:
    assert preflight_code(code) is None


def test_the_allowlist_has_no_ambient_authority_modules() -> None:
    forbidden = {"os", "sys", "socket", "subprocess", "shutil", "pathlib", "ctypes", "pickle"}
    assert not (ALLOWED_IMPORTS & forbidden)


# --------------------------------------------------------------------------- #
# Host-exec builtins and object-graph escapes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "code",
    [
        "exec('print(1)')",
        "eval('1+1')",
        "compile('x', '<s>', 'exec')",
        "__import__('os')",
        "breakpoint()",
        "value = input()",
    ],
)
def test_code_producing_builtins_are_refused(code: str) -> None:
    refusal = preflight_code(code)
    assert refusal is not None
    assert refusal.code == "denied_builtin"


@pytest.mark.parametrize(
    "code",
    [
        "print(().__class__.__bases__)",
        "print(type.__subclasses__(type))",
        "f = lambda: 1\nprint(f.__globals__)",
        "print((1).__reduce__())",
    ],
)
def test_object_graph_escapes_are_refused(code: str) -> None:
    refusal = preflight_code(code)
    assert refusal is not None
    assert refusal.code == "denied_attribute"


# --------------------------------------------------------------------------- #
# Path confinement
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "code",
    [
        "data = open('/etc/passwd').read()",
        "data = open('~/.ssh/id_rsa').read()",
        "data = open('C:/Windows/System32/config').read()",
        "data = open('../../secrets.env').read()",
        "path = '//server/share/secret'",
        "path = '/var/lib/other'",
    ],
)
def test_paths_outside_the_dataset_root_are_refused(code: str) -> None:
    refusal = preflight_code(code)
    assert refusal is not None
    assert refusal.code == "path_escape"


@pytest.mark.parametrize(
    "code",
    [
        "frame = 'sales.csv'",
        "path = '/workspace/sales.csv'",
        "path = 'subdir/data.parquet'",
        "label = 'a..b'",
    ],
)
def test_paths_inside_the_root_pass(code: str) -> None:
    assert preflight_code(code) is None


def test_confine_path_refuses_an_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "inner").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    assert confine_path(root, root / "inner") == (root / "inner").resolve()
    with pytest.raises(PermissionError) as excinfo:
        confine_path(root, outside)
    assert "\u062c\u0639\u0628\u0647" in str(excinfo.value)  # bilingual


def test_confine_path_refuses_a_symlink_out(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover - platform dependent
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(PermissionError):
        confine_path(root, link)


def test_a_workdir_outside_the_root_refuses_before_any_run(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    sandbox = RecordingSandbox()
    result = asyncio.run(
        run_agent_code("print(1)", workdir=other, root=root, sandbox=sandbox)
    )
    assert result.refused
    assert result.refusal is not None and result.refusal.code == "workdir_escape"
    assert sandbox.calls == []


# --------------------------------------------------------------------------- #
# Malformed programs
# --------------------------------------------------------------------------- #


def test_unparsable_code_is_refused_not_executed() -> None:
    refusal = preflight_code("def (:\n")
    assert refusal is not None and refusal.code == "unparsable_code"


def test_empty_and_oversize_and_binary_programs_are_refused() -> None:
    assert preflight_code("").code == "empty_code"  # type: ignore[union-attr]
    assert preflight_code("   \n ").code == "empty_code"  # type: ignore[union-attr]
    assert preflight_code("x = 1\x00").code == "code_not_text"  # type: ignore[union-attr]
    huge = "x = 1\n" * 60_000
    assert preflight_code(huge).code == "code_too_large"  # type: ignore[union-attr]


def test_an_unsupported_language_is_refused() -> None:
    refusal = preflight_code("puts 1", language="ruby")
    assert refusal is not None and refusal.code == "unsupported_language"


# --------------------------------------------------------------------------- #
# Fail-closed: no Docker, no execution
# --------------------------------------------------------------------------- #


def test_missing_docker_refuses_and_never_runs_on_the_host() -> None:
    sandbox = RecordingSandbox(available=False)
    result = asyncio.run(run_agent_code("print(1)", workdir=REPO_ROOT, sandbox=sandbox))
    assert result.refused
    assert result.refusal is not None and result.refusal.code == "docker_unavailable"
    assert sandbox.calls == []
    assert "Docker is unavailable" in result.refusal.reason_en
    assert any("\u0600" <= ch <= "\u06ff" for ch in result.refusal.reason_fa)


def test_docker_vanishing_mid_step_refuses() -> None:
    sandbox = RecordingSandbox(raises=DockerUnavailableError("gone"))
    result = asyncio.run(run_agent_code("print(1)", workdir=REPO_ROOT, sandbox=sandbox))
    assert result.refused
    assert result.refusal is not None and result.refusal.code == "docker_unavailable"


def test_a_sandbox_error_refuses_rather_than_reporting_success() -> None:
    sandbox = RecordingSandbox(raises=RuntimeError("container blew up"))
    result = asyncio.run(run_agent_code("print(1)", workdir=REPO_ROOT, sandbox=sandbox))
    assert result.refused
    assert result.refusal is not None and result.refusal.code == "sandbox_error"
    assert result.ok is False


def test_a_missing_workdir_refuses(tmp_path: Path) -> None:
    sandbox = RecordingSandbox()
    result = asyncio.run(
        run_agent_code("print(1)", workdir=tmp_path / "nope", sandbox=sandbox)
    )
    assert result.refused
    assert result.refusal is not None and result.refusal.code == "workdir_missing"
    assert sandbox.calls == []


# --------------------------------------------------------------------------- #
# Timeout, cancel, and output bounds
# --------------------------------------------------------------------------- #


def test_a_step_that_overruns_its_deadline_is_cancelled() -> None:
    policy = SandboxPolicy(timeout_seconds=1)
    sandbox = RecordingSandbox(delay=30.0)

    async def _drive() -> AgentCodeResult:
        task = asyncio.ensure_future(
            run_agent_code("print(1)", workdir=REPO_ROOT, policy=policy, sandbox=sandbox)
        )
        # The module's own wait_for is the guard; drive it with a virtual
        # clock instead of really sleeping six seconds.
        loop = asyncio.get_running_loop()
        start = loop.time()
        while not task.done() and loop.time() - start < 10:
            await asyncio.sleep(0.05)
        if not task.done():  # pragma: no cover - safety valve
            task.cancel()
            raise AssertionError("the deadline guard did not fire")
        return await task

    result = asyncio.run(asyncio.wait_for(_drive(), timeout=20))
    assert result.timed_out
    assert result.ok is False
    assert "\u0645\u0647\u0644\u062a" in result.stderr  # bilingual cancel notice


def test_a_sandbox_reported_timeout_is_surfaced_honestly() -> None:
    sandbox = RecordingSandbox(timed_out=True, return_code=-1, stderr="Execution timed out")
    result = asyncio.run(run_agent_code("print(1)", workdir=REPO_ROOT, sandbox=sandbox))
    assert result.timed_out and result.ok is False


def test_output_is_truncated_and_reported() -> None:
    policy = SandboxPolicy(max_output_bytes=1_000)
    sandbox = RecordingSandbox(stdout="A" * 50_000)
    result = asyncio.run(
        run_agent_code("print(1)", workdir=REPO_ROOT, policy=policy, sandbox=sandbox)
    )
    assert result.truncated
    assert len(result.stdout.encode()) <= 1_100
    assert result.stdout.endswith("[truncated]")


def test_truncate_output_keeps_short_text_identical() -> None:
    text, cut = truncate_output("short", 1_000)
    assert text == "short" and cut is False


def test_secrets_printed_inside_the_container_are_redacted_on_the_way_out() -> None:
    leaked = "sk_EXAMPLE_not_a_real_key"
    shaped = "sk-" + "abcdefghij" * 3
    sandbox = RecordingSandbox(stdout=f"token {shaped} and {leaked}")
    result = asyncio.run(run_agent_code("print(1)", workdir=REPO_ROOT, sandbox=sandbox))
    assert shaped not in result.stdout
    assert "[REDACTED:" in result.stdout


def test_a_successful_step_reports_its_output() -> None:
    sandbox = RecordingSandbox(stdout="mean = 4.5\n", return_code=0)
    result = asyncio.run(
        run_agent_code(
            "import pandas as pd\nprint(pd.Series([4, 5]).mean())",
            workdir=REPO_ROOT,
            sandbox=sandbox,
        )
    )
    assert result.ok
    assert "mean = 4.5" in result.stdout
    assert result.to_dict()["ok"] is True


# --------------------------------------------------------------------------- #
# The invariant, mechanically
# --------------------------------------------------------------------------- #


def test_no_security_module_executes_model_text_on_the_host() -> None:
    import re

    pattern = re.compile(r"(?<![\w.])(?:exec|eval|compile)\s*\(|runpy\.")
    offenders = []
    for path in sorted((REPO_ROOT / "dream" / "security").glob("*.py")):
        body = "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        if pattern.search(body):
            offenders.append(path.name)
    assert offenders == []


def test_preflight_never_evaluates_the_program() -> None:
    # If preflight executed anything, this would raise SystemExit or write a
    # file. It parses only, so the sentinel stays untouched.
    sentinel = REPO_ROOT / "tests" / "_agentcode_sentinel.tmp"
    code = (
        "import pandas as pd\n"
        f"open({str(sentinel)!r}, 'w').write('written')\n"
        "raise SystemExit(3)\n"
    )
    preflight_code(code)
    assert not sentinel.exists()
