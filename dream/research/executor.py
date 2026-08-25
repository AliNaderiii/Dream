"""Sandboxed CodeAct execution with a static gate and a no-hang watchdog.

The host process never runs model-authored code. A snippet travels through
three gates before it produces a number:

1. :func:`validate_code` — an AST allowlist. Imports outside a tiny science
   allowlist, ``exec``/``eval``/``compile``, ``__import__``, attribute access
   to dunder internals, subprocess/socket/shutil use, and absolute or
   traversing path literals are refused *before* anything is written to disk.
2. the executor — Docker by default (network off, cap-drop, seccomp, memory
   and CPU bounds via :mod:`dream.docker_sandbox`), falling back to the
   guarded ``-I`` subprocess of :mod:`dream.skills.data_science` with a loud
   warning when Docker is unavailable.
3. the watchdog — a hard wall-clock deadline enforced on a worker thread, so
   a wedged container or a stuck subprocess reports a controlled timeout
   instead of hanging the session. Output is truncated to a fixed budget.

Parameters reach the snippet through ``_params.json``; they are never
interpolated into source. Results come back through ``_result.json``.
"""

from __future__ import annotations

import ast
import concurrent.futures
import json
import logging
import os
import re
import textwrap
import time
from pathlib import Path
from typing import Any

from dream.research.errors import ResearchSecurityError, ResearchTimeout
from dream.research.schemas import Observation

logger = logging.getLogger("dream.research.executor")

__all__ = [
    "MAX_CODE_CHARS",
    "MAX_OUTPUT_CHARS",
    "CodeActExecutor",
    "validate_code",
]

MAX_CODE_CHARS = 8000
MAX_OUTPUT_CHARS = 20000

#: Modules a research snippet may import. Everything else is refused.
_ALLOWED_IMPORTS = frozenset(
    {"math", "statistics", "json", "re", "datetime", "itertools", "collections",
     "numpy", "pandas", "np", "pd"}
)

_FORBIDDEN_NAMES = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "globals",
        "locals",
        "vars",
        "getattr",
        "setattr",
        "delattr",
        "input",
        "breakpoint",
        "memoryview",
    }
)

_FORBIDDEN_MODULES = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "shutil",
        "socket",
        "requests",
        "urllib",
        "urllib3",
        "http",
        "ftplib",
        "pathlib",
        "importlib",
        "pickle",
        "marshal",
        "ctypes",
        "multiprocessing",
        "threading",
        "asyncio",
        "signal",
        "tempfile",
        "webbrowser",
        "smtplib",
        "telnetlib",
        "paramiko",
        "sqlite3",
    }
)

_PATH_LITERAL = re.compile(r"(?:\.\./)|(?:^/)|(?:^[A-Za-z]:\\)|(?:~/)")


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def validate_code(code: Any) -> str:
    """Refuse anything a research snippet has no business doing.

    Returns the accepted source. Raises :class:`ResearchSecurityError` with a
    short, user-safe reason otherwise — the reason is shown to the model so it
    can self-correct on the next iteration.
    """
    if not isinstance(code, str) or not code.strip():
        raise ResearchSecurityError("generated code was empty")
    if len(code) > MAX_CODE_CHARS:
        raise ResearchSecurityError(f"generated code exceeds {MAX_CODE_CHARS} characters")
    if "\x00" in code:
        raise ResearchSecurityError("generated code contains a NUL byte")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ResearchSecurityError(f"generated code does not parse: {exc.msg}") from None

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _FORBIDDEN_MODULES or root not in _ALLOWED_IMPORTS:
                    raise ResearchSecurityError(f"import of {alias.name!r} is not allowed")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level or root in _FORBIDDEN_MODULES or root not in _ALLOWED_IMPORTS:
                raise ResearchSecurityError(f"import from {node.module!r} is not allowed")
        elif isinstance(node, ast.Name):
            if node.id in _FORBIDDEN_NAMES:
                raise ResearchSecurityError(f"use of {node.id!r} is not allowed")
        elif isinstance(node, ast.Attribute):
            if _is_dunder(node.attr):
                raise ResearchSecurityError(f"attribute {node.attr!r} is not allowed")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                first = node.args[0] if node.args else None
                mode = node.args[1] if len(node.args) > 1 else None
                literal = (
                    first.value if isinstance(first, ast.Constant) and
                    isinstance(first.value, str) else None
                )
                if literal is None or _PATH_LITERAL.search(literal):
                    raise ResearchSecurityError(
                        "open() is limited to relative paths inside the workspace"
                    )
                if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
                    if any(flag in mode.value for flag in ("w", "a", "x", "+")):
                        raise ResearchSecurityError("writing files from a snippet is not allowed")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _PATH_LITERAL.search(node.value):
                raise ResearchSecurityError("absolute or traversing paths are not allowed")
    return code


