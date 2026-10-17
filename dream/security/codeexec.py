"""The authoritative execution contract for the Code surface (MASTER-P0).

One module owns the whole request/response shape that the desktop Code view,
the bridge, and every test agree on. It exists because the previous state had
two: an extension handler promised ``{status, result: {stdout, ...}}`` and the
built-in handler returned ``{stdout, stderr, return_code, ...}``, so the UI
rendered a red "error" chip and *displayed no output at all* for a program that
had run correctly.

Three rules, non-negotiable:

* **One contract.** :class:`CodeExecutionRequest` in,
  :class:`CodeExecutionResponse` out. Every field is validated on the backend;
  the frontend is a display layer, never a security control.
* **Container or nothing.** Model-generated and pasted code is untrusted input.
  The only runner wired here is the P-08 container
  (:mod:`dream.docker_sandbox`). When Docker is missing, misconfigured, or dies
  mid-step the answer is ``unavailable`` / ``error`` — never a host ``exec``,
  ``eval``, or subprocess. The AST gates in :mod:`dream.security.agentcode` are
  *additional* defence-in-depth for the agentic callers; a static check is not
  and must never be described as a sandbox.
* **Bound at the boundary.** Code size, timeout, CPU, memory, PID count, output
  bytes, and the writable mount are all clamped here, not in the UI.

What the container actually enforces is recorded per run in
:attr:`CodeExecutionResponse.isolation` and is derived from the argv this module
*requests*, so a reviewer can compare request against evidence instead of
trusting a docstring.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from dream.security.agentcode import SUPPORTED_LANGUAGES
from dream.security.secrets import redact_text

__all__ = [
    "DEFAULT_MAX_CODE_BYTES",
    "DEFAULT_MAX_OUTPUT_BYTES",
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_CODE_BYTES",
    "MAX_OUTPUT_BYTES",
    "MAX_TIMEOUT_SECONDS",
    "MIN_OUTPUT_BYTES",
    "CodeExecutionDenied",
    "CodeExecutionLimits",
    "CodeExecutionRequest",
    "CodeExecutionResponse",
    "CodeExecutionRuntime",
    "CodeExecutionStatus",
    "default_sandbox_root",
    "get_code_execution_runtime",
    "reset_code_execution_runtime",
]

# --------------------------------------------------------------------------- #
# Bounds. Every one of these is enforced on the backend.
# --------------------------------------------------------------------------- #

#: Hard ceiling on the accepted program text (bytes, UTF-8).
DEFAULT_MAX_CODE_BYTES = 200_000
MAX_CODE_BYTES = 1_000_000

#: Default and maximum wall-clock budget for one run.
DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_TIMEOUT_SECONDS = 120.0

#: Default and bounds for the per-stream output budget.
DEFAULT_MAX_OUTPUT_BYTES = 200_000
MIN_OUTPUT_BYTES = 1_000
MAX_OUTPUT_BYTES = 2_000_000

#: Memory / CPU / PID defaults and bounds handed to the container.
DEFAULT_MEMORY_MB = 1024
MIN_MEMORY_MB = 64
MAX_MEMORY_MB = 4096
DEFAULT_CPU_COUNT = 1.0
MIN_CPU_COUNT = 0.1
MAX_CPU_COUNT = 8.0
DEFAULT_PIDS_LIMIT = 64
MIN_PIDS_LIMIT = 1
MAX_PIDS_LIMIT = 512

#: Grace the outer deadline adds on top of the container's own timeout. The
#: container client is the first line; this catches a client that wedges
#: before that fires.
_DEADLINE_GRACE_SECONDS = 5.0

#: The writable locations the container gets. Everything else is read-only.
_CONTAINER_WORKSPACE = "/workspace"
_CONTAINER_TMP = "/tmp"

#: Params the contract deliberately REFUSES rather than silently ignores. Each
#: one used to be a way to widen the boundary through the bridge.
_REFUSED_PARAMS: dict[str, str] = {
    "resource_limits": (
        "resource_limits was removed: network and mount settings cannot be set "
        "per request, so the isolation profile is fixed by the core"
        "\nresource_limits حذف شد: تنظیمات شبکه و ماونت را نمی‌توان در هر درخواست تعیین کرد"
    ),
    "network_enabled": (
        "network access cannot be requested: the sandbox network is always off"
        "\nدسترسی شبکه قابل درخواست نیست: شبکهٔ جعبه‌شن همیشه خاموش است"
    ),
    "workspace_path": (
        "workspace_path was removed: pass `workspace` and it must resolve "
        "inside the sandbox root"
        "\nworkspace_path حذف شد: از `workspace` استفاده کنید و باید داخل ریشهٔ جعبه‌شن باشد"
    ),
    "mount_workspace_read_write": (
        "mount_workspace_read_write was removed: the executable workspace is "
        "the only writable mount and its mode is fixed"
        "\nقابلیت تنظیم حالت ماونت حذف شد: فقط پوشهٔ اجرا نوشتنی است و حالت آن ثابت است"
    ),
    "env_vars": (
        "env_vars was removed: callers cannot inject environment variables "
        "into the code process"
        "\nenv_vars حذف شد: فراخوان‌ها نمی‌توانند متغیر محیطی به فرایند کد تزریق کنند"
    ),
    "docker_host": (
        "docker_host was removed: the daemon socket is core configuration only"
        "\ndocker_host حذف شد: سوکت دیمن فقط تنظیم هسته است"
    ),
}

_ALLOWED_PARAMS = frozenset(
    {
        "code",
        "language",
        "timeout_seconds",
        "memory_mb",
        "cpu_count",
        "pids_limit",
        "max_output_bytes",
        "workspace",
        "execution_id",
    }
)

_EXECUTION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class CodeExecutionStatus(str, Enum):
    """The closed set of terminal states a run can report."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"


