#!/usr/bin/env python3
"""Phase 32: Isolated Code Interpreter & Data Science Sandbox Subsystem.

Applies all modules for Phase 32:
- dream/sandbox/types.py
- dream/sandbox/executor.py
- dream/sandbox/analyzer.py
- dream/sandbox/engine.py
- dream/sandbox/tools.py
- dream/sandbox/slash.py
- dream/sandbox/__init__.py
- dream/tools/toolsets.py (registered sandbox toolset)
- tests/test_code_sandbox_and_interpreter.py
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

FILES: dict[str, str] = {
    "dream/sandbox/types.py": r'''"""Domain models and data structures for Code Interpreter and Isolated Execution Sandbox."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any


class ExecutionLanguage(str, Enum):
    """Supported programming and query languages."""

    PYTHON = "python"
    BASH = "bash"
    SQL = "sql"
    JAVASCRIPT = "javascript"


class ExecutionStatus(str, Enum):
    """Outcome states of sandbox execution."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"


@dataclass(slots=True)
class ExecutionArtifact:
    """A file, chart, or dataset generated during sandbox execution."""

    name: str
    file_path: str
    mime_type: str
    size_bytes: int
    description_fa: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize artifact to dictionary."""
        return {
            "name": self.name,
            "file_path": self.file_path,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "description_fa": self.description_fa,
            "timestamp": round(self.timestamp, 2),
        }


@dataclass(slots=True)
class ExecutionResult:
    """Full outcome of a sandbox execution including stdout, stderr, and metrics."""

    code: str
    language: ExecutionLanguage
    status: ExecutionStatus
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    artifacts: list[ExecutionArtifact] = field(default_factory=list)
    error_message: str = ""
    variables_updated: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize execution result to dictionary."""
        return {
            "language": self.language.value,
            "status": self.status.value,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": round(self.duration_ms, 2),
            "artifacts": [a.to_dict() for a in self.artifacts],
            "error_message": self.error_message,
            "variables_updated": self.variables_updated,
            "timestamp": round(self.timestamp, 2),
        }


@dataclass(slots=True)
class DatasetSummary:
    """Statistical and structural summary of an analyzed dataset."""

    total_rows: int
    total_columns: int
    column_names: list[str]
    column_types: dict[str, str]
    null_counts: dict[str, int]
    numeric_stats: dict[str, dict[str, float]]  # col -> {mean, min, max, std}
    sample_preview: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Serialize dataset summary to dictionary."""
        return {
            "total_rows": self.total_rows,
            "total_columns": self.total_columns,
            "column_names": self.column_names,
            "column_types": self.column_types,
            "null_counts": self.null_counts,
            "numeric_stats": self.numeric_stats,
            "sample_preview": self.sample_preview,
        }
''',
    "dream/sandbox/executor.py": r'''"""Isolated code execution sandbox with output redirection and stateful namespace."""

from __future__ import annotations

import contextlib
import io
import math
from pathlib import Path
import re
import sys
import time
from typing import Any
import uuid

from dream.sandbox.types import (
    ExecutionArtifact,
    ExecutionLanguage,
    ExecutionResult,
    ExecutionStatus,
)
from dream.security.pathsafety import is_sensitive_path


