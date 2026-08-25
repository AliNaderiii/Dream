"""Watchdog executor for the trusted Data Q&A worker."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from dream.dataqa.models import ExecutionResult, QueryPlan
from dream.security.secrets import redact_structure, redact_text

MAX_MEMORY_BYTES = 512 * 1024 * 1024
MAX_STDOUT_BYTES = 1_100_000


def _limits() -> None:
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
        resource.setrlimit(resource.RLIMIT_AS, (MAX_MEMORY_BYTES, MAX_MEMORY_BYTES))
        resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
        resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))
    except (ImportError, OSError, ValueError):
        pass


def execute_plan(
    path: Path,
    fmt: str,
    plan: QueryPlan,
    *,
    timeout: float = 10.0,
    workspace: Path | None = None,
) -> ExecutionResult:
    worker = Path(__file__).with_name("worker.py").resolve()
    root = (workspace or path.parent).resolve()
    resolved_path = path.resolve()
    if path.is_symlink() or not resolved_path.is_file() or not resolved_path.is_relative_to(root):
        return ExecutionResult(
            status="error",
            answer_shape=plan.answer_shape,
            columns=[],
            rows=[],
            rows_considered=0,
            operation=plan.action,
            error="dataset path escaped the Dream workspace",
        )
    payload = json.dumps(
        {
            "dataset_path": str(resolved_path),
            "workspace_root": str(root),
            "format": fmt,
            "plan": plan.to_dict(),
        },
        ensure_ascii=False,
    )
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONHASHSEED": "0",
        "HOME": str(path.parent.resolve()),
    }
    try:
        completed = subprocess.run(
            [sys.executable, "-I", str(worker)],
            input=payload,
            text=True,
            capture_output=True,
            timeout=max(0.2, min(timeout, 30)),
            env=env,
            cwd=str(path.parent.resolve()),
            preexec_fn=_limits if os.name == "posix" else None,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            status="cancelled",
            answer_shape=plan.answer_shape,
            columns=[],
            rows=[],
            rows_considered=0,
            operation=plan.action,
            warnings=["The operation exceeded its deadline and was terminated."],
            error="deadline exceeded",
        )
    if len(completed.stdout.encode()) > MAX_STDOUT_BYTES:
        return ExecutionResult(
            status="error",
            answer_shape=plan.answer_shape,
            columns=[],
            rows=[],
            rows_considered=0,
            operation=plan.action,
            error="worker output quota exceeded",
        )
    try:
        raw: dict[str, Any] = json.loads(completed.stdout)
    except ValueError:
        message = redact_text(completed.stderr[-300:] or "worker returned invalid output")
        return ExecutionResult(
            status="error",
            answer_shape=plan.answer_shape,
            columns=[],
            rows=[],
            rows_considered=0,
            operation=plan.action,
            error=message,
        )
    result = ExecutionResult.from_dict(redact_structure(raw))
    result.warnings.insert(
        0, "Docker unavailable: guarded local subprocess used; this is not a container boundary."
    )
    return result
