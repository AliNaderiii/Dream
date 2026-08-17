"""G3 — every cleaning operation round-trips on a fixture with invariants.

Each test states the expected output shape / dtypes / known values
explicitly, so a silent behaviour change in the generated cleaning script
fails loudly.
"""

from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")

from dream.skills.data_science import DataScienceError  # noqa: E402
from tests._data_science_helpers import make_runtime  # noqa: E402


@pytest.fixture()
def runtime(tmp_path):
    return make_runtime(tmp_path)


def load_csv(runtime, tmp_path, text, name="fixture.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return runtime.load_data(str(path))["dataset_id"]


def test_drop_na(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "a,b\n1,x\n,y\n3,\n4,w\n")
    out = runtime.clean_data(ds, [{"op": "drop_na"}])
    assert out["rows_before"] == 4 and out["rows_after"] == 2
    values = [row["a"] for row in out["preview"]]
    assert values == [1, 4]


def test_drop_na_subset(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "a,b\n1,x\n,y\n3,\n")
    out = runtime.clean_data(ds, [{"op": "drop_na", "columns": ["b"]}])
    assert out["rows_after"] == 2  # only the b-missing row dropped


def test_fill_na_mean_median_constant(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "a,b\n1,u\n,v\n3,\n")
    out = runtime.clean_data(
        ds,
        [
            {"op": "fill_na", "column": "a", "strategy": "mean"},
            {"op": "fill_na", "column": "b", "strategy": "constant", "value": "zz"},
        ],
    )
    assert out["rows_after"] == 3
    a_values = [row["a"] for row in out["preview"]]
    assert a_values == [1.0, 2.0, 3.0]  # mean of {1,3} = 2
    assert [row["b"] for row in out["preview"]] == ["u", "v", "zz"]


def test_convert_dtype_datetime_and_int(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "d,n\n2024-01-05,1.0\n2024-02-06,2.0\n")
    out = runtime.clean_data(
        ds,
        [
            {"op": "convert_dtype", "column": "d", "dtype": "datetime"},
            {"op": "convert_dtype", "column": "n", "dtype": "int"},
        ],
    )
    assert out["dtypes"]["d"].startswith("datetime64")
    assert out["dtypes"]["n"] == "Int64"
    assert out["preview"][0]["d"].startswith("2024-01-05")


def test_remove_duplicates(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "a,b\n1,x\n1,x\n2,y\n1,z\n")
    out = runtime.clean_data(ds, [{"op": "remove_duplicates"}])
    assert out["rows_after"] == 3
    subset = runtime.clean_data(ds, [{"op": "remove_duplicates", "columns": ["a"]}])
    assert subset["rows_after"] == 2  # a=1 kept once, a=2


def test_rename_and_drop_column(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "a,b,c\n1,2,3\n")
    out = runtime.clean_data(
        ds,
        [
            {"op": "rename_column", "column": "a", "new_name": "alpha"},
            {"op": "drop_column", "column": "c"},
        ],
    )
    assert out["columns"] == ["alpha", "b"]
    # After rename, later ops must validate against the *new* schema.
    out2 = runtime.clean_data(ds, [{"op": "drop_column", "column": "alpha"}])
    assert out2["columns"] == ["b"]


def test_filter_rows_operators(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "n,s\n1,apple\n5,banana\n9,apricot\n")
    gt = runtime.clean_data(ds, [{"op": "filter_rows", "column": "n",
                                  "operator": "gt", "value": 4}])
    assert gt["rows_after"] == 2
    # cleaned.csv became the active file — reload fresh for each operator
    contains = runtime.clean_data(ds, [{"op": "filter_rows", "column": "s",
                                        "operator": "contains", "value": "ban"}])
    assert contains["rows_after"] == 1


def test_filter_rows_in_and_not_null(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "n,s\n1,a\n2,\n3,c\n")
    out = runtime.clean_data(
        ds,
        [
            {"op": "filter_rows", "column": "s", "operator": "not_null"},
            {"op": "filter_rows", "column": "n", "operator": "in", "value": [1, 3]},
        ],
    )
    assert out["rows_after"] == 2


def test_normalize_column_minmax_and_zscore(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "v\n0\n5\n10\n")
    out = runtime.clean_data(ds, [{"op": "normalize_column", "column": "v",
                                   "method": "minmax"}])
    assert [row["v"] for row in out["preview"]] == [0.0, 0.5, 1.0]
    z = runtime.clean_data(ds, [{"op": "normalize_column", "column": "v",
                                 "method": "zscore"}])
    values = [row["v"] for row in z["preview"]]
    assert abs(sum(values)) < 1e-9  # zero-centred


def test_encode_categorical_onehot(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "color,v\nred,1\nblue,2\nred,3\n")
    out = runtime.clean_data(ds, [{"op": "encode_categorical", "column": "color",
                                   "method": "onehot"}])
    assert "color" not in out["columns"]
    assert "color_red" in out["columns"] and "color_blue" in out["columns"]
    assert out["preview"][0]["color_red"] == 1
    assert out["preview"][1]["color_red"] == 0


def test_encode_categorical_label(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "color\nred\nblue\nred\n")
    out = runtime.clean_data(ds, [{"op": "encode_categorical", "column": "color",
                                   "method": "label"}])
    values = [row["color"] for row in out["preview"]]
    assert values[0] == values[2] and values[0] != values[1]


def test_handle_outliers_clip_and_drop(runtime, tmp_path):
    body = "v\n" + "\n".join(str(v) for v in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 1000]) + "\n"
    ds = load_csv(runtime, tmp_path, body)
    clipped = runtime.clean_data(ds, [{"op": "handle_outliers", "column": "v",
                                       "detect": "iqr", "action": "clip"}])
    assert clipped["rows_after"] == 11
    assert max(row["v"] for row in clipped["preview"]) < 1000
    ds2 = load_csv(runtime, tmp_path, body, name="second.csv")
    dropped = runtime.clean_data(ds2, [{"op": "handle_outliers", "column": "v",
                                        "detect": "zscore", "action": "drop",
                                        "threshold": 3.0}])
    assert dropped["rows_after"] == 10


def test_clean_writes_cleaned_csv_and_updates_registry(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "a\n1\n\n3\n")
    runtime.clean_data(ds, [{"op": "drop_na"}])
    record = runtime.datasets.get(ds)
    assert record.cleaned is True
    assert record.active_file == "cleaned.csv"
    assert (runtime.datasets.dir_for(record) / "cleaned.csv").exists()
    # Subsequent profile runs against the cleaned file.
    assert runtime.profile_data(ds)["row_count"] == 2


def test_clean_rejects_unknown_column_before_sandbox(runtime, tmp_path):
    ds = load_csv(runtime, tmp_path, "a\n1\n")
    with pytest.raises(DataScienceError, match="not in the dataset schema"):
        runtime.clean_data(ds, [{"op": "drop_column", "column": "nope"}])
    with pytest.raises(DataScienceError, match="non-empty list"):
        runtime.clean_data(ds, [])
    with pytest.raises(DataScienceError, match="at most 50"):
        runtime.clean_data(ds, [{"op": "drop_na"}] * 51)