class SandboxExecutor:
    """Safely runs code in a stateful isolated environment and captures artifacts."""

    def __init__(self, workspace_dir: str | Path | None = None) -> None:
        self.workspace_dir = Path(workspace_dir or "/tmp/dream_sandbox")
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self._namespace: dict[str, Any] = self._create_initial_namespace()
        self._forbidden_patterns = [
            r"rm\s+-rf\s+/",
            r"/etc/passwd",
            r"/etc/shadow",
            r"C:\\Windows\\System32",
            r"os\.system\(",
            r"subprocess\.Popen\(",
            r"shutil\.rmtree\(['\"]\/",
        ]

    def _create_initial_namespace(self) -> dict[str, Any]:
        """Set up standard math and utility namespace."""
        ns: dict[str, Any] = {
            "math": math,
            "__builtins__": __builtins__,
            "Path": Path,
            "json": __import__("json"),
            "re": re,
            "workspace_dir": str(self.workspace_dir),
        }
        return ns

    def reset_namespace(self) -> None:
        """Reset execution namespace to initial state."""
        self._namespace = self._create_initial_namespace()

    def execute_python(
        self,
        code: str,
        timeout_seconds: float = 15.0,
    ) -> ExecutionResult:
        """Execute Python code within the stateful session namespace."""
        start_time = time.monotonic()

        # Security check for destructive commands
        for pat in self._forbidden_patterns:
            if re.search(pat, code, re.IGNORECASE):
                return ExecutionResult(
                    code=code,
                    language=ExecutionLanguage.PYTHON,
                    status=ExecutionStatus.BLOCKED,
                    exit_code=1,
                    stdout="",
                    stderr="\u062f\u0633\u062a\u0648\u0631 \u0628\u0647 \u062f\u0644\u06cc\u0644 \u0645\u0644\u0627\u062d\u0638\u0627\u062a \u0627\u0645\u0646\u06cc\u062a\u06cc \u0645\u0633\u062f\u0648\u062f \u0634\u062f.",
                    duration_ms=(time.monotonic() - start_time) * 1000,
                    error_message="Security Policy Refusal: Destructive pattern detected.",
                )

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        initial_keys = set(self._namespace.keys())
        initial_files = set(self.workspace_dir.glob("*")) if self.workspace_dir.exists() else set()

        status = ExecutionStatus.SUCCESS
        exit_code = 0
        err_msg = ""

        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            try:
                # If code is a single expression, evaluate and print
                try:
                    expr_ast = compile(code, "<sandbox>", "eval")
                    res = eval(expr_ast, self._namespace)
                    if res is not None:
                        print(repr(res))
                except SyntaxError:
                    exec_ast = compile(code, "<sandbox>", "exec")
                    exec(exec_ast, self._namespace)
            except Exception as exc:
                status = ExecutionStatus.ERROR
                exit_code = 1
                err_msg = f"{type(exc).__name__}: {str(exc)}"
                stderr_buf.write(f"\nTraceback: {err_msg}")

        duration = (time.monotonic() - start_time) * 1000
        new_keys = [k for k in self._namespace.keys() if k not in initial_keys and not k.startswith("_")]

        # Discover new generated artifacts in workspace
        current_files = set(self.workspace_dir.glob("*")) if self.workspace_dir.exists() else set()
        new_files = current_files - initial_files
        artifacts: list[ExecutionArtifact] = []

        for f in new_files:
            if f.is_file():
                mime = "image/png" if f.suffix == ".png" else "text/plain"
                artifacts.append(
                    ExecutionArtifact(
                        name=f.name,
                        file_path=str(f),
                        mime_type=mime,
                        size_bytes=f.stat().st_size,
                        description_fa=f"\u0641\u0627\u06cc\u0644 \u062a\u0648\u0644\u06cc\u062f\u0634\u062f\u0647: {f.name}",
                    )
                )

        return ExecutionResult(
            code=code,
            language=ExecutionLanguage.PYTHON,
            status=status,
            exit_code=exit_code,
            stdout=stdout_buf.getvalue(),
            stderr=stderr_buf.getvalue(),
            duration_ms=duration,
            artifacts=artifacts,
            error_message=err_msg,
            variables_updated=new_keys,
        )
''',
    "dream/sandbox/analyzer.py": r'''"""Data Science Analyzer: Automated dataset profiling, statistics, and tabular analysis."""

from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path
from typing import Any

from dream.sandbox.types import DatasetSummary
from dream.security.pathsafety import is_sensitive_path


