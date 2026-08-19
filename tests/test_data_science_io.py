"""G1 — every supported format loads through the sandboxed loader.

One fixture per format: CSV, TSV, Excel, JSON, YAML, XML, SQLite, Parquet.
Auto-detection is covered separately in test_data_science.py; here each
fixture goes through the full ``load_data`` round trip and must come back
with the right shape, columns, and preview rows.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

from tests._data_science_helpers import make_runtime  # noqa: E402

ROWS = [
    {"name": "ada", "score": 90, "passed": True},
    {"name": "grace", "score": 82, "passed": True},
    {"name": "linus", "score": 55, "passed": False},
]


@pytest.fixture()
def runtime(tmp_path):
    return make_runtime(tmp_path)


def check(result):
    assert result["shape"] == [3, 3]
    assert set(result["columns"]) == {"name", "score", "passed"}
    assert len(result["preview"]) == 3
    names = {row["name"] for row in result["preview"]}
    assert names == {"ada", "grace", "linus"}
    return result


def test_load_csv(runtime, tmp_path):
    path = tmp_path / "d.csv"
    pd.DataFrame(ROWS).to_csv(path, index=False)
    result = check(runtime.load_data(str(path)))
    assert result["format"] == "csv"
    assert result["memory_bytes"] > 0


def test_load_tsv(runtime, tmp_path):
    path = tmp_path / "d.tsv"
    pd.DataFrame(ROWS).to_csv(path, index=False, sep="\t")
    assert check(runtime.load_data(str(path)))["format"] == "tsv"


def test_load_excel_xlsx(runtime, tmp_path):
    pytest.importorskip("openpyxl")
    path = tmp_path / "d.xlsx"
    pd.DataFrame(ROWS).to_excel(path, index=False)
    assert check(runtime.load_data(str(path)))["format"] == "excel"


def test_load_json(runtime, tmp_path):
    path = tmp_path / "d.json"
    path.write_text(json.dumps(ROWS), encoding="utf-8")
    assert check(runtime.load_data(str(path)))["format"] == "json"


def test_load_yaml(runtime, tmp_path):
    path = tmp_path / "d.yaml"
    lines = []
    for row in ROWS:
        lines.append(f"- name: {row['name']}")
        lines.append(f"  score: {row['score']}")
        lines.append(f"  passed: {str(row['passed']).lower()}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert check(runtime.load_data(str(path)))["format"] == "yaml"


def test_load_xml(runtime, tmp_path):
    pytest.importorskip("lxml")
    path = tmp_path / "d.xml"
    items = "".join(
        f"<row><name>{r['name']}</name><score>{r['score']}</score>"
        f"<passed>{str(r['passed']).lower()}</passed></row>"
        for r in ROWS
    )
    path.write_text(f"<?xml version='1.0'?><rows>{items}</rows>", encoding="utf-8")
    assert check(runtime.load_data(str(path)))["format"] == "xml"


def test_load_sqlite(runtime, tmp_path):
    path = tmp_path / "d.sqlite"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE results (name TEXT, score INTEGER, passed BOOLEAN)")
    con.executemany(
        "INSERT INTO results VALUES (?, ?, ?)",
        [(r["name"], r["score"], r["passed"]) for r in ROWS],
    )
    con.commit()
    con.close()
    assert check(runtime.load_data(str(path)))["format"] == "sqlite"


def test_load_parquet(runtime, tmp_path):
    pytest.importorskip("pyarrow")
    path = tmp_path / "d.parquet"
    pd.DataFrame(ROWS).to_parquet(path, index=False)
    assert check(runtime.load_data(str(path)))["format"] == "parquet"


def test_load_registers_dataset_and_copies_source(runtime, tmp_path):
    path = tmp_path / "d.csv"
    pd.DataFrame(ROWS).to_csv(path, index=False)
    result = runtime.load_data(str(path), "grades")
    listed = runtime.list_datasets()
    assert listed[0]["dataset_id"] == result["dataset_id"]
    assert listed[0]["name"] == "grades"
    stored = runtime.datasets.dir_for(runtime.datasets.get(result["dataset_id"]))
    assert (stored / "source.csv").exists()
    # Deleting the original does not break the dataset (registry owns a copy).
    path.unlink()
    profile = runtime.profile_data(result["dataset_id"])
    assert profile["row_count"] == 3


def test_load_failure_rolls_back_registration(runtime, tmp_path):
    path = tmp_path / "broken.parquet"
    path.write_bytes(b"PAR1 this is not a real parquet file")
    from dream.skills.data_science import DataScienceError

    with pytest.raises(DataScienceError):
        runtime.load_data(str(path))
    assert runtime.list_datasets() == []


# --------------------------------------------------------------------------- #
# Iranian office files — encodings, BOM, Persian digits (sandbox round-trip)
# --------------------------------------------------------------------------- #

# تاريخ / شركت / قيمت / مشتري use Arabic yeh/kaf so the body is valid cp1256.
_DATE_AR = "\u062a\u0627\u0631\u064a\u062e"
_DATE_FA = "\u062a\u0627\u0631\u06cc\u062e"
_CO_AR = "\u0634\u0631\u0643\u062a"
_QTY = "\u062a\u0639\u062f\u0627\u062f"
_PRICE_AR = "\u0642\u064a\u0645\u062a"
_PRICE_FA = "\u0642\u06cc\u0645\u062a"
_CUSTOMER_AR = "\u0646\u0627\u0645 \u0645\u0634\u062a\u0631\u064a"

_REPO = Path(__file__).resolve().parents[1]


def test_load_cp1256_csv_byte_level(runtime, tmp_path):
    """A CSV that is actually encoded cp1256 (bytes) loads with the right cells."""
    body = (
        f"{_DATE_AR},{_CUSTOMER_AR},{_QTY},{_PRICE_AR}\n"
        f"1404-01-15,{_CO_AR} 1,2,250000\n"
        f"1404-02-03,{_CO_AR} 2,150,85000\n"
    )
    raw = body.encode("cp1256")
    utf8_rejected = False
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        utf8_rejected = True
    assert utf8_rejected
    path = tmp_path / "office-cp1256.csv"
    path.write_bytes(raw)
    result = runtime.load_data(str(path), "office-cp1256")
    assert result["format"] == "csv"
    assert result["shape"] == [2, 4]
    assert result["columns"][0] == _DATE_AR
    assert _PRICE_AR in result["columns"]
    assert "\ufeff" not in result["columns"][0]
    assert result["preview"][0][_QTY] == 2
    assert result["preview"][1][_PRICE_AR] == 85000


def test_load_utf8_sig_csv_strips_bom(runtime, tmp_path):
    body = "name,score\nada,90\n"
    path = tmp_path / "bom.csv"
    path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    result = runtime.load_data(str(path))
    assert result["format"] == "csv"
    assert result["columns"] == ["name", "score"]
    assert result["preview"][0]["name"] == "ada"
    assert result["preview"][0]["score"] == 90


def test_persian_digits_become_numbers(runtime, tmp_path):
    """Persian digits in numeric cells are Latin digits, then coerced."""
    # ۱۲۳ and ۴۵۶.۷۵
    qty = "\u06f1\u06f2\u06f3"
    price = "\u06f4\u06f5\u06f6.\u06f7\u06f5"
    path = tmp_path / "digits.csv"
    path.write_text(f"qty,price\n{qty},{price}\n", encoding="utf-8")
    result = runtime.load_data(str(path))
    assert result["preview"][0]["qty"] == 123
    assert abs(float(result["preview"][0]["price"]) - 456.75) < 1e-9
    profile = runtime.profile_data(result["dataset_id"])
    assert profile["columns"]["qty"]["role"] == "numeric"
    assert profile["columns"]["price"]["role"] == "numeric"
    assert abs(profile["columns"]["qty"]["mean"] - 123.0) < 1e-9
    assert abs(profile["columns"]["price"]["mean"] - 456.75) < 1e-9


def test_arabic_yeh_header_matches_farsi_yeh_for_clean(runtime, tmp_path):
    """File keeps Arabic yeh on display; clean_data accepts the Farsi spelling."""
    body = f"{_DATE_AR},{_PRICE_AR}\n1404-01-15,10\n"
    path = tmp_path / "yeh.csv"
    path.write_bytes(body.encode("cp1256"))
    ds = runtime.load_data(str(path))["dataset_id"]
    loaded = runtime.list_datasets()[0]
    assert loaded["columns"][0] == _DATE_AR
    out = runtime.clean_data(ds, [{"op": "drop_column", "column": _DATE_FA}])
    assert out["columns"] == [_PRICE_AR]
    # The surviving header is still the file's Arabic-yeh spelling.
    assert out["columns"][0] == _PRICE_AR
    renamed = runtime.clean_data(
        ds, [{"op": "rename_column", "column": _PRICE_FA, "new_name": "price"}]
    )
    assert renamed["columns"] == ["price"]


def test_committed_iranian_examples_load(runtime):
    cp = runtime.load_data(str(_REPO / "examples" / "iranian-sales-cp1256.csv"))
    assert cp["format"] == "csv"
    assert cp["shape"][0] >= 2
    assert _DATE_AR in cp["columns"]
    bom = runtime.load_data(str(_REPO / "examples" / "iranian-sales-utf8-sig.csv"))
    assert bom["format"] == "csv"
    assert bom["shape"][0] >= 2
    assert _DATE_FA in bom["columns"]
    sample = runtime.load_data(str(_REPO / "examples" / "iranian-sales-sample.csv"))
    assert sample["format"] == "csv"
    assert sample["shape"][0] == 10
