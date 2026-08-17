"""G2 — profiling agrees with hand-computed references to within 1e-9.

The reference values below are computed by hand (and cross-checked against
the statistics definitions, not against pandas), so a regression in the
generated profiling script cannot hide behind "the library said so".
"""

from __future__ import annotations

import math

import pytest

pd = pytest.importorskip("pandas")

from tests._data_science_helpers import make_runtime  # noqa: E402

# Fixture: values 1..10 plus one hand-planted outlier.
VALUES = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 100.0]

# Hand-computed references (n=11):
REF_MEAN = sum(VALUES) / 11  # 155/11
REF_MEDIAN = 6.0
# Sample std (ddof=1): sqrt(sum((x-mean)^2) / 10)
REF_STD = math.sqrt(sum((v - REF_MEAN) ** 2 for v in VALUES) / 10)
# Quartiles with linear interpolation (pandas default, type 7):
# q1 at position 0.25*(11-1)=2.5 -> 3 + 0.5*(4-3) = 3.5
# q3 at position 0.75*10=7.5 -> 8 + 0.5*(9-8) = 8.5
REF_Q1, REF_Q3 = 3.5, 8.5
# IQR fence: 8.5 + 1.5*5 = 16 -> only 100 is above. Lower fence 3.5-7.5=-4.
REF_IQR_OUTLIERS = 1


@pytest.fixture()
def runtime(tmp_path):
    return make_runtime(tmp_path)


@pytest.fixture()
def dataset(runtime, tmp_path):
    path = tmp_path / "ref.csv"
    lines = ["v,label"]
    for i, v in enumerate(VALUES):
        lines.append(f"{v},{'a' if i % 2 == 0 else 'b'}")
    lines.append(",missing_row")  # one missing numeric value
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return runtime.load_data(str(path))["dataset_id"]


def test_numeric_stats_match_hand_computed_reference(runtime, dataset):
    profile = runtime.profile_data(dataset)
    stats = profile["columns"]["v"]
    assert stats["count"] == 11
    assert abs(stats["mean"] - REF_MEAN) < 1e-9
    assert abs(stats["median"] - REF_MEDIAN) < 1e-9
    assert abs(stats["std"] - REF_STD) < 1e-9
    assert abs(stats["q1"] - REF_Q1) < 1e-9
    assert abs(stats["q3"] - REF_Q3) < 1e-9
    assert abs(stats["min"] - 1.0) < 1e-9
    assert abs(stats["max"] - 100.0) < 1e-9


def test_iqr_outlier_detection_matches_ground_truth(runtime, dataset):
    profile = runtime.profile_data(dataset)
    assert profile["columns"]["v"]["outliers_iqr"] == REF_IQR_OUTLIERS


def test_zscore_outlier_detection_on_synthetic_fixture(runtime, tmp_path):
    # 100 points at ~N(0,1) plus one at 50: exactly one |z| > 3.
    values = [((i % 21) - 10) / 10.0 for i in range(100)] + [50.0]
    path = tmp_path / "z.csv"
    path.write_text("x\n" + "\n".join(str(v) for v in values) + "\n", encoding="utf-8")
    dataset_id = runtime.load_data(str(path))["dataset_id"]
    profile = runtime.profile_data(dataset_id)
    assert profile["columns"]["x"]["outliers_zscore"] == 1


def test_missing_and_duplicate_accounting(runtime, dataset):
    profile = runtime.profile_data(dataset)
    assert profile["row_count"] == 12
    assert profile["columns"]["v"]["missing"] == 1
    assert abs(profile["columns"]["v"]["missing_pct"] - 100.0 / 12.0) < 1e-9
    assert profile["duplicate_rows"] == 0


def test_categorical_profile_reports_top_values(runtime, dataset):
    profile = runtime.profile_data(dataset)
    label = profile["columns"]["label"]
    assert label["role"] in ("categorical", "text")
    top = {entry["value"]: entry["count"] for entry in label["top_values"]}
    assert top["a"] == 6 and top["b"] == 5 and top["missing_row"] == 1


def test_histogram_present_for_numeric_columns(runtime, dataset):
    profile = runtime.profile_data(dataset)
    hist = profile["columns"]["v"]["histogram"]
    assert sum(hist["counts"]) == 11
    assert len(hist["edges"]) == len(hist["counts"]) + 1


def test_profile_validates_max_categories(runtime, dataset):
    from dream.skills.data_science import DataScienceError

    with pytest.raises(DataScienceError, match="max_categories"):
        runtime.profile_data(dataset, max_categories=0)


def test_boolean_and_datetime_roles(runtime, tmp_path):
    path = tmp_path / "roles.csv"
    path.write_text(
        "flag,when\ntrue,2024-01-01\nfalse,2024-02-01\ntrue,2024-03-01\n",
        encoding="utf-8",
    )
    dataset_id = runtime.load_data(str(path))["dataset_id"]
    runtime.clean_data(
        dataset_id,
        [
            {"op": "convert_dtype", "column": "flag", "dtype": "bool"},
            {"op": "convert_dtype", "column": "when", "dtype": "datetime"},
        ],
    )
    profile = runtime.profile_data(dataset_id)
    assert profile["columns"]["flag"]["role"] == "boolean"
    assert profile["columns"]["when"]["role"] == "datetime"
    assert profile["columns"]["when"]["min"].startswith("2024-01-01")