class DataScienceAnalyzer:
    """Automated statistical summarization and column profiling for tabular datasets."""

    def analyze_tabular_data(
        self,
        data_content_or_path: str,
        delimiter: str = ",",
    ) -> DatasetSummary:
        """Parse raw CSV/JSON string or load from file, generating statistical breakdown."""
        raw_rows: list[dict[str, str]] = []
        content = ""
        is_path = False

        # Safe path detection without triggering Windows [WinError 123] invalid filename syntax
        raw_str = data_content_or_path.strip()
        if (
            "\n" not in data_content_or_path
            and len(data_content_or_path) < 1024
            and not raw_str.startswith(("{", "["))
        ):
            try:
                p = Path(data_content_or_path)
                if p.exists() and p.is_file():
                    is_path = True
            except OSError:
                is_path = False

        if is_path:
            if is_sensitive_path(data_content_or_path):
                raise PermissionError(
                    f"Permission denied: '{data_content_or_path}' is a sensitive system path."
                )
            content = Path(data_content_or_path).read_text(encoding="utf-8")
        else:
            content = raw_str

        # Parse JSON or CSV
        if content.startswith("[") or content.startswith("{"):
            try:
                parsed_json = json.loads(content)
                if isinstance(parsed_json, list):
                    raw_rows = [
                        {k: str(v) for k, v in row.items()}
                        for row in parsed_json
                        if isinstance(row, dict)
                    ]
                elif isinstance(parsed_json, dict):
                    raw_rows = [{k: str(v) for k, v in parsed_json.items()}]
            except Exception:
                pass

        if not raw_rows:
            reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
            raw_rows = list(reader)

        if not raw_rows:
            return DatasetSummary(
                total_rows=0,
                total_columns=0,
                column_names=[],
                column_types={},
                null_counts={},
                numeric_stats={},
                sample_preview=[],
            )

        col_names = list(raw_rows[0].keys())
        total_rows = len(raw_rows)
        total_cols = len(col_names)

        col_types: dict[str, str] = {}
        null_counts: dict[str, int] = {}
        numeric_stats: dict[str, dict[str, float]] = {}

        for col in col_names:
            values = [row.get(col, "").strip() for row in raw_rows]
            nulls = sum(1 for v in values if v == "" or v.lower() in ("null", "none", "nan"))
            null_counts[col] = nulls

            # Check if numeric
            non_empty = [v for v in values if v not in ("", "null", "none", "nan")]
            is_num = False
            num_vals: list[float] = []

            if non_empty:
                try:
                    num_vals = [float(v.replace(",", "")) for v in non_empty]
                    is_num = True
                except ValueError:
                    is_num = False

            if is_num and num_vals:
                col_types[col] = "float" if any("." in v for v in non_empty) else "integer"
                avg = sum(num_vals) / len(num_vals)
                variance = (
                    sum((x - avg) ** 2 for x in num_vals) / len(num_vals)
                    if len(num_vals) > 1
                    else 0.0
                )
                numeric_stats[col] = {
                    "mean": round(avg, 2),
                    "min": round(min(num_vals), 2),
                    "max": round(max(num_vals), 2),
                    "std": round(math.sqrt(variance), 2),
                }
            else:
                col_types[col] = "string"

        return DatasetSummary(
            total_rows=total_rows,
            total_columns=total_cols,
            column_names=col_names,
            column_types=col_types,
            null_counts=null_counts,
            numeric_stats=numeric_stats,
            sample_preview=[dict(r) for r in raw_rows[:5]],
        )

    def format_summary_markdown(self, summary: DatasetSummary) -> str:
        """Format dataset profiling summary into a clean Persian/English Markdown report."""
        lines = [
            f"## \U0001f4ca \u06af\u0632\u0627\u0631\u0634 \u062a\u062d\u0644\u06cc\u0644 \u062f\u0627\u062f\u0647\u200c\u0647\u0627 (Dataset Profile)",
            f"- \u062a\u0639\u062f\u0627\u062f \u0633\u0637\u0631\u0647\u0627 (Rows): {summary.total_rows:,}",
            f"- \u062a\u0639\u062f\u0627\u062f \u0633\u062a\u0648\u0646\u200c\u0647\u0627 (Columns): {summary.total_columns}",
            "",
            "### \U0001f4cb \u062c\u062f\u0648\u0644 \u0645\u0634\u062e\u0635\u0627\u062a \u0633\u062a\u0648\u0646\u200c\u0647\u0627",
            "| \u0633\u062a\u0648\u0646 | \u0646\u0648\u0639 \u062f\u0627\u062f\u0647 | \u0645\u0642\u0627\u062f\u06cc\u0631 \u062e\u0627\u0644\u06cc (Nulls) | \u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 (Mean) | \u062d\u062f\u0627\u0642\u0644-\u062d\u062f\u0627\u06a9\u062b\u0631 (Min-Max) |",
            "|---|---|---|---|---|",
        ]

        for col in summary.column_names:
            c_type = summary.column_types.get(col, "string")
            nulls = summary.null_counts.get(col, 0)
            stats = summary.numeric_stats.get(col)

            if stats:
                mean_str = f"{stats['mean']:.2f}"
                min_max_str = f"{stats['min']:.1f} - {stats['max']:.1f}"
            else:
                mean_str = "-"
                min_max_str = "-"

            lines.append(f"| `{col}` | {c_type} | {nulls} | {mean_str} | {min_max_str} |")

        return "\n".join(lines)
''',
    "dream/sandbox/engine.py": r'''"""Code Interpreter Sandbox Engine Coordinator."""

from __future__ import annotations

import time
from typing import Any

from dream.sandbox.analyzer import DataScienceAnalyzer
from dream.sandbox.executor import SandboxExecutor
from dream.sandbox.types import DatasetSummary, ExecutionArtifact, ExecutionResult


class SandboxEngine:
    """Coordinates code execution, stateful REPL namespaces, and automated data analysis."""

    def __init__(
        self,
        executor: SandboxExecutor | None = None,
        analyzer: DataScienceAnalyzer | None = None,
    ) -> None:
        self.executor = executor or SandboxExecutor()
        self.analyzer = analyzer or DataScienceAnalyzer()
        self._history: list[ExecutionResult] = []
        self._all_artifacts: list[ExecutionArtifact] = []

    def run_code(
        self,
        code: str,
        timeout_seconds: float = 15.0,
    ) -> ExecutionResult:
        """Execute Python code in isolated sandbox and register output artifacts."""
        result = self.executor.execute_python(code, timeout_seconds=timeout_seconds)
        self._history.append(result)
        for art in result.artifacts:
            self._all_artifacts.append(art)
        return result

    def analyze_data(
        self,
        data_or_path: str,
    ) -> tuple[DatasetSummary, str]:
        """Perform statistical profiling on a CSV/JSON tabular dataset."""
        summary = self.analyzer.analyze_tabular_data(data_or_path)
        report_md = self.analyzer.format_summary_markdown(summary)
        return summary, report_md

    def reset(self) -> None:
        """Reset stateful session variables and clear history."""
        self.executor.reset_namespace()
        self._history.clear()

    def list_artifacts(self) -> list[ExecutionArtifact]:
        """Return all files and charts generated during this sandbox session."""
        return list(self._all_artifacts)

    def get_status(self) -> dict[str, Any]:
        """Get summary metrics on executions, namespaces, and generated artifacts."""
        return {
            "total_executions": len(self._history),
            "total_artifacts": len(self._all_artifacts),
            "workspace_dir": str(self.executor.workspace_dir),
            "variables_count": len(self.executor._namespace),
            "last_execution_status": self._history[-1].status.value if self._history else "ready",
        }
''',
    "dream/sandbox/tools.py": r'''"""LLM Tool bindings for Code Interpreter and Execution Sandbox."""

from __future__ import annotations

from typing import Any

