"""Shared fixtures for the sandboxed data-science round-trip tests.

The suite runs the generated scripts with :class:`LocalPythonExecutor` (the
test interpreter has pandas/scipy/matplotlib installed); production routes
the same scripts through the Docker sandbox. Skipping is module-level: when
pandas is absent (minimal CI env) every round-trip module skips cleanly while
the host-side validator tests in ``test_data_science.py`` still run.
"""

from __future__ import annotations

from pathlib import Path

from dream.skills.data_science import (
    DataScienceRuntime,
    DatasetManager,
    LocalPythonExecutor,
)

SALES_HEADER = "region,price,quantity,invoice_date,email,active"


def make_runtime(tmp_path: Path) -> DataScienceRuntime:
    """A runtime with an isolated registry and the local executor."""
    return DataScienceRuntime(
        DatasetManager(tmp_path / "datasets"),
        LocalPythonExecutor(),
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
