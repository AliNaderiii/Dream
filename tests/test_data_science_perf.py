"""G10 — performance floor: 1 MB CSV loads < 3s, profile < 10s, chart < 3s.

Wall-clock budgets are generous multiples of what the pipeline needs on a
developer laptop, so they catch algorithmic regressions (accidental O(n²)
paths, frame copies per operation) rather than machine variance.
"""

from __future__ import annotations

import time

import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("matplotlib")

from tests._data_science_helpers import make_runtime  # noqa: E402


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("perf")
    runtime = make_runtime(tmp_path)
    path = tmp_path / "big.csv"
    with path.open("w", encoding="utf-8") as fh:
        fh.write("region,price,quantity,invoice_date\n")
        row = 0
        while fh.tell() < 1_048_576:
            fh.write(
                f"r{row % 5},{10 + row % 97}.{row % 100:02d},{row % 9},"
                f"2024-{(row % 12) + 1:02d}-{(row % 28) + 1:02d}\n"
            )
            row += 1
    assert path.stat().st_size >= 1_048_576
    return runtime, path


def test_one_megabyte_csv_loads_under_three_seconds(env):
    runtime, path = env
    started = time.monotonic()
    result = runtime.load_data(str(path), "perf")
    elapsed = time.monotonic() - started
    assert result["shape"][0] > 20_000
    assert elapsed < 3.0, f"load took {elapsed:.2f}s"
    env_state["dataset_id"] = result["dataset_id"]


env_state: dict[str, str] = {}


def test_profile_under_ten_seconds(env):
    runtime, _ = env
    started = time.monotonic()
    profile = runtime.profile_data(env_state["dataset_id"])
    elapsed = time.monotonic() - started
    assert profile["row_count"] > 20_000
    assert elapsed < 10.0, f"profile took {elapsed:.2f}s"


def test_chart_render_under_three_seconds(env):
    runtime, _ = env
    started = time.monotonic()
    chart = runtime.create_chart({
        "type": "bar", "dataset_id": env_state["dataset_id"],
        "x": "region", "y": "price",
    })
    elapsed = time.monotonic() - started
    assert chart["sizes"]["png"] > 0
    assert elapsed < 3.0, f"chart took {elapsed:.2f}s"
