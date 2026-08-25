"""Sandbox-only execution policy for model-generated code (P6, L9-A).

The agentic surfaces added by P1 (research), P3 (data Q&A), and P4
(workspace / agent modes) all want the same dangerous thing: run code a
model just wrote. This module is the policy that stands in front of that
wish. Its contract is short and absolute:

* **the host never executes model code.** There is no ``exec``, ``eval``,
  ``compile``, or ``runpy`` call in this module, and the audit asserts it
  over the whole ``dream/security`` package. Execution happens inside a
  container built by :mod:`dream.docker_sandbox`, which this module
  *calls* and never rewrites.
* **fail closed.** No Docker daemon, an unknown language, an unparsable
  program, a denied import, a path outside the confinement root, or a
  policy object that has been tampered with — every one of those refuses
  with a bilingual reason instead of degrading to a host subprocess.
* **network off, always.** The resource limits this module hands the
  sandbox carry ``network_enabled=False`` unconditionally; there is no
  switch to turn it on, so no caller and no injected plan can ask for one.
* **bounded.** Per-step wall-clock timeout, memory cap, CPU cap, process
  cap, and output truncation. Output is redacted before it is returned,
  so a secret printed inside the container never lands in a transcript.

Imports are deny-by-default: a program may import only the analysis
libraries on :data:`ALLOWED_IMPORTS`. Over-refusing a legitimate program
is an annoyance; letting ``socket`` into a sandbox that a future
misconfiguration connects to the network is an incident.
"""

from __future__ import annotations

import ast
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dream.docker_sandbox import (
    DockerSandbox,
    DockerUnavailableError,
    ResourceLimits,
)
from dream.security.secrets import redact_text

__all__ = [
    "ALLOWED_IMPORTS",
    "DENIED_ATTRIBUTES",
    "DENIED_CALLS",
    "SUPPORTED_LANGUAGES",
    "AgentCodeRefusal",
    "AgentCodeResult",
    "SandboxPolicy",
    "confine_path",
    "preflight_code",
    "run_agent_code",
    "truncate_output",
]

#: Top-level modules a generated analysis program may import. Deny by
#: default: anything not named here is refused before the container starts.
ALLOWED_IMPORTS: frozenset[str] = frozenset(
    {
        # analysis stack
        "pandas",
        "numpy",
        "matplotlib",
        "seaborn",
        "scipy",
        "sklearn",
        "statsmodels",
        "pyarrow",
        # pure-stdlib helpers that carry no ambient authority
        "math",
        "statistics",
        "decimal",
        "fractions",
        "random",
        "json",
        "csv",
        "re",
        "textwrap",
        "string",
        "datetime",
        "calendar",
        "collections",
        "itertools",
        "functools",
        "operator",
        "dataclasses",
        "typing",
        "enum",
        "uuid",
        "warnings",
        "unicodedata",
    }
)

#: Builtins that turn data back into code inside the container. Even in a
#: sandbox they defeat the import allowlist, so they are refused here.
DENIED_CALLS: frozenset[str] = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "breakpoint",
        "input",
        "memoryview",
        "globals",
        "locals",
        "vars",
    }
)

#: Attribute names used to walk out of the object graph into the runtime.
DENIED_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "__builtins__",
        "__globals__",
        "__subclasses__",
        "__bases__",
        "__mro__",
        "__code__",
        "__loader__",
        "__spec__",
        "__reduce__",
        "__reduce_ex__",
        "__getattribute__",
        "__dict__",
    }
)

SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"python"})

#: Where the sandbox mounts the confinement root. Absolute literals in
#: generated code may only reference this subtree.
CONTAINER_WORKDIR = "/workspace"

_MAX_CODE_BYTES = 200_000


@dataclass(frozen=True)
class AgentCodeRefusal:
    """One fail-closed refusal, named in English and Persian."""

    code: str
    reason_en: str
    reason_fa: str
    detail: str = ""

    def message(self) -> str:
        """The two-line bilingual text a caller may surface verbatim."""
        tail = f" ({self.detail})" if self.detail else ""
        return f"{self.reason_en}{tail}\n{self.reason_fa}{tail}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "reason_en": self.reason_en,
            "reason_fa": self.reason_fa,
            "detail": self.detail,
        }