class CodeExecutionDenied(ValueError):
    """A request that never reached a runner.

    Carries a :class:`CodeExecutionResponse`-shaped refusal so the bridge can
    answer with the same envelope a normal run uses instead of inventing a
    third shape for errors.
    """

    def __init__(self, refusal: CodeExecutionRefusal) -> None:
        super().__init__(refusal.message())
        self.refusal = refusal


@dataclass(frozen=True, slots=True)
class CodeExecutionRefusal:
    """A fail-closed reason, named in English and Persian."""

    code: str
    reason_en: str
    reason_fa: str
    detail: str = ""

    def message(self) -> str:
        """Two-line bilingual text safe to show to the user verbatim."""
        tail = f" ({self.detail})" if self.detail else ""
        return f"{self.reason_en}{tail}\n{self.reason_fa}{tail}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "reason_en": self.reason_en,
            "reason_fa": self.reason_fa,
            "detail": self.detail,
        }


# --------------------------------------------------------------------------- #
# Bounds object
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class CodeExecutionLimits:
    """Validated resource bounds for one run.

    ``network_enabled`` exists only so the value can be *asserted* to be False;
    there is no code path that sets it True, and constructing an instance with
    True raises. This mirrors :class:`dream.security.agentcode.SandboxPolicy`
    on purpose: one rule, stated once, in two places that must agree.
    """

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    memory_mb: int = DEFAULT_MEMORY_MB
    cpu_count: float = DEFAULT_CPU_COUNT
    pids_limit: int = DEFAULT_PIDS_LIMIT
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES
    network_enabled: bool = False

    def __post_init__(self) -> None:
        if self.network_enabled:
            raise ValueError("code execution: network can never be enabled")
        if not 0 < self.timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise ValueError(f"timeout_seconds must be in (0, {MAX_TIMEOUT_SECONDS}]")
        if not MIN_MEMORY_MB <= self.memory_mb <= MAX_MEMORY_MB:
            raise ValueError(f"memory_mb must be in [{MIN_MEMORY_MB}, {MAX_MEMORY_MB}]")
        if not MIN_CPU_COUNT <= self.cpu_count <= MAX_CPU_COUNT:
            raise ValueError(f"cpu_count must be in [{MIN_CPU_COUNT}, {MAX_CPU_COUNT}]")
        if not MIN_PIDS_LIMIT <= self.pids_limit <= MAX_PIDS_LIMIT:
            raise ValueError(f"pids_limit must be in [{MIN_PIDS_LIMIT}, {MAX_PIDS_LIMIT}]")
        if not MIN_OUTPUT_BYTES <= self.max_output_bytes <= MAX_OUTPUT_BYTES:
            raise ValueError(
                f"max_output_bytes must be in [{MIN_OUTPUT_BYTES}, {MAX_OUTPUT_BYTES}]"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeout_seconds": self.timeout_seconds,
            "memory_mb": self.memory_mb,
            "cpu_count": self.cpu_count,
            "pids_limit": self.pids_limit,
            "max_output_bytes": self.max_output_bytes,
            "network_enabled": False,
        }