_EMIT_GUARD = textwrap.dedent(
    """
    # The snippet's contract: `df` is the active table, `emit(obj)` returns
    # a JSON-safe dict to the host. A snippet that emits nothing still
    # produces a (empty) result file, so the host never blocks on a missing
    # artifact.
    df = active_df()
    _emitted = {}

    def emit(obj):
        global _emitted
        _emitted = _clean(obj) if isinstance(obj, dict) else {"value": _clean(obj)}
    """
).strip()

_EMIT_FLUSH = textwrap.dedent(
    """
    with open("_result.json", "w", encoding="utf-8") as _fh:
        json.dump({"emitted": _emitted}, _fh, ensure_ascii=False, default=str)
    """
).strip()


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [truncated {len(text) - limit} chars]"


class CodeActExecutor:
    """Run one validated snippet against one dataset, under a hard deadline."""

    def __init__(
        self,
        runtime: Any,
        *,
        default_timeout: float = 120.0,
        memory_mb: int = 1024,
    ) -> None:
        self.runtime = runtime
        self.default_timeout = float(default_timeout)
        self.memory_mb = int(memory_mb)
        self._warned_local = False

    # -- introspection ----------------------------------------------------- #

    @property
    def backend_name(self) -> str:
        return type(getattr(self.runtime, "executor", None)).__name__

    def _warn_if_local(self) -> None:
        if self._warned_local or "Local" not in self.backend_name:
            return
        self._warned_local = True
        logger.warning(
            "research CodeAct is running in the guarded local subprocess "
            "fallback (Docker unavailable): the AST gate and the workspace "
            "cwd are the only isolation. Install/start Docker for the full "
            "sandbox."
        )

    # -- execution --------------------------------------------------------- #

    def run(
        self,
        dataset_id: str,
        code: str,
        *,
        timeout: float | None = None,
        cancelled: Any = None,
    ) -> Observation:
        """Execute ``code`` and return a bounded :class:`Observation`.

        Never raises for a *snippet* failure — a traceback is data the loop
        reflects on. Raises only for a refused snippet
        (:class:`ResearchSecurityError`) or a blown deadline
        (:class:`ResearchTimeout`).
        """
        source = validate_code(code)
        self._warn_if_local()
        deadline = float(timeout or self.default_timeout)
        record = self.runtime.datasets.get(dataset_id)
        workspace = self.runtime.datasets.dir_for(record)

        body = f"{_EMIT_GUARD}\n\n{textwrap.dedent(source).strip()}\n\n{_EMIT_FLUSH}\n"
        params = {
            "active_file": record.active_file,
            "active_format": "csv" if record.cleaned else record.format,
            "known_dtypes": record.dtypes if record.cleaned else {},
            "encoding": "utf-8" if record.cleaned else (record.encoding or "utf-8"),
            "preview_rows": 20,
        }
        return self._execute(workspace, body, params, deadline, cancelled)

    def run_trusted(
        self,
        dataset_id: str,
        body: str,
        params: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> Observation:
        """Run an *engine-authored* script body (never model output).

        Used for compilation steps — PDF rendering, for example — where the
        source is a constant in Dream's own codebase. It skips the AST gate
        (there is no untrusted author to gate) but keeps every other control:
        the same sandbox, the same deadline, the same output truncation, and
        the same ``_params.json`` discipline.
        """
        record = self.runtime.datasets.get(dataset_id)
        workspace = self.runtime.datasets.dir_for(record)
        merged = {
            "active_file": record.active_file,
            "active_format": "csv" if record.cleaned else record.format,
            "known_dtypes": record.dtypes if record.cleaned else {},
            "encoding": "utf-8" if record.cleaned else (record.encoding or "utf-8"),
            "preview_rows": 20,
            **params,
        }
        return self._execute(
            workspace, body, merged, float(timeout or self.default_timeout), None
        )

    def _execute(
        self,
        workspace: Path,
        body: str,
        params: dict[str, Any],
        deadline: float,
        cancelled: Any,
    ) -> Observation:
        from dream.skills.data_science import _script  # reuse, never re-implement

        params_path = workspace / "_params.json"
        result_path = workspace / "_result.json"
        params_path.write_text(json.dumps(params, ensure_ascii=False), encoding="utf-8")
        result_path.unlink(missing_ok=True)
        script = _script(body)

        # Watchdog: the executor's own timeout is the first line of defence;
        # the thread deadline (+ grace) is the second, so a wedged container
        # client cannot hang the session forever.
        # Not a context manager: exiting one joins the worker, which would
        # undo the watchdog. A wedged execution thread is abandoned instead.
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(
                self.runtime.executor.run, script, workspace, int(max(1, deadline))
            )
            try:
                outcome = future.result(timeout=deadline + 15.0)
            except concurrent.futures.TimeoutError:
                future.cancel()
                raise ResearchTimeout(
                    f"code execution exceeded {deadline:.0f}s and was abandoned"
                ) from None
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
            params_path.unlink(missing_ok=True)

        if cancelled is not None and getattr(cancelled, "is_set", lambda: False)():
            result_path.unlink(missing_ok=True)
            from dream.research.errors import ResearchCancelled

            raise ResearchCancelled("cancelled during code execution")

        if getattr(outcome, "timed_out", False):
            result_path.unlink(missing_ok=True)
            raise ResearchTimeout(f"code execution exceeded {deadline:.0f}s inside the sandbox")

        result: dict[str, Any] = {}
        if result_path.exists():
            try:
                payload = json.loads(result_path.read_text(encoding="utf-8"))
                # Snippets emit through the loop's wrapper ({"emitted": ...});
                # trusted bodies use the prelude's own emit() and write the
                # object directly.
                if isinstance(payload, dict) and "emitted" in payload:
                    result = dict(payload.get("emitted") or {})
                elif isinstance(payload, dict):
                    result = payload
                else:
                    result = {"value": payload}
            except (OSError, ValueError):
                result = {}
            result_path.unlink(missing_ok=True)

        stderr = _truncate(getattr(outcome, "stderr", "") or "")
        error = ""
        if getattr(outcome, "return_code", 0) != 0:
            error = stderr.strip().splitlines()[-1] if stderr.strip() else "execution failed"
        return Observation(
            stdout=_truncate(getattr(outcome, "stdout", "") or ""),
            stderr=stderr,
            result=result,
            error=error,
        )

    # -- diagnostics ------------------------------------------------------- #

    @staticmethod
    def docker_available() -> bool:
        """True when the Docker sandbox path is selectable in this process."""
        if os.environ.get("DREAM_DATA_LOCAL_EXEC", "").strip().lower() in {"1", "true", "yes"}:
            return False
        try:
            from dream.docker_sandbox import DockerSandbox  # noqa: F401
        except ImportError:  # pragma: no cover - dream always ships it
            return False
        return True

    def elapsed_budget(self, started: float, budget: float) -> float:
        """Remaining seconds in a budget, floored at zero (no negative sleeps)."""
        return max(0.0, budget - (time.monotonic() - started))
