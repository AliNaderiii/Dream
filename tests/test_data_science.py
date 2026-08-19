"""Host-side unit tests for the data science pipeline (P-09).

Everything here runs without pandas/scipy: validators, format detection,
auto-chart scoring, and the dataset registry are pure host code by design —
the heavy lifting happens inside the sandbox (see test_data_science_*.py for
the sandboxed round-trips).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dream.skills.data_science import (
    ALLOWED_ANALYSES,
    ALLOWED_CLEAN_OPS,
    ALLOWED_PALETTES,
    ALLOWED_THEMES,
    CHART_TYPES,
    CHUNK_THRESHOLD_BYTES,
    MAX_SOURCE_BYTES,
    DataScienceError,
    DatasetManager,
    DatasetRecord,
    detect_format,
    resolve_column,
    sniff_text_encoding,
    suggest_charts,
    validate_analysis,
    validate_chart_spec,
    validate_clean_op,
)

COLUMNS = ["region", "price", "quantity", "invoice_date", "email"]


# --------------------------------------------------------------------------- #
# detect_format
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("a.csv", "csv"),
        ("a.tsv", "tsv"),
        ("a.xlsx", "excel"),
        ("a.xls", "excel"),
        ("a.json", "json"),
        ("a.yaml", "yaml"),
        ("a.yml", "yaml"),
        ("a.xml", "xml"),
        ("a.db", "sqlite"),
        ("a.sqlite", "sqlite"),
        ("a.parquet", "parquet"),
    ],
)
def test_detect_format_by_extension(tmp_path, filename, expected):
    path = tmp_path / filename
    path.write_bytes(b"placeholder")
    assert detect_format(path) == expected


def test_detect_format_sniffs_sqlite_magic(tmp_path):
    path = tmp_path / "mystery.txt"
    path.write_bytes(b"SQLite format 3\x00" + b"\x00" * 32)
    assert detect_format(path) == "sqlite"


def test_detect_format_sniffs_parquet_magic(tmp_path):
    path = tmp_path / "mystery.dat"
    path.write_bytes(b"PAR1" + b"\x00" * 16)
    assert detect_format(path) == "parquet"


def test_detect_format_sniffs_json_and_xml(tmp_path):
    j = tmp_path / "payload.txt"
    j.write_text('[{"a": 1}]', encoding="utf-8")
    assert detect_format(j) == "json"
    x = tmp_path / "doc.data"
    x.write_text("<?xml version='1.0'?><rows/>", encoding="utf-8")
    assert detect_format(x) == "xml"


def test_detect_format_sniffs_delimiters(tmp_path):
    c = tmp_path / "table.txt"
    c.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    assert detect_format(c) == "csv"
    t = tmp_path / "table2.txt"
    t.write_text("a\tb\tc\n1\t2\t3\n", encoding="utf-8")
    assert detect_format(t) == "tsv"


# --------------------------------------------------------------------------- #
# validate_clean_op — every tag plus the refusal paths
# --------------------------------------------------------------------------- #


def test_all_ten_clean_ops_are_declared():
    assert len(ALLOWED_CLEAN_OPS) == 10


def test_validate_clean_op_rejects_unknown_tag():
    with pytest.raises(DataScienceError, match="unknown cleaning op"):
        validate_clean_op({"op": "exec_code"}, COLUMNS)


def test_validate_clean_op_rejects_absent_column():
    with pytest.raises(DataScienceError, match="not in the dataset schema"):
        validate_clean_op({"op": "drop_column", "column": "ghost"}, COLUMNS)


def test_validate_clean_op_rejects_bad_column_name():
    with pytest.raises(DataScienceError, match=r"\^\[A-Za-z_\]"):
        validate_clean_op({"op": "drop_column", "column": "a; rm -rf /"}, COLUMNS)


def test_validate_clean_op_rejects_overlong_column_name():
    with pytest.raises(DataScienceError, match="64"):
        validate_clean_op({"op": "drop_column", "column": "c" * 65}, COLUMNS)


def test_validate_clean_op_drop_na_variants():
    out = validate_clean_op({"op": "drop_na", "how": "all", "columns": ["email"]}, COLUMNS)
    assert out == {"op": "drop_na", "how": "all", "columns": ["email"]}
    with pytest.raises(DataScienceError, match="how"):
        validate_clean_op({"op": "drop_na", "how": "sometimes"}, COLUMNS)


def test_validate_clean_op_fill_na_requires_constant_value():
    with pytest.raises(DataScienceError, match="requires a value"):
        validate_clean_op({"op": "fill_na", "strategy": "constant"}, COLUMNS)
    out = validate_clean_op(
        {"op": "fill_na", "column": "price", "strategy": "mean"}, COLUMNS
    )
    assert out["strategy"] == "mean"


def test_validate_clean_op_fill_na_rejects_non_scalar_value():
    with pytest.raises(DataScienceError, match="scalar"):
        validate_clean_op(
            {"op": "fill_na", "strategy": "constant", "value": {"__code__": "x"}}, COLUMNS
        )


def test_validate_clean_op_convert_dtype():
    out = validate_clean_op(
        {"op": "convert_dtype", "column": "invoice_date", "dtype": "datetime"}, COLUMNS
    )
    assert out["dtype"] == "datetime"
    with pytest.raises(DataScienceError, match="dtype"):
        validate_clean_op({"op": "convert_dtype", "column": "price", "dtype": "void*"}, COLUMNS)


def test_validate_clean_op_rename_rejects_collision():
    with pytest.raises(DataScienceError, match="already exists"):
        validate_clean_op(
            {"op": "rename_column", "column": "price", "new_name": "quantity"}, COLUMNS
        )


def test_validate_clean_op_filter_rows_operators():
    out = validate_clean_op(
        {"op": "filter_rows", "column": "region", "operator": "in", "value": ["a", "b"]},
        COLUMNS,
    )
    assert out["operator"] == "in"
    with pytest.raises(DataScienceError, match="operator"):
        validate_clean_op(
            {"op": "filter_rows", "column": "region", "operator": "regex", "value": ".*"},
            COLUMNS,
        )
    with pytest.raises(DataScienceError, match="requires a value"):
        validate_clean_op(
            {"op": "filter_rows", "column": "price", "operator": "gt", "value": None}, COLUMNS
        )


def test_validate_clean_op_handle_outliers_threshold_bounds():
    out = validate_clean_op({"op": "handle_outliers", "column": "price"}, COLUMNS)
    assert out["detect"] == "iqr" and out["threshold"] == 1.5
    with pytest.raises(DataScienceError, match="threshold"):
        validate_clean_op(
            {"op": "handle_outliers", "column": "price", "threshold": 999}, COLUMNS
        )


def test_validate_clean_op_normalize_and_encode():
    assert validate_clean_op(
        {"op": "normalize_column", "column": "price", "method": "zscore"}, COLUMNS
    )["method"] == "zscore"
    assert validate_clean_op(
        {"op": "encode_categorical", "column": "region", "method": "label"}, COLUMNS
    )["method"] == "label"
    with pytest.raises(DataScienceError):
        validate_clean_op(
            {"op": "normalize_column", "column": "price", "method": "log"}, COLUMNS
        )


# --------------------------------------------------------------------------- #
# validate_analysis
# --------------------------------------------------------------------------- #


def test_all_nine_analyses_are_declared():
    assert len(ALLOWED_ANALYSES) == 9


def test_validate_analysis_rejects_unknown_kind():
    with pytest.raises(DataScienceError, match="unknown analysis"):
        validate_analysis({"kind": "sql_injection"}, COLUMNS)


def test_validate_analysis_ttest_requires_columns():
    with pytest.raises(DataScienceError, match="requires 'value_column'"):
        validate_analysis({"kind": "ttest", "group_column": "region"}, COLUMNS)
    out = validate_analysis(
        {"kind": "ttest", "value_column": "price", "group_column": "region"}, COLUMNS
    )
    assert out["value_column"] == "price"


def test_validate_analysis_regression_rejects_target_in_features():
    with pytest.raises(DataScienceError, match="target must not be among"):
        validate_analysis(
            {"kind": "linear_regression", "target": "price", "features": ["price"]}, COLUMNS
        )


def test_validate_analysis_kmeans_bounds():
    with pytest.raises(DataScienceError, match="k must be"):
        validate_analysis({"kind": "kmeans", "columns": ["price"], "k": 1}, COLUMNS)
    out = validate_analysis({"kind": "kmeans", "columns": ["price", "quantity"]}, COLUMNS)
    assert out["k"] == 3


def test_validate_analysis_time_series_requires_datetime_column_name():
    out = validate_analysis(
        {
            "kind": "time_series_decompose",
            "datetime_column": "invoice_date",
            "value_column": "price",
            "period": 7,
        },
        COLUMNS,
    )
    assert out["period"] == 7
    with pytest.raises(DataScienceError, match="period"):
        validate_analysis(
            {
                "kind": "time_series_decompose",
                "datetime_column": "invoice_date",
                "value_column": "price",
                "period": 1,
            },
            COLUMNS,
        )


# --------------------------------------------------------------------------- #
# validate_chart_spec
# --------------------------------------------------------------------------- #


def test_all_nine_chart_types_are_declared():
    assert len(CHART_TYPES) == 9


def test_validate_chart_spec_happy_path():
    out = validate_chart_spec(
        {"type": "bar", "x": "region", "y": "price", "theme": "dark", "palette": "Set2"},
        COLUMNS,
    )
    assert out["theme"] == "dark" and out["palette"] == "Set2"
    assert out["width"] == 960 and out["dpi"] == 96


def test_validate_chart_spec_rejects_bad_type_theme_palette():
    with pytest.raises(DataScienceError, match="unknown chart type"):
        validate_chart_spec({"type": "3d-explode", "x": "region"}, COLUMNS)
    with pytest.raises(DataScienceError, match="theme"):
        validate_chart_spec(
            {"type": "bar", "x": "region", "y": "price", "theme": "../evil"}, COLUMNS
        )
    with pytest.raises(DataScienceError, match="palette"):
        validate_chart_spec(
            {"type": "bar", "x": "region", "y": "price", "palette": "../../etc"}, COLUMNS
        )


def test_validate_chart_spec_size_bounds():
    with pytest.raises(DataScienceError, match="width"):
        validate_chart_spec(
            {"type": "bar", "x": "region", "y": "price", "size": {"width": 10_000}}, COLUMNS
        )
    with pytest.raises(DataScienceError, match="dpi"):
        validate_chart_spec(
            {"type": "bar", "x": "region", "y": "price", "size": {"dpi": 1200}}, COLUMNS
        )
    out = validate_chart_spec(
        {
            "type": "bar",
            "x": "region",
            "y": "price",
            "size": {"width": 200, "height": 150, "dpi": 300},
        },
        COLUMNS,
    )
    assert (out["width"], out["height"], out["dpi"]) == (200, 150, 300)


def test_validate_chart_spec_custom_palette_needs_hex_colors():
    with pytest.raises(DataScienceError, match="custom palette"):
        validate_chart_spec(
            {"type": "bar", "x": "region", "y": "price", "palette": "custom"}, COLUMNS
        )
    with pytest.raises(DataScienceError, match="RRGGBB"):
        validate_chart_spec(
            {
                "type": "bar",
                "x": "region",
                "y": "price",
                "palette": "custom",
                "colors": ["javascript:alert(1)"],
            },
            COLUMNS,
        )
    out = validate_chart_spec(
        {
            "type": "bar",
            "x": "region",
            "y": "price",
            "palette": "custom",
            "colors": ["#112233", "#AABBCC"],
        },
        COLUMNS,
    )
    assert out["colors"] == ["#112233", "#AABBCC"]


def test_validate_chart_spec_requires_axes():
    with pytest.raises(DataScienceError, match="requires 'y'"):
        validate_chart_spec({"type": "scatter", "x": "price"}, COLUMNS)
    # heatmap has no axis requirement; histogram needs only x
    assert validate_chart_spec({"type": "heatmap"}, COLUMNS)["type"] == "heatmap"
    assert validate_chart_spec({"type": "histogram", "x": "price"}, COLUMNS)["x"] == "price"


def test_theme_and_palette_allowlists_are_closed():
    assert set(ALLOWED_THEMES) == {"default", "minimal", "dark", "ggplot", "seaborn"}
    assert set(ALLOWED_PALETTES) == {
        "viridis", "plasma", "inferno", "Set1", "Set2", "Pastel1", "custom",
    }


# --------------------------------------------------------------------------- #
# suggest_charts — deterministic scoring
# --------------------------------------------------------------------------- #

SALES_META = [
    {"name": "invoice_date", "role": "datetime", "cardinality": 300},
    {"name": "region", "role": "categorical", "cardinality": 4},
    {"name": "price", "role": "numeric", "cardinality": 400},
    {"name": "quantity", "role": "numeric", "cardinality": 30},
]


def test_suggest_charts_prefers_time_series_line():
    charts = suggest_charts(SALES_META, max_charts=3)
    assert charts[0]["type"] == "line"
    assert charts[0]["x"] == "invoice_date"


def test_suggest_charts_is_deterministic():
    a = suggest_charts(SALES_META, max_charts=6)
    b = suggest_charts(SALES_META, max_charts=6)
    assert a == b


def test_suggest_charts_ground_truth_choices():
    """Auto-selection picks the canonical chart for canonical column shapes."""
    cases = [
        # (columns, expected top chart type)
        ([{"name": "t", "role": "datetime", "cardinality": 100},
          {"name": "v", "role": "numeric", "cardinality": 90}], "line"),
        ([{"name": "cat", "role": "categorical", "cardinality": 5},
          {"name": "v", "role": "numeric", "cardinality": 90}], "bar"),
        ([{"name": "a", "role": "numeric", "cardinality": 80},
          {"name": "b", "role": "numeric", "cardinality": 70}], "scatter"),
        ([{"name": "v", "role": "numeric", "cardinality": 50}], "histogram"),
        ([{"name": "c", "role": "categorical", "cardinality": 3}], "pie"),
    ]
    for meta, expected in cases:
        top = suggest_charts(meta, max_charts=1)[0]
        assert top["type"] == expected, f"{meta} → {top['type']}, wanted {expected}"


def test_suggest_charts_heatmap_for_many_numerics():
    meta = [{"name": f"n{i}", "role": "numeric", "cardinality": 40} for i in range(4)]
    types = {c["type"] for c in suggest_charts(meta, max_charts=10)}
    assert "heatmap" in types


def test_suggest_charts_bounds_max_charts():
    with pytest.raises(DataScienceError):
        suggest_charts(SALES_META, max_charts=0)
    assert len(suggest_charts(SALES_META, max_charts=2)) == 2


# --------------------------------------------------------------------------- #
# DatasetManager registry
# --------------------------------------------------------------------------- #


def test_dataset_manager_round_trip(tmp_path):
    manager = DatasetManager(tmp_path / "datasets")
    source = tmp_path / "input.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    record = manager.create("demo", source, "csv")
    assert (tmp_path / "datasets" / record.dataset_id / "source.csv").exists()

    # Reload from disk: index.json survives a restart.
    reloaded = DatasetManager(tmp_path / "datasets")
    assert reloaded.get(record.dataset_id).name == "demo"
    assert reloaded.list()[0].dataset_id == record.dataset_id

    assert reloaded.delete(record.dataset_id) is True
    assert not (tmp_path / "datasets" / record.dataset_id).exists()
    with pytest.raises(DataScienceError, match="unknown dataset"):
        reloaded.get(record.dataset_id)


def test_dataset_manager_rejects_malformed_ids(tmp_path):
    manager = DatasetManager(tmp_path / "datasets")
    for bad in ("../../etc/passwd", "short", 42, None, "Z" * 32):
        with pytest.raises(DataScienceError):
            manager.get(bad)


def test_dataset_record_serialisation_round_trip():
    record = DatasetRecord(
        dataset_id="a" * 32,
        name="n",
        filename="f.csv",
        format="csv",
        created_at=123.0,
        active_file="source.csv",
        shape=[10, 2],
        columns=["a", "b"],
        dtypes={"a": "int64"},
        cleaned=True,
    )
    assert DatasetRecord.from_dict(json.loads(json.dumps(record.to_dict()))) == record


def test_dataset_manager_survives_corrupt_index(tmp_path):
    root = tmp_path / "datasets"
    root.mkdir()
    (root / "index.json").write_text("{not json", encoding="utf-8")
    manager = DatasetManager(root)
    assert manager.list() == []


def test_runtime_load_rejects_missing_and_empty_files(tmp_path):
    from dream.skills.data_science import DataScienceRuntime, LocalPythonExecutor

    runtime = DataScienceRuntime(
        DatasetManager(tmp_path / "datasets"), LocalPythonExecutor()
    )
    with pytest.raises(DataScienceError, match="file not found"):
        runtime.load_data(str(tmp_path / "ghost.csv"))
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(DataScienceError, match="empty"):
        runtime.load_data(str(empty))
    with pytest.raises(DataScienceError, match="file_path"):
        runtime.load_data("   ")


def test_register_data_science_tools_registers_and_is_idempotent(tmp_path):
    from dream.skills.data_science import (
        DataScienceRuntime,
        LocalPythonExecutor,
        register_data_science_tools,
    )
    from dream.tools import REGISTRY

    runtime = DataScienceRuntime(
        DatasetManager(tmp_path / "datasets"), LocalPythonExecutor()
    )
    before = dict(REGISTRY)
    try:
        names = register_data_science_tools(runtime)
        assert set(names) == {
            "load_data", "profile_data", "clean_data", "analyze_data",
            "auto_chart", "create_chart", "generate_report",
        }
        assert REGISTRY["load_data"].risk == "guarded"
        assert REGISTRY["profile_data"].risk == "safe"
        # Second registration is a no-op, not a duplicate.
        assert set(register_data_science_tools(runtime)) == set(names)
    finally:
        REGISTRY.clear()
        REGISTRY.update(before)


def test_local_executor_reports_timeout(tmp_path):
    from dream.skills.data_science import LocalPythonExecutor

    result = LocalPythonExecutor().run(
        "import time; time.sleep(30)", Path(tmp_path), timeout=1
    )
    assert result.timed_out is True


# --------------------------------------------------------------------------- #
# Iranian office files — encoding sniff, header fold, size cap (host-side)
# --------------------------------------------------------------------------- #

# تاريخ (Arabic yeh) vs تاریخ (Farsi yeh) — identical on screen, different bytes.
_DATE_AR = "\u062a\u0627\u0631\u064a\u062e"
_DATE_FA = "\u062a\u0627\u0631\u06cc\u062e"
# شركت (Arabic kaf) vs شرکت (Farsi keheh).
_CO_AR = "\u0634\u0631\u0643\u062a"
_CO_FA = "\u0634\u0631\u06a9\u062a"

_REPO = Path(__file__).resolve().parents[1]


def test_sniff_utf8_plain(tmp_path):
    path = tmp_path / "plain.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    assert sniff_text_encoding(path) == "utf-8"


def test_sniff_utf8_sig_bom(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_bytes(b"\xef\xbb\xbf" + b"a,b\n1,2\n")
    assert sniff_text_encoding(path) == "utf-8-sig"


def test_sniff_cp1256_is_byte_level(tmp_path):
    """The fixture is real Windows-1256 bytes, not UTF-8 pretending to be."""
    body = f"{_DATE_AR},{_CO_AR}\n1,2\n"
    raw = body.encode("cp1256")
    utf8_rejected = False
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        utf8_rejected = True
    assert utf8_rejected
    assert raw[:3] != b"\xef\xbb\xbf"
    path = tmp_path / "win.csv"
    path.write_bytes(raw)
    assert sniff_text_encoding(path) == "cp1256"


def test_committed_cp1256_example_is_really_cp1256():
    path = _REPO / "examples" / "iranian-sales-cp1256.csv"
    raw = path.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    utf8_rejected = False
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        utf8_rejected = True
    assert utf8_rejected
    assert sniff_text_encoding(path) == "cp1256"
    assert _DATE_AR in raw.decode("cp1256")


def test_committed_utf8_sig_example_has_bom():
    path = _REPO / "examples" / "iranian-sales-utf8-sig.csv"
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert sniff_text_encoding(path) == "utf-8-sig"
    assert _DATE_FA in raw.decode("utf-8-sig")


def test_resolve_column_folds_arabic_yeh_without_rewriting_display():
    """Displayed headers keep the file's yeh/kaf; only matching is folded."""
    assert _DATE_AR != _DATE_FA
    assert resolve_column(_DATE_FA, [_DATE_AR, "qty"]) == _DATE_AR
    assert "\u064a" in _DATE_AR
    assert "\u06cc" not in _DATE_AR