def _deny(code: str, detail: str = "") -> CodeExecutionDenied:
    reasons = {
        "code_missing": (
            "denied: nothing to run",
            "رد شد: برنامه‌ای برای اجرا وجود ندارد",
        ),
        "code_not_text": (
            "denied: the program must be a string",
            "رد شد: برنامه باید متن باشد",
        ),
        "code_empty": (
            "denied: the program is empty",
            "رد شد: برنامه خالی است",
        ),
        "code_too_large": (
            "denied: the program exceeds the size cap",
            "رد شد: برنامه از سقف اندازه بزرگ‌تر است",
        ),
        "unsupported_language": (
            "denied: unsupported sandbox language",
            "رد شد: زبان جعبه‌شن پشتیبانی نمی‌شود",
        ),
        "unknown_field": (
            "denied: the request carries a field this contract does not accept",
            "رد شد: درخواست فیلدی دارد که این قرارداد نمی‌پذیرد",
        ),
        "removed_field": (
            "denied: this field was removed because it widened the sandbox",
            "رد شد: این فیلد چون مرز جعبه‌شن را باز می‌کرد حذف شده است",
        ),
        "invalid_limit": (
            "denied: a resource limit is outside its allowed range",
            "رد شد: یک محدودیت منابع بیرون از بازهٔ مجاز است",
        ),
        "workspace_outside_root": (
            "denied: the workspace is outside the sandbox root",
            "رد شد: پوشهٔ کاری بیرون از ریشهٔ جعبه‌شن است",
        ),
        "workspace_not_directory": (
            "denied: the workspace is not a directory",
            "رد شد: پوشهٔ کاری یک پوشه نیست",
        ),
        "invalid_execution_id": (
            "denied: execution_id must match [A-Za-z0-9._-]{1,64}",
            "رد شد: شناسهٔ اجرا باید با الگوی مجاز بخواند",
        ),
    }
    reason_en, reason_fa = reasons.get(code, ("denied", "رد شد"))
    return CodeExecutionDenied(CodeExecutionRefusal(code, reason_en, reason_fa, detail))


def default_sandbox_root() -> Path:
    """The only host directory tree the sandbox may mount.

    ``DREAM_SANDBOX_ROOT`` overrides it; the default lives under the app data
    directory so a run can never be pointed at the user's home, a project, an
    SSH key directory, or the Docker socket by request.
    """
    override = os.environ.get("DREAM_SANDBOX_ROOT", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(os.environ.get("DREAM_DATA_DIR", str(Path.home() / ".dream"))) / "sandbox"


def _as_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _deny("invalid_limit", f"{field_name} must be a number")
    return float(value)


@dataclass(frozen=True, slots=True)
class CodeExecutionRequest:
    """A validated, canonical run request. Constructed only via :meth:`from_params`."""

    code: str
    language: str
    limits: CodeExecutionLimits
    workspace: Path
    #: True when the caller named the workspace (and it was confined) rather
    #: than the runtime minting a fresh per-run directory.
    workspace_explicit: bool
    execution_id: str
    runtime_root: Path

    @classmethod
    def from_params(
        cls,
        params: Mapping[str, Any] | None,
        *,
        sandbox_root: Path | str | None = None,
        execution_id: str | None = None,
    ) -> CodeExecutionRequest:
        """Validate *params* into a request, or raise :class:`CodeExecutionDenied`."""
        raw: Mapping[str, Any] = params or {}
        if not isinstance(raw, Mapping):
            raise _deny("code_not_text", "params must be an object")

        for field_name in raw:
            if not isinstance(field_name, str):
                raise _deny("unknown_field", "field names must be strings")
            if field_name in _REFUSED_PARAMS:
                raise _deny("removed_field", f"{field_name}: {_REFUSED_PARAMS[field_name]}")
            if field_name not in _ALLOWED_PARAMS:
                raise _deny("unknown_field", f"unexpected field {field_name!r}")

        code = raw.get("code")
        if code is None:
            raise _deny("code_missing")
        if not isinstance(code, str):
            raise _deny("code_not_text", f"got {type(code).__name__}")
        if not code.strip():
            raise _deny("code_empty")
        if len(code.encode("utf-8", "surrogatepass")) > MAX_CODE_BYTES:
            raise _deny("code_too_large", f"limit is {MAX_CODE_BYTES} bytes")

        language = raw.get("language", "python")
        if not isinstance(language, str) or language.strip().lower() not in SUPPORTED_LANGUAGES:
            raise _deny("unsupported_language", f"got {language!r}")

        limits = cls._limits_from(raw)
        root = Path(sandbox_root).expanduser() if sandbox_root else default_sandbox_root()
        root = root.resolve()

        requested = raw.get("workspace")
        if requested is None or (isinstance(requested, str) and not requested.strip()):
            workspace = root / "runs" / "pending"
            workspace_explicit = False
        else:
            if not isinstance(requested, str):
                raise _deny("workspace_outside_root", "workspace must be a string")
            workspace = _canonical(requested)
            if not _is_relative_to(workspace, root):
                raise _deny(
                    "workspace_outside_root", f"{requested!r} is not under the sandbox root"
                )
            if not workspace.is_dir():
                raise _deny("workspace_not_directory", str(workspace))
            workspace_explicit = True

        ident = execution_id
        if ident is None:
            ident = raw.get("execution_id")
        if ident is None:
            ident = f"exe-{uuid.uuid4().hex[:12]}"
        if not isinstance(ident, str) or not _EXECUTION_ID_RE.match(ident):
            raise _deny("invalid_execution_id", repr(ident)[:80])

        return cls(
            code=code,
            language="python",
            limits=limits,
            workspace=workspace,
            workspace_explicit=workspace_explicit,
            execution_id=ident,
            runtime_root=root,
        )

    @staticmethod
    def _limits_from(raw: Mapping[str, Any]) -> CodeExecutionLimits:
        timeout = _as_number(raw.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS), "timeout_seconds")
        if not 0 < timeout <= MAX_TIMEOUT_SECONDS:
            raise _deny(
                "invalid_limit", f"timeout_seconds must be in (0, {MAX_TIMEOUT_SECONDS}]"
            )

        def _int_field(name: str, default: int) -> int:
            value = raw.get(name, default)
            if isinstance(value, bool) or not isinstance(value, int):
                raise _deny("invalid_limit", f"{name} must be an integer")
            return value

        memory_mb = _int_field("memory_mb", DEFAULT_MEMORY_MB)
        if not MIN_MEMORY_MB <= memory_mb <= MAX_MEMORY_MB:
            raise _deny("invalid_limit", f"memory_mb must be in [{MIN_MEMORY_MB}, {MAX_MEMORY_MB}]")
        pids_limit = _int_field("pids_limit", DEFAULT_PIDS_LIMIT)
        if not MIN_PIDS_LIMIT <= pids_limit <= MAX_PIDS_LIMIT:
            raise _deny(
                "invalid_limit", f"pids_limit must be in [{MIN_PIDS_LIMIT}, {MAX_PIDS_LIMIT}]"
            )
        max_output = _int_field("max_output_bytes", DEFAULT_MAX_OUTPUT_BYTES)
        if not MIN_OUTPUT_BYTES <= max_output <= MAX_OUTPUT_BYTES:
            raise _deny(
                "invalid_limit",
                f"max_output_bytes must be in [{MIN_OUTPUT_BYTES}, {MAX_OUTPUT_BYTES}]",
            )
        cpu_count = _as_number(raw.get("cpu_count", DEFAULT_CPU_COUNT), "cpu_count")
        if not MIN_CPU_COUNT <= cpu_count <= MAX_CPU_COUNT:
            raise _deny("invalid_limit", f"cpu_count must be in [{MIN_CPU_COUNT}, {MAX_CPU_COUNT}]")

        return CodeExecutionLimits(
            timeout_seconds=timeout,
            memory_mb=memory_mb,
            cpu_count=cpu_count,
            pids_limit=pids_limit,
            max_output_bytes=max_output,
            network_enabled=False,
        )

    def to_dict(self) -> dict[str, Any]:
        """The canonical, secret-free view of the request."""
        return {
            "execution_id": self.execution_id,
            "language": self.language,
            "code_bytes": len(self.code.encode("utf-8", "surrogatepass")),
            "workspace": str(self.workspace),
            "workspace_explicit": self.workspace_explicit,
            "limits": self.limits.to_dict(),
        }