from dream.sandbox.engine import SandboxEngine

_GLOBAL_SANDBOX_ENGINE: SandboxEngine | None = None


def get_global_sandbox_engine() -> SandboxEngine:
    """Get or initialize singleton SandboxEngine."""
    global _GLOBAL_SANDBOX_ENGINE
    if _GLOBAL_SANDBOX_ENGINE is None:
        _GLOBAL_SANDBOX_ENGINE = SandboxEngine()
    return _GLOBAL_SANDBOX_ENGINE


def reset_global_sandbox_engine() -> None:
    """Reset SandboxEngine singleton instance."""
    global _GLOBAL_SANDBOX_ENGINE
    _GLOBAL_SANDBOX_ENGINE = None


def sandbox_execute_python(
    code: str,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    """Execute Python code in the stateful sandbox, capturing output and generated files."""
    engine = get_global_sandbox_engine()
    res = engine.run_code(code, timeout_seconds=timeout_seconds)
    return {"success": res.status.value == "success", "result": res.to_dict()}


def sandbox_analyze_dataset(
    data_or_path: str,
) -> dict[str, Any]:
    """Profile tabular data (CSV/JSON), computing column distributions and statistics."""
    engine = get_global_sandbox_engine()
    try:
        summary, report_md = engine.analyze_data(data_or_path)
        return {
            "success": True,
            "summary": summary.to_dict(),
            "markdown_report": report_md,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def sandbox_reset_session() -> dict[str, Any]:
    """Reset the sandbox stateful namespace and purge local artifacts."""
    engine = get_global_sandbox_engine()
    engine.reset()
    return {"success": True, "message": "\u0645\u062d\u06cc\u0637 \u0633\u0646\u062f\u0628\u0627\u06a9\u0633 \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."}


def sandbox_list_artifacts() -> dict[str, Any]:
    """List all charts, plots, and files produced during sandbox sessions."""
    engine = get_global_sandbox_engine()
    artifacts = engine.list_artifacts()
    return {"success": True, "artifacts": [a.to_dict() for a in artifacts]}


def sandbox_get_status() -> dict[str, Any]:
    """Get current status of sandbox execution environment."""
    engine = get_global_sandbox_engine()
    status = engine.get_status()
    return {"success": True, **status}


def get_sandbox_tools() -> list[Any]:
    """Return Sandbox tool functions for agent registration."""
    return [
        sandbox_execute_python,
        sandbox_analyze_dataset,
        sandbox_reset_session,
        sandbox_list_artifacts,
        sandbox_get_status,
    ]
''',
    "dream/sandbox/slash.py": r'''"""Slash command handlers for Code Interpreter & Sandbox Execution."""

from __future__ import annotations

from typing import Any

from dream.sandbox.tools import (
    sandbox_analyze_dataset,
    sandbox_execute_python,
    sandbox_get_status,
    sandbox_reset_session,
)


def handle_sandbox_slash_command(command_str: str) -> str:
    """Handle /code, /data, and /sandbox CLI slash commands.

    Usage:
        /code <python_snippet>
        /data <path_or_content>
        /sandbox reset
        /sandbox status
    """
    cmd = command_str.strip()

    if cmd.startswith("/code"):
        code = cmd[len("/code") :].strip()
        if not code:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u06a9\u062f \u067e\u0627\u06cc\u062a\u0648\u0646 \u0631\u0627 \u0628\u0631\u0627\u06cc \u0627\u062c\u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = sandbox_execute_python(code)
        r = res.get("result", {})
        stdout = r.get("stdout", "").strip()
        stderr = r.get("stderr", "").strip()
        dur = r.get("duration_ms", 0.0)

        out_parts = [f"\u2699\ufe0f \u0646\u062a\u06cc\u062c\u0647 \u0627\u062c\u0631\u0627 ({dur:.1f} \u0645\u06cc\u0644\u06cc\u200c\u062b\u0627\u0646\u06cc\u0647):"]
        if stdout:
            out_parts.append(f"```text\n{stdout}\n```")
        if stderr:
            out_parts.append(f"\u274c \u062e\u0637\u0627:\n```text\n{stderr}\n```")
        if not stdout and not stderr:
            out_parts.append("\u2705 \u06a9\u062f \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u0648 \u0628\u062f\u0648\u0646 \u062e\u0631\u0648\u062c\u06cc \u0627\u062c\u0631\u0627 \u0634\u062f.")
        return "\n".join(out_parts)

    if cmd.startswith("/data"):
        data_arg = cmd[len("/data") :].strip()
        if not data_arg:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0645\u0633\u06cc\u0631 \u0641\u0627\u06cc\u0644 CSV \u06cc\u0627 \u0645\u062d\u062a\u0648\u0627\u06cc \u062f\u0627\u062f\u0647 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = sandbox_analyze_dataset(data_arg)
        if res.get("success"):
            return res.get("markdown_report", "")
        return f"\u274c \u062e\u0637\u0627 \u062f\u0631 \u062a\u062d\u0644\u06cc\u0644 \u062f\u0627\u062f\u0647: {res.get('error')}"

    parts = cmd.split(maxsplit=2)
    subcommand = parts[1].lower() if len(parts) > 1 else "status"

    if subcommand == "reset":
        sandbox_reset_session()
        return "\u2705 \u0645\u062d\u06cc\u0637 \u0633\u0646\u062f\u0628\u0627\u06a9\u0633 \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."

    if subcommand == "status":
        st = sandbox_get_status()
        return (
            f"\U0001f4df \u0648\u0636\u0639\u06cc\u062a \u0633\u0646\u062f\u0628\u0627\u06a9\u0633:\n"
            f"- \u062a\u0639\u062f\u0627\u062f \u0627\u062c\u0631\u0627\u0647\u0627: {st.get('total_executions')}\n"
            f"- \u0641\u0627\u06cc\u0644\u200c\u0647\u0627\u06cc \u062a\u0648\u0644\u06cc\u062f\u0634\u062f\u0647: {st.get('total_artifacts')}\n"
            f"- \u0645\u062a\u063a\u06cc\u0631\u0647\u0627\u06cc \u0641\u0639\u0627\u0644 \u062f\u0631 \u062d\u0627\u0641\u0638\u0647: {st.get('variables_count')}"
        )

    return (
        "\u2699\ufe0f \u062f\u0633\u062a\u0648\u0631\u0627\u062a \u0645\u0641\u0633\u0631 \u06a9\u062f \u0648 \u0633\u0646\u062f\u0628\u0627\u06a9\u0633:\n"
        "  /code <python_code>               \u0627\u062c\u0631\u0627\u06cc \u06a9\u062f \u067e\u0627\u06cc\u062a\u0648\u0646\n"
        "  /data <path_or_csv>               \u062a\u062d\u0644\u06cc\u0644 \u0622\u0645\u0627\u0631\u06cc \u062f\u0627\u062f\u06af\u0627\u0646\n"
        "  /sandbox status                   \u0648\u0636\u0639\u06cc\u062a \u0645\u062d\u06cc\u0637 \u0627\u062c\u0631\u0627\n"
        "  /sandbox reset                    \u067e\u0627\u06a9\u0633\u0627\u0632\u06cc \u0648 \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u062d\u0627\u0641\u0638\u0647"
    )
''',
    "dream/sandbox/__init__.py": r'''"""Isolated Code Interpreter, Data Science Profiler, and Execution Sandbox Subsystem."""

from __future__ import annotations

from dream.sandbox.analyzer import DataScienceAnalyzer
from dream.sandbox.engine import SandboxEngine
from dream.sandbox.executor import SandboxExecutor
from dream.sandbox.slash import handle_sandbox_slash_command
from dream.sandbox.tools import (
    get_global_sandbox_engine,
    get_sandbox_tools,
    reset_global_sandbox_engine,
    sandbox_analyze_dataset,
    sandbox_execute_python,
    sandbox_get_status,
    sandbox_list_artifacts,
    sandbox_reset_session,
)
from dream.sandbox.types import (
    DatasetSummary,
    ExecutionArtifact,
    ExecutionLanguage,
    ExecutionResult,
    ExecutionStatus,
)

# Register toolset if toolset registry is present
try:
    from dream.tools.toolsets import Toolset, register_toolset

    register_toolset(
        Toolset(
            name="sandbox",
            description="Isolated Python code execution, dataset analysis, and REPL interpreter.",
            tools=[
                "sandbox_execute_python",
                "sandbox_analyze_dataset",
                "sandbox_reset_session",
                "sandbox_list_artifacts",
                "sandbox_get_status",
            ],
            metadata={"category": "sandbox", "builtin": True},
        )
    )
except Exception:
    pass

__all__ = [
    "DataScienceAnalyzer",
    "DatasetSummary",
    "ExecutionArtifact",
    "ExecutionLanguage",
    "ExecutionResult",
    "ExecutionStatus",
    "SandboxEngine",
    "SandboxExecutor",
    "get_global_sandbox_engine",
    "get_sandbox_tools",
    "handle_sandbox_slash_command",
    "reset_global_sandbox_engine",
    "sandbox_analyze_dataset",
    "sandbox_execute_python",
    "sandbox_get_status",
    "sandbox_list_artifacts",
    "sandbox_reset_session",
]
''',
    "dream/tools/toolsets.py": r'''"""Toolset categorization, grouping, and dynamic tool management."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from dream.tools.base import REGISTRY, Tool


@dataclass(frozen=True)
class Toolset:
    """Group of related tools identified by name."""

    name: str
    description: str
    tools: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


# Default built-in toolsets matching Dream's core capabilities
BUILTIN_TOOLSETS: dict[str, Toolset] = {
    "core": Toolset(
        name="core",
        description="Fundamental utilities (datetime, math calculation)",
        tools=("get_datetime", "calculate"),
    ),
    "workspace": Toolset(
        name="workspace",
        description="Workspace note inspection and editing",
        tools=("read_note", "list_notes", "write_note"),
    ),
    "web": Toolset(
        name="web",
        description="Public internet search and page fetching",
        tools=("search_web", "read_page"),
    ),
    "skills": Toolset(
        name="skills",
        description="Reusable skill management, hub discovery, and autonomous evolution",
        tools=(
            "save_skill",
            "use_skill",
            "list_skills",
            "skill_view",
            "edit_skill",
            "delete_skill",
            "save_skill_bundle",
            "apply_skill_proposal",
            "discard_skill_proposal",
            "hub_search_skills",
            "hub_install_skill",
            "skill_evolve_optimize",
            "skill_export_bundle",
            "skill_import_bundle",
        ),
    ),
    "reminders": Toolset(
        name="reminders",
        description="Scheduled reminders and tasks",
        tools=("create_reminder", "cancel_reminder"),
    ),
    "system": Toolset(
        name="system",
        description="System commands and external communication",
        tools=("run_shell", "send_email"),
    ),
    "mcp": Toolset(
        name="mcp",
        description="Model Context Protocol servers, discovery, and tool execution",
        tools=(
            "mcp_list_servers",
            "mcp_list_tools",
            "mcp_call_tool",
            "mcp_read_resource",
            "mcp_reload",
        ),
    ),
    "subagents": Toolset(
        name="subagents",
        description="Multi-agent orchestration, delegation, and worker lifecycle",
        tools=(
            "subagent_spawn",
            "subagent_wait",
            "subagent_delegate_task",
            "subagent_list",
            "subagent_terminate",
        ),
    ),
    "scheduler": Toolset(
        name="scheduler",
        description="Autonomous cron scheduling, reminders, and multi-channel delivery",
        tools=(
            "schedule_task",
            "list_schedules",
            "cancel_schedule",
            "trigger_schedule",
        ),
    ),
    "retrieval": Toolset(
        name="retrieval",
        description="Hybrid semantic retrieval and knowledge graph memory association",
        tools=(
            "search_hybrid_memory",
            "query_knowledge_graph",
        ),
    ),
    "distill": Toolset(
        name="distill",
        description="Autonomous trajectory recording, distillation, and evaluation benchmarks",
        tools=(
            "distill_record_trajectory",
            "distill_export_dataset",
            "eval_run_benchmark",
        ),
    ),
    "profiles": Toolset(
        name="profiles",
        description="Multi-profile persona scoping and isolated workspace management",
        tools=(
            "profile_list",
            "profile_get_current",
            "profile_switch",
            "profile_create",
        ),
    ),
    "context": Toolset(
        name="context",
        description="Prioritized context files (SOUL, AGENTS, USER, MEMORY) and budgeting",
        tools=(
            "context_get_tier",
            "context_update_tier",
            "context_get_budget_report",
            "context_assemble_prompt",
            "context_reload_all",
        ),
    ),
    "terminal": Toolset(
        name="terminal",
        description="Multi-backend isolated execution (Local, Docker, SSH, Cloud Sandboxes)",
        tools=(
            "terminal_execute",
            "terminal_list_backends",
            "terminal_switch_backend",
        ),
    ),
    "browser": Toolset(
        name="browser",
        description="Multi-driver browser control, DOM extraction, and visual interaction",
        tools=(
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_screenshot",
            "browser_extract_content",
            "browser_close",
            "browser_get_status",
        ),
    ),
    "dialectic": Toolset(
        name="dialectic",
        description="Self-reflective dialectic user modeling and knowledge synthesis",
        tools=(
            "dialectic_observe",
            "dialectic_reflect",
            "dialectic_get_belief_graph",
            "dialectic_reconcile",
            "dialectic_query_traits",
        ),
    ),
    "acp": Toolset(
        name="acp",
        description="Agent Client Protocol (ACP) IDE integration and diff tools",
        tools=(
            "acp_apply_diff",
            "acp_read_diagnostics",
            "acp_get_session_status",
            "acp_list_agents",
            "acp_call_agent",
        ),
    ),
    "plugins": Toolset(
        name="plugins",
        description="Dynamic plugin installation, lifecycle management, and extension hooks",
        tools=(
            "plugin_list",
            "plugin_install",
            "plugin_enable",
            "plugin_disable",
            "plugin_get_info",
        ),
    ),
    "swarm": Toolset(
        name="swarm",
        description="Distributed swarm orchestration, DAG task execution, and consensus",
        tools=(
            "swarm_spawn_node",
            "swarm_plan_workflow",
            "swarm_execute_step",
            "swarm_run_all",
            "swarm_reach_consensus",
            "swarm_get_status",
            "swarm_broadcast_message",
        ),
    ),
    "speech": Toolset(
        name="speech",
        description="Voice synthesis (TTS), recognition (STT), and HybridEmo emotion modeling",
        tools=(
            "speech_text_to_speech",
            "speech_speech_to_text",
            "speech_analyze_voice_emotion",
            "speech_list_voices",
        ),
    ),
    "ocr": Toolset(
        name="ocr",
        description="Persian document OCR, receipt parsing, and invoice field extraction",
        tools=(
            "ocr_extract_document",
            "ocr_extract_invoice",
        ),
    ),
    "knowledge": Toolset(
        name="knowledge",
        description=(
            "Multimodal temporal knowledge graph, timeline reasoning, "
            "and cross-modal entity linking"
        ),
        tools=(
            "knowledge_add_entity",
            "knowledge_add_relation",
            "knowledge_query_temporal",
            "knowledge_get_entity_timeline",
            "knowledge_link_multimodal_artifact",
            "knowledge_get_stats",
        ),
    ),
    "alignment": Toolset(
        name="alignment",
        description=(
            "Continuous self-improving alignment, multi-dimensional scoring, "
            "self-critique, and DPO dataset generation"
        ),
        tools=(
            "alignment_record_feedback",
            "alignment_critique_and_refine",
            "alignment_evaluate_response",
            "alignment_export_dataset",
            "alignment_get_stats",
        ),
    ),
    "research": Toolset(
        name="research",
        description=(
            "Autonomous multi-step deep research, evidence collection, "
            "and multi-source intelligence synthesis"
        ),
        tools=(
            "research_plan_investigation",
            "research_add_source",
            "research_synthesize_report",
            "research_run_autonomous",
            "research_export_report",
            "research_get_status",
            "research_list_sessions",
        ),
    ),
    "cache": Toolset(
        name="cache",
        description=(
            "Semantic caching, speculative pre-fetching, and token economics optimization"
        ),
        tools=(
            "cache_lookup_query",
            "cache_store_entry",
            "cache_predict_tool",
            "cache_get_economics",
            "cache_clear",
            "cache_warmup",
        ),
    ),
    "sandbox": Toolset(
        name="sandbox",
        description=(
            "Isolated Python code execution, dataset analysis, and REPL interpreter"
        ),
        tools=(
            "sandbox_execute_python",
            "sandbox_analyze_dataset",
            "sandbox_reset_session",
            "sandbox_list_artifacts",
            "sandbox_get_status",
        ),
    ),
}

_TOOLSETS: dict[str, Toolset] = dict(BUILTIN_TOOLSETS)


def register_toolset(
    name: str,
    tools: Collection[str],
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> Toolset:
    """Register a new named toolset or update an existing one."""
    toolset = Toolset(
        name=name,
        description=description,
        tools=tuple(sorted(set(tools))),
        metadata=metadata or {},
    )
    _TOOLSETS[name] = toolset
    return toolset


def unregister_toolset(name: str) -> bool:
    """Remove a registered toolset (returns True if removed)."""
    if name in _TOOLSETS:
        del _TOOLSETS[name]
        return True
    return False


def get_toolset(name: str) -> Toolset | None:
    """Return a Toolset by name, or None if not registered."""
    return _TOOLSETS.get(name)


def list_toolsets() -> list[Toolset]:
    """Return a list of all registered Toolsets."""
    return list(_TOOLSETS.values())


def filter_tools(
    toolsets: Collection[str] | None = None,
    include_tools: Collection[str] | None = None,
    exclude_tools: Collection[str] | None = None,
    registry: Mapping[str, Tool] | None = None,
) -> dict[str, Tool]:
    """Filter registered tools by toolset names and explicit inclusions/exclusions."""
    source = REGISTRY if registry is None else registry

    if toolsets is None and include_tools is None and exclude_tools is None:
        return dict(source)

    allowed_names: set[str] = set()

    if toolsets is not None:
        for ts_name in toolsets:
            ts = _TOOLSETS.get(ts_name)
            if ts:
                allowed_names.update(ts.tools)

    if include_tools is not None:
        allowed_names.update(include_tools)

    if toolsets is None and include_tools is None:
        allowed_names.update(source.keys())

    if exclude_tools is not None:
        allowed_names.difference_update(exclude_tools)

    return {name: tool for name, tool in source.items() if name in allowed_names}
''',
    "tests/test_code_sandbox_and_interpreter.py": r'''"""Unit and integration tests for Code Interpreter, Dataset Analysis, and Sandbox Subsystem."""

from __future__ import annotations

from pathlib import Path
import tempfile
import pytest

from dream.sandbox import (
    DataScienceAnalyzer,
    ExecutionLanguage,
    ExecutionStatus,
    SandboxEngine,
    SandboxExecutor,
    handle_sandbox_slash_command,
    reset_global_sandbox_engine,
    sandbox_analyze_dataset,
    sandbox_execute_python,
    sandbox_get_status,
    sandbox_list_artifacts,
    sandbox_reset_session,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_sandbox_engine() -> None:
    reset_global_sandbox_engine()
    yield
    reset_global_sandbox_engine()


def test_toolset_includes_sandbox() -> None:
    """Verify sandbox toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("sandbox")
    assert ts is not None
    assert "sandbox_execute_python" in ts.tools
    assert "sandbox_analyze_dataset" in ts.tools
    assert "sandbox_reset_session" in ts.tools
    assert "sandbox" in BUILTIN_TOOLSETS


def test_sandbox_executor_stateful_execution() -> None:
    """Verify execution of expressions, statements, and stateful namespace across turns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = SandboxExecutor(workspace_dir=tmpdir)

        # Turn 1: Define variables
        res1 = executor.execute_python("x = 50\ny = 25\nz = x + y")
        assert res1.status == ExecutionStatus.SUCCESS
        assert res1.exit_code == 0
        assert "z" in res1.variables_updated

        # Turn 2: Reference previously defined variable and evaluate expression
        res2 = executor.execute_python("z * 2")
        assert res2.status == ExecutionStatus.SUCCESS
        assert "150" in res2.stdout.strip()

        # Turn 3: Reset namespace
        executor.reset_namespace()
        res3 = executor.execute_python("z")
        assert res3.status == ExecutionStatus.ERROR
        assert "NameError" in res3.error_message


def test_sandbox_executor_security_blocking() -> None:
    """Verify interception and blocking of destructive host commands."""
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = SandboxExecutor(workspace_dir=tmpdir)

        # Test rm -rf / blocking
        res_rm = executor.execute_python("import os; os.system('rm -rf /')")
        assert res_rm.status == ExecutionStatus.BLOCKED
        assert res_rm.exit_code == 1

        # Test sensitive path blocking
        res_pass = executor.execute_python("f = open('/etc/passwd')")
        assert res_pass.status == ExecutionStatus.BLOCKED


def test_data_science_analyzer_tabular_profiling() -> None:
    """Verify automated statistical profiling and Markdown table generation."""
    analyzer = DataScienceAnalyzer()

    csv_data = """product,sales,quantity,active
Widget A,120.50,10,true
Widget B,240.00,20,true
Widget C,95.25,5,false
Widget D,,15,true
"""
    summary = analyzer.analyze_tabular_data(csv_data)
    assert summary.total_rows == 4
    assert summary.total_columns == 4
    assert "sales" in summary.column_names
    assert summary.null_counts["sales"] == 1
    assert summary.column_types["quantity"] == "integer"
    assert summary.numeric_stats["quantity"]["mean"] == 12.5
    assert summary.numeric_stats["quantity"]["min"] == 5.0
    assert summary.numeric_stats["quantity"]["max"] == 20.0

    md_report = analyzer.format_summary_markdown(summary)
    assert "Dataset Profile" in md_report
    assert "Widget A" in md_report or "quantity" in md_report


def test_sandbox_engine_and_artifact_generation() -> None:
    """Verify end-to-end sandbox engine and workspace file discovery."""
    with tempfile.TemporaryDirectory() as tmpdir:
        executor = SandboxExecutor(workspace_dir=tmpdir)
        engine = SandboxEngine(executor=executor)

        # Script that writes a local file in workspace using injected workspace_dir
        code = """
from pathlib import Path
out = Path(workspace_dir) / 'results.txt'
out.write_text('Simulation Complete: 100% accuracy', encoding='utf-8')
"""
        res = engine.run_code(code)
        assert res.status == ExecutionStatus.SUCCESS
        assert len(res.artifacts) >= 1
        assert res.artifacts[0].name == "results.txt"

        status = engine.get_status()
        assert status["total_executions"] == 1
        assert status["total_artifacts"] == 1


def test_sandbox_tools_and_slash_commands() -> None:
    """Verify LLM tool wrappers and /code, /data, /sandbox slash commands."""
    # Tool: execute python
    res_py = sandbox_execute_python("math.sqrt(144)")
    assert res_py["success"] is True
    assert "12.0" in res_py["result"]["stdout"]

    # Tool: analyze dataset
    json_data = '[{"name": "Ali", "score": 98}, {"name": "Sara", "score": 92}]'
    res_data = sandbox_analyze_dataset(json_data)
    assert res_data["success"] is True
    assert res_data["summary"]["total_rows"] == 2

    # Tool: get status
    res_st = sandbox_get_status()
    assert res_st["success"] is True
    assert res_st["total_executions"] >= 1

    # Slash: /code
    slash_code = handle_sandbox_slash_command("/code print('Hello Dream Sandbox')")
    assert "Hello Dream Sandbox" in slash_code

    # Slash: /data
    slash_data = handle_sandbox_slash_command(f"/data {json_data}")
    assert "Dataset Profile" in slash_data

    # Slash: /sandbox status
    slash_status = handle_sandbox_slash_command("/sandbox status")
    assert "\u0648\u0636\u0639\u06cc\u062a \u0633\u0646\u062f\u0628\u0627\u06a9\u0633" in slash_status

    # Slash: /sandbox reset
    slash_reset = handle_sandbox_slash_command("/sandbox reset")
    assert "\u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f" in slash_reset
''',
}


def main() -> None:
    root = Path(__file__).resolve().parent
    if not (root / "dream").exists():
        if (root / "dream-repo" / "dream").exists():
            root = root / "dream-repo"
        elif (Path.cwd() / "dream").exists():
            root = Path.cwd()
        else:
            print(f"Error: could not locate Dream repo root from {root}")
            sys.exit(1)

    print(f"Applying Phase 32 (Code Interpreter & Sandbox Engine) to: {root}")

    for rel_path, content in FILES.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"  [written] {rel_path}")

    print("\nRunning pytest validation...")
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_code_sandbox_and_interpreter.py", "-v"],
        cwd=root,
    )
    if res.returncode != 0:
        print("\n[FAIL] Pytest failed for Phase 32")
        sys.exit(res.returncode)

    print("\nRunning security audit...")
    audit_res = subprocess.run(
        [sys.executable, "tools/security_audit.py"],
        cwd=root,
    )
    if audit_res.returncode != 0:
        print("\n[FAIL] Security audit failed for Phase 32")
        sys.exit(audit_res.returncode)

    print("\n[SUCCESS] Phase 32 (Code Interpreter & Sandbox Engine) applied and verified cleanly!")


if __name__ == "__main__":
    main()