def test_resolve_column_folds_arabic_kaf_without_rewriting_display():
    assert _CO_AR != _CO_FA
    assert resolve_column(_CO_FA, [_CO_AR]) == _CO_AR
    assert resolve_column(_CO_AR, [_CO_AR]) == _CO_AR


def test_resolve_column_exact_match_wins_before_fold():
    assert resolve_column(_DATE_AR, [_DATE_AR, _DATE_FA]) == _DATE_AR
    assert resolve_column(_DATE_FA, [_DATE_AR, _DATE_FA]) == _DATE_FA


def test_validate_clean_op_matches_folded_persian_header():
    columns = [_DATE_AR, "qty"]
    out = validate_clean_op({"op": "drop_column", "column": _DATE_FA}, columns)
    assert out["column"] == _DATE_AR


def test_ingestion_cap_stays_500_mb_and_chunk_threshold_100_mb():
    assert MAX_SOURCE_BYTES == 500 * 1024 * 1024
    assert CHUNK_THRESHOLD_BYTES == 100 * 1024 * 1024


def test_load_data_rejects_over_500_mb(tmp_path, monkeypatch):
    path = tmp_path / "huge.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    from dream.skills.data_science import DataScienceRuntime, LocalPythonExecutor

    runtime = DataScienceRuntime(
        DatasetManager(tmp_path / "datasets"), LocalPythonExecutor()
    )
    import os

    original = Path.stat

    def fake_stat(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if self.name == "huge.csv":
            values = list(result)
            values[6] = MAX_SOURCE_BYTES + 1  # st_size
            return os.stat_result(values)
        return result

    monkeypatch.setattr(Path, "stat", fake_stat)
    with pytest.raises(DataScienceError, match="500 MB"):
        runtime.load_data(str(path))