def _canonical(raw: str) -> Path:
    """Resolve *raw* with symlinks followed, without requiring it to exist."""
    candidate = Path(raw).expanduser()
    try:
        return candidate.resolve(strict=False)
    except OSError:  # pragma: no cover - unreadable path component
        return Path(os.path.abspath(str(candidate)))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------- #
# Response
# --------------------------------------------------------------------------- #


@dataclass
class CodeExecutionResponse:
    """The single response every caller serialises."""

    status: CodeExecutionStatus
    execution_id: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    duration_ms: float = 0.0
    timed_out: bool = False
    truncated: bool = False
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    error: CodeExecutionRefusal | None = None
    isolation: dict[str, Any] = field(default_factory=dict)
    limits: dict[str, Any] = field(default_factory=dict)
    stdout_path: str = ""
    stderr_path: str = ""

    @property
    def ok(self) -> bool:
        return self.status is CodeExecutionStatus.SUCCESS

    @classmethod
    def refused(
        cls, refusal: CodeExecutionRefusal, *, execution_id: str = ""
    ) -> CodeExecutionResponse:
        """A denial envelope, so rejected input never gets a second shape."""
        return cls(
            status=CodeExecutionStatus.DENIED,
            execution_id=execution_id,
            exit_code=-1,
            timed_out=False,
            error=refusal,
        )

    def to_dict(self) -> dict[str, Any]:
        """The wire payload.

        ``status`` is repeated at the top level *and* inside ``result`` on
        purpose: the top level is the contract's summary the UI switches on,
        ``result`` is the detail panel. Both are always present, always the
        same value, so a client can never read one and miss the other.
        """
        return {
            "status": self.status.value,
            "execution_id": self.execution_id,
            "result": {
                "status": self.status.value,
                "execution_id": self.execution_id,
                "stdout": self.stdout,
                "stderr": self.stderr,
                "stdout_path": self.stdout_path,
                "stderr_path": self.stderr_path,
                "exit_code": self.exit_code,
                "duration_ms": round(self.duration_ms, 2),
                "timed_out": self.timed_out,
                "truncated": self.truncated,
                "artifacts": list(self.artifacts),
                "error": self.error.to_dict() if self.error else None,
                "error_message": self.error.message() if self.error else "",
                # Container runs are stateless by design; the field stays in
                # the contract because the UI renders it, and an empty list is
                # the honest answer rather than a stale namespace.
                "variables_updated": [],
                "isolation": dict(self.isolation),
                "limits": dict(self.limits),
            },
        }


