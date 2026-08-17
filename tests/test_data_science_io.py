"""G1 — every supported format loads through the sandboxed loader.

One fixture per format: CSV, TSV, Excel, JSON, YAML, XML, SQLite, Parquet.
Auto-detection is covered separately in test_data_science.py; here each
fixture goes through the full ``load_data`` round trip and must come back
with the right shape, columns, and preview rows.
"""

from __future__ import annotations

import json
import sqlite3

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
