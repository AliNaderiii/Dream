"""Shared fixtures for the sandboxed data-science round-trip tests.

The suite runs the generated scripts on the *test interpreter* (which has
pandas/scipy/matplotlib installed) through :class:`LocalTestExecutor` below.
Production has no such executor any more: MASTER-P0 D1 removed both the
``DREAM_DATA_LOCAL_EXEC`` opt-in and the import-failure fallback, so
``DataScienceRuntime()`` routes every script through the Docker sandbox or
reports a typed ``unavailable`` result.

``LocalTestExecutor`` is a **test fixture**, not a product path: it lives under
``tests/`` and nothing in ``dream/`` imports it. It exists so the round-trip
tests can exercise the generated scripts on a machine without a Docker daemon
without leaving a hole in the shipped runtime.

Skipping is module-level: when pandas is absent (minimal CI env) every
round-trip module skips cleanly while the host-side validator tests in
``test_data_science.py`` still run.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from dream.skills.data_science import (
    DataScienceRuntime,
    DatasetManager,
    ExecResult,
)

SALES_HEADER = "region,price,quantity,invoice_date,email,active"


class LocalTestExecutor:
    """Run a script with the test interpreter. Test-only; never shipped.

    This is deliberately *not* a sandbox and must never be described as one:
    ``python -I`` isolates imports and the working directory, nothing else. It
    is acceptable here only because the payload is a fixture this repository
    owns, and it is unreachable from any product entry point.
    """

    available = True
    backend = "test-local"

    def __init__(self, python: str | None = None) -> None:
        self.python = python or sys.executable

    def run(self, code: str, workspace: Path, timeout: int = 120) -> ExecResult:
        script = workspace / "_script.py"
        script.write_text(code, encoding="utf-8")
        started = time.monotonic()
        env = {"PATH": os.environ.get("PATH", ""), "MPLBACKEND": "Agg"}
        if os.environ.get("SYSTEMROOT"):  # Windows needs this for the CRT
            env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
        try:
            completed = subprocess.run(
                [self.python, "-I", str(script)],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                check=False,
            )
            return ExecResult(
                stdout=completed.stdout,
                stderr=completed.stderr,
                return_code=completed.returncode,
                elapsed_seconds=time.monotonic() - started,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(
                timed_out=True,
                return_code=-1,
                stderr=f"execution exceeded {timeout}s",
                elapsed_seconds=time.monotonic() - started,
            )
        finally:
            script.unlink(missing_ok=True)


def test_executor() -> LocalTestExecutor:
    """The executor the round-trip fixtures inject explicitly."""
    return LocalTestExecutor()


def make_runtime(tmp_path: Path) -> DataScienceRuntime:
    """A runtime with an isolated registry and an injected test executor."""
    return DataScienceRuntime(
        DatasetManager(tmp_path / "datasets"),
        test_executor(),
        preview_rows=10,
    )


def write_sales_csv(path: Path, rows: int = 60) -> Path:
    """Deterministic mixed-type fixture: numerics, categorical, dates, gaps."""
    lines = [SALES_HEADER]
    for i in range(rows):
        region = ["north", "south", "east"][i % 3]
        price = "" if i % 13 == 0 else str(10.0 + i)
        quantity = str(1 + (i % 7))
        date = f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}"
        email = "" if i % 9 == 0 else f"user{i}@example.com"
        active = "true" if i % 2 == 0 else "false"
        lines.append(f"{region},{price},{quantity},{date},{email},{active}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load_sales(runtime: DataScienceRuntime, tmp_path: Path, rows: int = 60) -> str:
    """Ingest the sales fixture, returning the dataset id."""
    csv = write_sales_csv(tmp_path / "sales.csv", rows)
    return runtime.load_data(str(csv), "sales")["dataset_id"]