def _refuse(code: str, reason_en: str, reason_fa: str, detail: str = "") -> AgentCodeRefusal:
    return AgentCodeRefusal(code=code, reason_en=reason_en, reason_fa=reason_fa, detail=detail)


@dataclass(frozen=True)
class SandboxPolicy:
    """Bounds for one agentic code step. Network is not configurable."""

    timeout_seconds: int = 60
    memory_mb: int = 1024
    cpu_count: float = 1.0
    pids_limit: int = 64
    disk_mb: int = 512
    max_output_bytes: int = 200_000
    allowed_imports: frozenset[str] = field(default_factory=lambda: ALLOWED_IMPORTS)
    container_workdir: str = CONTAINER_WORKDIR

    #: Fixed, read-only, and asserted by the audit: the sandbox never gets
    #: a network namespace, whatever the caller or the model asks for.
    network_enabled: bool = False

    def __post_init__(self) -> None:
        if self.network_enabled:
            raise ValueError("agentic sandbox policy: network can never be enabled")
        if not 1 <= self.timeout_seconds <= 900:
            raise ValueError("timeout_seconds must be between 1 and 900")
        if not 64 <= self.memory_mb <= 8192:
            raise ValueError("memory_mb must be between 64 and 8192")
        if not 0.1 <= self.cpu_count <= 8:
            raise ValueError("cpu_count must be between 0.1 and 8")
        if not 1 <= self.pids_limit <= 512:
            raise ValueError("pids_limit must be between 1 and 512")
        if not 1_000 <= self.max_output_bytes <= 5_000_000:
            raise ValueError("max_output_bytes must be between 1000 and 5000000")

    def resource_limits(self) -> ResourceLimits:
        """The :class:`~dream.docker_sandbox.ResourceLimits` for this step."""
        return ResourceLimits(
            cpu_count=self.cpu_count,
            memory_mb=self.memory_mb,
            disk_mb=self.disk_mb,
            network_enabled=False,
            timeout_seconds=self.timeout_seconds,
            pids_limit=self.pids_limit,
        )


@dataclass
class AgentCodeResult:
    """Outcome of one guarded step: either a refusal, or bounded output."""

    stdout: str = ""
    stderr: str = ""
    return_code: int = -1
    timed_out: bool = False
    truncated: bool = False
    elapsed_seconds: float = 0.0
    output_files: list[str] = field(default_factory=list)
    refusal: AgentCodeRefusal | None = None

    @property
    def ok(self) -> bool:
        return self.refusal is None and self.return_code == 0 and not self.timed_out

    @property
    def refused(self) -> bool:
        return self.refusal is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_code": self.return_code,
            "timed_out": self.timed_out,
            "truncated": self.truncated,
            "elapsed_seconds": self.elapsed_seconds,
            "output_files": list(self.output_files),
            "refusal": self.refusal.to_dict() if self.refusal else None,
        }


def _refused(refusal: AgentCodeRefusal) -> AgentCodeResult:
    return AgentCodeResult(refusal=refusal, stderr=refusal.message())


# --------------------------------------------------------------------------- #
# Static policy: what a generated program is allowed to say
# --------------------------------------------------------------------------- #