def _refusal(code: str, reason_en: str, reason_fa: str, detail: str = "") -> CodeExecutionRefusal:
    return CodeExecutionRefusal(
        code=code, reason_en=reason_en, reason_fa=reason_fa, detail=redact_text(detail)[:200]
    )


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8", "surrogatepass")
    if len(encoded) <= limit:
        return text, False
    clipped = encoded[:limit].decode("utf-8", "ignore")
    return clipped + "\n… [truncated by Dream: output exceeded the byte budget]", True


# --------------------------------------------------------------------------- #
# Isolation descriptor
# --------------------------------------------------------------------------- #


def isolation_descriptor(limits: CodeExecutionLimits, *, user: str | None) -> dict[str, Any]:
    """What this run asks the container for, stated as facts.

    Kept next to the runner so the tests assert the *requested* argv rather
    than a hand-written table that can drift.
    """
    return {
        "backend": "docker",
        "network": "none",
        "rootfs": "read-only",
        "mounts": [
            {"container_path": _CONTAINER_WORKSPACE, "mode": "rw", "source": "per-run workspace"},
            {"container_path": _CONTAINER_TMP, "mode": "rw", "source": "tmpfs"},
        ],
        "capabilities": "drop-all",
        "no_new_privileges": True,
        "privileged": False,
        "user": user or "image-default",
        "process_limit": limits.pids_limit,
        "memory_mb": limits.memory_mb,
        "cpu_count": limits.cpu_count,
        "timeout_seconds": limits.timeout_seconds,
        "max_output_bytes": limits.max_output_bytes,
        "env_policy": "explicit-minimal (no host environment, no credentials)",
        "docker_socket": "not mounted",
    }


# --------------------------------------------------------------------------- #
# Runtime
# --------------------------------------------------------------------------- #