def _literal_paths(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append(node.value)
    return found


def _path_is_confined(literal: str, workdir: str) -> bool:
    """True when a string literal cannot reference anything outside *workdir*."""
    text = literal.strip().replace("\\", "/")
    if not text:
        return True
    if text.startswith("~"):
        return False
    if len(text) >= 2 and text[1] == ":":  # C:/...
        return False
    if text.startswith("//"):
        return False
    if text.startswith("/"):
        root = workdir.rstrip("/")
        return text == root or text.startswith(root + "/")
    # Relative literals: only ".." escapes are interesting. A bare "..md"
    # style suffix is not a traversal, so require a path segment.
    return ".." not in [segment for segment in text.split("/")]


def preflight_code(
    code: str,
    *,
    policy: SandboxPolicy | None = None,
    language: str = "python",
) -> AgentCodeRefusal | None:
    """The refusal for this program, or ``None`` when it may reach a sandbox.

    Parsing is not execution: :func:`ast.parse` builds a tree and runs no
    user code. Nothing in this function evaluates the program.
    """
    resolved = policy or SandboxPolicy()
    if language not in SUPPORTED_LANGUAGES:
        return _refuse(
            "unsupported_language",
            f"refused: {language!r} is not a supported sandbox language",
            f"رد شد: زبان {language!r} در جعبه‌شن پشتیبانی نمی‌شود",
        )
    if not isinstance(code, str) or not code.strip():
        return _refuse(
            "empty_code",
            "refused: there is no program to run",
            "رد شد: برنامه‌ای برای اجرا وجود ندارد",
        )
    if len(code.encode("utf-8", "ignore")) > _MAX_CODE_BYTES:
        return _refuse(
            "code_too_large",
            "refused: the generated program exceeds the size cap",
            "رد شد: برنامهٔ تولیدشده از سقف اندازه بزرگ‌تر است",
        )
    if "\x00" in code:
        return _refuse(
            "code_not_text",
            "refused: the generated program contains a null byte",
            "رد شد: برنامهٔ تولیدشده شامل بایت تهی است",
        )
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return _refuse(
            "unparsable_code",
            "refused: the generated program does not parse",
            "رد شد: برنامهٔ تولیدشده تجزیه نمی‌شود",
            detail=str(exc.msg),
        )

    allowed = frozenset(resolved.allowed_imports)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in allowed:
                    return _refuse(
                        "denied_import",
                        f"refused: import of {top!r} is not on the sandbox allowlist",
                        f"رد شد: وارد کردن {top!r} در فهرست مجاز جعبه‌شن نیست",
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                return _refuse(
                    "denied_import",
                    "refused: relative imports are not allowed in generated code",
                    "رد شد: واردسازی نسبی در کد تولیدشده مجاز نیست",
                )
            top = (node.module or "").split(".")[0]
            if top not in allowed:
                return _refuse(
                    "denied_import",
                    f"refused: import of {top!r} is not on the sandbox allowlist",
                    f"رد شد: وارد کردن {top!r} در فهرست مجاز جعبه‌شن نیست",
                )
        elif isinstance(node, ast.Call):
            target = node.func
            name = getattr(target, "id", None) or getattr(target, "attr", None)
            if isinstance(name, str) and name in DENIED_CALLS:
                return _refuse(
                    "denied_builtin",
                    f"refused: {name}() turns data back into code and is not allowed",
                    f"رد شد: {name}() داده را دوباره به کد تبدیل می‌کند و مجاز نیست",
                )
        elif isinstance(node, ast.Attribute):
            if node.attr in DENIED_ATTRIBUTES:
                return _refuse(
                    "denied_attribute",
                    f"refused: attribute {node.attr!r} escapes the sandbox object graph",
                    f"رد شد: ویژگی {node.attr!r} از مرز شیء‌های جعبه‌شن می‌گریزد",
                )

    for literal in _literal_paths(tree):
        if not _path_is_confined(literal, resolved.container_workdir):
            return _refuse(
                "path_escape",
                "refused: the program references a path outside the dataset root",
                "رد شد: برنامه به مسیری بیرون از ریشهٔ داده اشاره می‌کند",
                detail=literal[:80],
            )
    return None


def confine_path(root: Path | str, candidate: Path | str) -> Path:
    """Resolve *candidate* inside *root* or raise ``PermissionError``.

    The working directory handed to a sandbox step must be the dataset or
    workspace root itself, or a directory beneath it. Symlinks are
    resolved first, so a planted link cannot widen the mount.
    """
    root_path = Path(root).expanduser().resolve()
    target = Path(candidate).expanduser().resolve()
    try:
        target.relative_to(root_path)
    except ValueError as exc:
        raise PermissionError(
            "sandbox refused: the working directory escapes the dataset root\n"
            "جعبه‌شن رد کرد: پوشهٔ کاری از ریشهٔ داده بیرون می‌رود"
        ) from exc
    return target


def truncate_output(text: str, limit: int) -> tuple[str, bool]:
    """Cap *text* at *limit* bytes, reporting whether anything was dropped."""
    if not isinstance(text, str):
        text = str(text)
    encoded = text.encode("utf-8", "ignore")
    if len(encoded) <= limit:
        return text, False
    clipped = encoded[:limit].decode("utf-8", "ignore")
    return clipped + "\n…[truncated]", True


# --------------------------------------------------------------------------- #
# The guarded run
# --------------------------------------------------------------------------- #


async def _docker_available(sandbox: Any) -> bool:
    checker = getattr(sandbox, "check_available", None)
    if checker is None:
        return False
    try:
        return bool(await checker())
    except (DockerUnavailableError, OSError, RuntimeError):
        return False


async def run_agent_code(
    code: str,
    *,
    workdir: Path | str,
    root: Path | str | None = None,
    policy: SandboxPolicy | None = None,
    sandbox: Any = None,
    language: str = "python",
) -> AgentCodeResult:
    """Run model-generated *code* in a container, or refuse.

    The host never executes the program. When Docker is unreachable this
    returns a refusal — falling back to a host subprocess would trade the
    container boundary for convenience, which is exactly the trade this
    module exists to prevent.
    """
    resolved = policy or SandboxPolicy()
    refusal = preflight_code(code, policy=resolved, language=language)
    if refusal is not None:
        return _refused(refusal)

    try:
        confinement_root = Path(root).expanduser().resolve() if root else None
        target_dir = (
            confine_path(confinement_root, workdir)
            if confinement_root is not None
            else Path(workdir).expanduser().resolve()
        )
    except PermissionError as exc:
        return _refused(
            _refuse(
                "workdir_escape",
                "refused: the working directory escapes the dataset root",
                "رد شد: پوشهٔ کاری از ریشهٔ داده بیرون می‌رود",
                detail=str(exc).splitlines()[0],
            )
        )
    if not target_dir.is_dir():
        return _refused(
            _refuse(
                "workdir_missing",
                "refused: the working directory does not exist",
                "رد شد: پوشهٔ کاری وجود ندارد",
            )
        )

    runner = sandbox if sandbox is not None else DockerSandbox()
    if not await _docker_available(runner):
        return _refused(
            _refuse(
                "docker_unavailable",
                "refused: Docker is unavailable, and Dream never runs model code on the host",
                "رد شد: داکر در دسترس نیست و دریم هرگز کد مدل را روی میزبان اجرا نمی‌کند",
            )
        )

    limits = resolved.resource_limits()
    # The container enforces its own timeout; this outer deadline is the
    # guard for a sandbox that hangs *before* that fires. The grace is
    # proportional so a one-second step is not held open for six.
    deadline = resolved.timeout_seconds + min(5.0, max(1.0, resolved.timeout_seconds * 0.5))
    try:
        raw = await asyncio.wait_for(
            runner.run_code(
                code=code,
                language=language,
                workspace_path=target_dir,
                resource_limits=limits,
                mount_workspace_read_write=False,
                timeout=resolved.timeout_seconds,
            ),
            timeout=deadline,
        )
    except asyncio.TimeoutError:
        return AgentCodeResult(
            timed_out=True,
            return_code=-1,
            stderr=(
                "sandbox step cancelled: the deadline passed\n"
                "گام جعبه‌شن لغو شد: مهلت به پایان رسید"
            ),
        )
    except DockerUnavailableError:
        return _refused(
            _refuse(
                "docker_unavailable",
                "refused: Docker went away mid-step; nothing ran on the host",
                "رد شد: داکر در میانهٔ گام از دسترس خارج شد؛ چیزی روی میزبان اجرا نشد",
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return _refused(
            _refuse(
                "sandbox_error",
                "refused: the sandbox could not complete the step",
                "رد شد: جعبه‌شن نتوانست گام را کامل کند",
                detail=redact_text(str(exc))[:120],
            )
        )

    stdout, cut_out = truncate_output(
        redact_text(getattr(raw, "stdout", "") or ""), resolved.max_output_bytes
    )
    stderr, cut_err = truncate_output(
        redact_text(getattr(raw, "stderr", "") or ""), resolved.max_output_bytes
    )
    return AgentCodeResult(
        stdout=stdout,
        stderr=stderr,
        return_code=int(getattr(raw, "return_code", -1)),
        timed_out=bool(getattr(raw, "timed_out", False)),
        truncated=cut_out or cut_err,
        elapsed_seconds=float(getattr(raw, "elapsed_seconds", 0.0) or 0.0),
        output_files=list(getattr(raw, "output_files", []) or []),
    )