class CodeExecutionRuntime:
    """Owns the sandbox root, the run history, and the container runner.

    The runner is injectable so tests can prove the fail-closed behaviour with
    a fake and prove the argv with a fake ``docker`` binary. Both are honest:
    the fake proves policy, never isolation.
    """

    def __init__(
        self,
        sandbox: Any = None,
        *,
        root: Path | str | None = None,
        sandbox_factory: Any = None,
    ) -> None:
        self._sandbox = sandbox
        self._sandbox_factory = sandbox_factory
        self.root = Path(root).expanduser().resolve() if root else default_sandbox_root().resolve()
        self._history: list[CodeExecutionResponse] = []
        self._live: dict[str, dict[str, Any]] = {}
        self._cancelled: set[str] = set()
        self._lock = asyncio.Lock()

    # -- runner plumbing --------------------------------------------------- #

    def _resolve_runner(self) -> Any:
        """The container runner, or ``None`` when this build cannot isolate."""
        if self._sandbox is not None:
            return self._sandbox
        if self._sandbox_factory is not None:
            self._sandbox = self._sandbox_factory()
            return self._sandbox
        try:  # pragma: no cover - exercised through DockerSandbox directly
            from dream.docker_sandbox import DockerSandbox
        except ImportError:  # pragma: no cover
            return None
        self._sandbox = DockerSandbox()
        return self._sandbox

    async def _runner_available(self, runner: Any) -> bool:
        checker = getattr(runner, "check_available", None)
        if checker is None:
            return False
        try:
            return bool(await checker())
        except Exception:  # noqa: BLE001 - any probe failure means "not isolated"
            return False

    # -- workspaces -------------------------------------------------------- #

    def ensure_root(self) -> Path:
        """Create the sandbox root with owner-only permissions."""
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:  # pragma: no cover - exotic filesystems / Windows
            pass
        return self.root

    def workspace_for(self, request: CodeExecutionRequest) -> Path:
        """The directory this run may write to, and the only one it may see."""
        if request.workspace_explicit:
            workspace = request.workspace
        else:
            workspace = self.root / "runs" / request.execution_id
        workspace.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(workspace, 0o700)
        except OSError:  # pragma: no cover
            pass
        # Re-check after mkdir: a symlinked parent could have moved it.
        resolved = workspace.resolve()
        if not _is_relative_to(resolved, self.root):
            raise _deny("workspace_outside_root", str(resolved))
        return resolved

    # -- status / artifacts / reset --------------------------------------- #

    def status(self) -> dict[str, Any]:
        """Honest snapshot of the real runner, not of a namespace."""
        last = self._history[-1] if self._history else None
        return {
            "status": "healthy",
            "backend": "docker",
            "available": bool(self._sandbox is not None),
            "sandbox_root": str(self.root),
            "total_executions": len(self._history),
            "total_artifacts": sum(len(r.artifacts) for r in self._history),
            "variables_count": 0,
            "statefulness": "none (each run is a fresh container)",
            "network": "disabled",
            "last_execution_status": last.status.value if last else "ready",
            "last_execution_id": last.execution_id if last else "",
            "live_executions": sorted(self._live),
            "limits": CodeExecutionLimits().to_dict(),
        }

    def list_artifacts(self) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        for response in self._history:
            artifacts.extend(response.artifacts)
        return artifacts

    def reset(self) -> dict[str, Any]:
        """Drop history and delete only directories under the sandbox root."""
        removed = 0
        runs = self.root / "runs"
        if runs.is_dir():
            for child in sorted(runs.iterdir()):
                resolved = child.resolve()
                if not _is_relative_to(resolved, self.root) or resolved == self.root:
                    continue
                try:
                    if child.is_dir() and not child.is_symlink():
                        shutil.rmtree(child, ignore_errors=True)
                    else:
                        child.unlink(missing_ok=True)
                    removed += 1
                except OSError:  # pragma: no cover - permissions / locking
                    continue
        self._history.clear()
        return {
            "status": "reset",
            "message": (
                "sandbox runs and artifacts cleared; the container filesystem is "
                "recreated on every execution so there is no session state to reset"
                "\nاجراها و آرتیفکت‌های جعبه‌شن پاک شد؛ فایل‌سیستم کانتینر در هر اجرا از "
                "نو ساخته می‌شود"
            ),
            "removed": removed,
            "sandbox_root": str(self.root),
        }

    # -- cancellation ------------------------------------------------------ #

    async def cancel(self, execution_id: str) -> dict[str, Any]:
        """Terminate the whole container tree for a live run.

        ``docker rm -f`` is issued against the recorded container name, so the
        container dies even if the ``docker run`` client is still attached.
        """
        entry = self._live.get(execution_id)
        if entry is None:
            return {
                "status": "not_running",
                "execution_id": execution_id,
                "message": "no live execution with that id",
            }
        self._cancelled.add(execution_id)
        killed = await self._kill_container(entry.get("runner"), entry.get("container_name"))
        return {
            "status": "cancelled",
            "execution_id": execution_id,
            "container_killed": killed,
            "message": "execution cancelled and its container terminated",
        }

    async def _kill_container(self, runner: Any, container_name: str | None) -> bool:
        if not container_name or runner is None:
            return False
        force_remove = getattr(runner, "force_remove_container", None)
        if force_remove is None:
            return False
        try:
            return bool(await force_remove(container_name))
        except Exception:  # noqa: BLE001 - teardown must never mask the result
            return False

    # -- the run ----------------------------------------------------------- #

    async def run(self, request: CodeExecutionRequest) -> CodeExecutionResponse:
        """Execute *request*, or fail closed. Never falls back to the host."""
        started = time.monotonic()
        limits_dict = request.limits.to_dict()
        # The profile this run asks for. Computed before any early return so a
        # refusal carries it too: the client must be able to show what the
        # sandbox *is* even when nothing ran.
        isolation = isolation_descriptor(request.limits, user=self._container_user())

        runner = self._resolve_runner()
        if runner is None:
            return self._fail(
                request,
                CodeExecutionStatus.UNAVAILABLE,
                _refusal(
                    "runner_missing",
                    "unavailable: this build has no isolated runner, and Dream never "
                    "runs code on the host",
                    "در دسترس نیست: این نسخه اجراکنندهٔ ایزوله ندارد و دریم هرگز کد را "
                    "روی میزبان اجرا نمی‌کند",
                ),
                limits_dict,
                started,
                isolation=isolation,
            )

        if not await self._runner_available(runner):
            return self._fail(
                request,
                CodeExecutionStatus.UNAVAILABLE,
                _refusal(
                    "docker_unavailable",
                    "unavailable: the container runtime is not reachable, and Dream "
                    "never runs code on the host",
                    "در دسترس نیست: رانتایم کانتینر قابل دسترس نیست و دریم هرگز کد را "
                    "روی میزبان اجرا نمی‌کند",
                ),
                limits_dict,
                started,
                isolation=isolation,
            )

        try:
            workspace = self.workspace_for(request)
        except CodeExecutionDenied as denied:
            return self._fail(
                request,
                CodeExecutionStatus.DENIED,
                denied.refusal,
                limits_dict,
                started,
                isolation=isolation,
            )
        except OSError as exc:
            return self._fail(
                request,
                CodeExecutionStatus.ERROR,
                _refusal(
                    "workspace_error",
                    "error: the sandbox workspace could not be prepared",
                    "خطا: پوشهٔ کاری جعبه‌شن آماده نشد",
                    str(exc),
                ),
                limits_dict,
                started,
                isolation=isolation,
            )

        container_name = f"dream-code-{request.execution_id}"[:63]

        async with self._lock:
            self._live[request.execution_id] = {
                "runner": runner,
                "container_name": container_name,
                "started": started,
            }

        try:
            result = await asyncio.wait_for(
                self._invoke_runner(runner, request, workspace, container_name),
                timeout=request.limits.timeout_seconds + _DEADLINE_GRACE_SECONDS,
            )
        except asyncio.TimeoutError:
            await self._kill_container(runner, container_name)
            return self._finish(
                request,
                self._fail(
                    request,
                    CodeExecutionStatus.TIMEOUT,
                    _refusal(
                        "timeout",
                        f"timeout: the run exceeded {request.limits.timeout_seconds:g}s "
                        "and its container was terminated",
                        f"مهلت تمام شد: اجرا از {request.limits.timeout_seconds:g} ثانیه گذشت و "
                        "کانتینر آن خاتمه یافت",
                    ),
                    limits_dict,
                    started,
                ),
                isolation=isolation,
            )
        except asyncio.CancelledError:
            # The bridge is going away or the caller cancelled us: the container
            # must not outlive the request.
            await self._kill_container(runner, container_name)
            self._cancelled.add(request.execution_id)
            response = self._fail(
                request,
                CodeExecutionStatus.CANCELLED,
                _refusal(
                    "cancelled",
                    "cancelled: the run was cancelled and its container was terminated",
                    "لغو شد: اجرا لغو و کانتینر آن خاتمه یافت",
                ),
                limits_dict,
                started,
            )
            self._finish(request, response, isolation=isolation)
            raise
        except Exception as exc:  # noqa: BLE001 - any runner failure fails closed
            await self._kill_container(runner, container_name)
            return self._finish(
                request,
                self._fail(
                    request,
                    CodeExecutionStatus.ERROR,
                    _refusal(
                        "runner_failure",
                        "error: the sandbox runner failed before reporting a result",
                        "خطا: اجراکنندهٔ جعبه‌شن پیش از گزارش نتیجه شکست خورد",
                        f"{type(exc).__name__}: {exc}",
                    ),
                    limits_dict,
                    started,
                ),
                isolation=isolation,
            )

        return self._finish(
            request,
            self._from_runner(result, request, limits_dict, started),
            isolation=isolation,
        )

    async def _invoke_runner(
        self,
        runner: Any,
        request: CodeExecutionRequest,
        workspace: Path,
        container_name: str,
    ) -> Any:
        from dream.docker_sandbox import ResourceLimits

        limits = ResourceLimits(
            cpu_count=request.limits.cpu_count,
            memory_mb=request.limits.memory_mb,
            disk_mb=request.limits.memory_mb,
            network_enabled=False,
            timeout_seconds=int(request.limits.timeout_seconds),
            pids_limit=request.limits.pids_limit,
        )
        return await runner.run_code(
            code=request.code,
            language=request.language,
            workspace_path=workspace,
            resource_limits=limits,
            # The per-run workspace is the ONE writable host location. Every
            # other path in the container is read-only.
            mount_workspace_read_write=True,
            timeout=int(request.limits.timeout_seconds),
            container_name=container_name,
        )

    def _container_user(self) -> str | None:
        """The uid:gid the container process runs as.

        Root is never acceptable. When the host app is unprivileged we reuse its
        uid so the bind-mounted workspace stays writable; when it is root we drop
        to ``nobody``. On platforms without ``os.getuid`` (Windows, where Docker
        Desktop owns the mapping) we return ``None`` and the image default is
        recorded honestly in the isolation descriptor instead of being claimed.
        """
        getuid = getattr(os, "getuid", None)
        getgid = getattr(os, "getgid", None)
        if getuid is None or getgid is None:  # pragma: no cover - Windows
            return None
        uid = getuid()
        gid = getgid()
        if uid == 0:
            return "65534:65534"
        return f"{uid}:{gid}"

    def _from_runner(
        self,
        result: Any,
        request: CodeExecutionRequest,
        limits_dict: dict[str, Any],
        started: float,
    ) -> CodeExecutionResponse:
        stdout, cut_out = _truncate(
            redact_text(str(getattr(result, "stdout", "") or "")), request.limits.max_output_bytes
        )
        stderr, cut_err = _truncate(
            redact_text(str(getattr(result, "stderr", "") or "")), request.limits.max_output_bytes
        )
        timed_out = bool(getattr(result, "timed_out", False))
        cancelled = bool(getattr(result, "cancelled", False)) or (
            request.execution_id in self._cancelled
        )
        exit_code = int(getattr(result, "return_code", -1))

        if cancelled:
            status = CodeExecutionStatus.CANCELLED
            error = _refusal(
                "cancelled",
                "cancelled: the run was cancelled and its container was terminated",
                "لغو شد: اجرا لغو و کانتینر آن خاتمه یافت",
            )
        elif timed_out:
            status = CodeExecutionStatus.TIMEOUT
            error = _refusal(
                "timeout",
                f"timeout: the run exceeded {request.limits.timeout_seconds:g}s and its "
                "container was terminated",
                f"مهلت تمام شد: اجرا از {request.limits.timeout_seconds:g} ثانیه گذشت و کانتینر "
                "آن خاتمه یافت",
            )
        elif exit_code == 0:
            status = CodeExecutionStatus.SUCCESS
            error = None
        else:
            status = CodeExecutionStatus.ERROR
            error = _refusal(
                "nonzero_exit",
                f"error: the program exited with status {exit_code}",
                f"خطا: برنامه با کد {exit_code} پایان یافت",
            )

        response = CodeExecutionResponse(
            status=status,
            execution_id=request.execution_id,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=(time.monotonic() - started) * 1000,
            timed_out=timed_out,
            truncated=cut_out or cut_err,
            artifacts=self._artifacts_for(request),
            error=error,
            limits=limits_dict,
        )
        if response.truncated:
            response.stdout_path, response.stderr_path = self._persist_overflow(
                request, stdout, stderr
            )
        return response

    def _artifacts_for(self, request: CodeExecutionRequest) -> list[dict[str, Any]]:
        """Enumerate what the run wrote, inside its own workspace only."""
        try:
            workspace = self.workspace_for(request)
        except (CodeExecutionDenied, OSError):
            return []
        artifacts: list[dict[str, Any]] = []
        for path in sorted(workspace.iterdir()):
            # `script.py` is Dream's own payload, not a user artifact.
            if path.name in {"script.py", "_script.py"}:
                continue
            try:
                resolved = path.resolve()
                if not _is_relative_to(resolved, self.root) or path.is_symlink():
                    continue
                if not path.is_file():
                    continue
                stat = path.stat()
            except OSError:
                continue
            artifacts.append(
                {
                    "name": path.name,
                    "file_path": str(resolved),
                    "mime_type": _guess_mime(path.suffix),
                    "size_bytes": stat.st_size,
                }
            )
        return artifacts

    def _persist_overflow(
        self, request: CodeExecutionRequest, stdout: str, stderr: str
    ) -> tuple[str, str]:
        """Keep the full stream for the operator; hand back only a safe reference."""
        try:
            directory = self.workspace_for(request)
        except (CodeExecutionDenied, OSError):
            return "", ""
        written: list[str] = []
        for name, text in (("stdout.txt", stdout), ("stderr.txt", stderr)):
            target = directory / name
            try:
                target.write_text(text, encoding="utf-8", errors="replace")
                written.append(str(target.resolve()))
            except OSError:  # pragma: no cover
                written.append("")
        return written[0], written[1]

    def _fail(
        self,
        request: CodeExecutionRequest,
        status: CodeExecutionStatus,
        refusal: CodeExecutionRefusal,
        limits_dict: dict[str, Any],
        started: float,
        *,
        isolation: dict[str, Any] | None = None,
    ) -> CodeExecutionResponse:
        return CodeExecutionResponse(
            status=status,
            execution_id=request.execution_id,
            exit_code=-1,
            duration_ms=(time.monotonic() - started) * 1000,
            timed_out=status is CodeExecutionStatus.TIMEOUT,
            error=refusal,
            limits=limits_dict,
            isolation=dict(isolation or {}),
        )

    def _finish(
        self,
        request: CodeExecutionRequest,
        response: CodeExecutionResponse,
        *,
        isolation: dict[str, Any] | None = None,
    ) -> CodeExecutionResponse:
        if isolation is not None:
            response.isolation = isolation
        self._live.pop(request.execution_id, None)
        self._cancelled.discard(request.execution_id)
        self._history.append(response)
        return response


_MIME_BY_SUFFIX: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".json": "application/json",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _guess_mime(suffix: str) -> str:
    return _MIME_BY_SUFFIX.get(suffix.lower(), "application/octet-stream")


# --------------------------------------------------------------------------- #
# Singleton accessor (the bridge reads this; tests reset it)
# --------------------------------------------------------------------------- #

_RUNTIME: CodeExecutionRuntime | None = None


def get_code_execution_runtime() -> CodeExecutionRuntime:
    """Process-wide runtime. Injectable: reset it in tests."""
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = CodeExecutionRuntime()
    return _RUNTIME


def reset_code_execution_runtime(runtime: CodeExecutionRuntime | None = None) -> None:
    """Replace (or clear) the singleton — the seam the tests use."""
    global _RUNTIME
    _RUNTIME = runtime
