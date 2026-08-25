"""Bounded, dependency-free readers used by discovery and the guarded worker.

CSV, TSV, JSON/JSONL, simple YAML and SQLite are available offline.  Formats
that require optional data-science dependencies are discovered but reported as
unavailable rather than guessed at.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

SUPPORTED_SUFFIXES: dict[str, str] = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".tab": "tsv",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".db": "sqlite",
    ".sqlite": "sqlite",
    ".sqlite3": "sqlite",
    ".xlsx": "excel",
    ".xls": "excel",
    ".parquet": "parquet",
    ".pq": "parquet",
    ".xml": "xml",
}
LOADABLE_FORMATS = frozenset({"csv", "tsv", "json", "jsonl", "yaml", "sqlite"})
MAX_COLUMNS = 256
MAX_CELL_CHARS = 20_000
MAX_EAGER_FILE_BYTES = 16 * 1024 * 1024
MAX_JSONL_RECORD_CHARS = 2 * 1024 * 1024
MAX_SAMPLE_BYTES = 16 * 1024 * 1024
_SAFE_TABLE = re.compile(r"^[^\x00-\x1f]{1,128}$")

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_NULLS = frozenset({"", "null", "none", "nan", "na", "n/a", "-"})


class DataReadError(ValueError):
    """A bounded reader could not safely load a dataset."""


def detect_format(path: Path) -> str | None:
    return SUPPORTED_SUFFIXES.get(path.suffix.lower())


def sniff_encoding(path: Path, sample_bytes: int = 65_536) -> str:
    head = path.open("rb").read(sample_bytes)
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        try:
            head.decode("cp1256")
        except UnicodeDecodeError as exc:
            raise DataReadError("text is not valid UTF-8 or Windows-1256") from exc
        return "cp1256"
    return "utf-8"


def clean_header(value: Any) -> str:
    name = str(value).strip().lstrip("\ufeff")
    if not name or len(name) > 128 or any(ord(char) < 32 for char in name):
        raise DataReadError("column names must be non-empty, printable, and at most 128 characters")
    return name


def validate_headers(headers: list[Any]) -> list[str]:
    if not headers or len(headers) > MAX_COLUMNS:
        raise DataReadError(f"datasets must have between 1 and {MAX_COLUMNS} columns")
    cleaned = [clean_header(value) for value in headers]
    if len(set(cleaned)) != len(cleaned):
        raise DataReadError("duplicate column names are not supported")
    return cleaned


def coerce_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))[:MAX_CELL_CHARS]
    text = str(value).strip()[:MAX_CELL_CHARS]
    folded = text.translate(_PERSIAN_DIGITS)
    if folded.lower() in _NULLS:
        return None
    lower = folded.lower()
    if lower in {"true", "yes"}:
        return True
    if lower in {"false", "no"}:
        return False
    numeric = folded.replace(",", "")
    if re.fullmatch(r"[-+]?\d+", numeric):
        try:
            return int(numeric)
        except ValueError:
            pass
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)(?:e[-+]?\d+)?", numeric, re.I):
        try:
            return float(numeric)
        except ValueError:
            pass
    return text


def _normalise_row(row: dict[Any, Any], headers: list[str]) -> dict[str, Any]:
    return {header: coerce_scalar(row.get(header)) for header in headers}


def _csv_rows(path: Path, fmt: str) -> Iterator[dict[str, Any]]:
    encoding = sniff_encoding(path)
    previous_limit = csv.field_size_limit()
    csv.field_size_limit(MAX_CELL_CHARS)
    try:
        with path.open("r", encoding=encoding, newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t" if fmt == "tsv" else ",")
            raw_headers = list(reader.fieldnames or [])
            headers = validate_headers(raw_headers)
            rename = dict(zip(raw_headers, headers, strict=True))
            for row in reader:
                converted = {rename[key]: value for key, value in row.items() if key in rename}
                yield _normalise_row(converted, headers)
    except csv.Error as exc:
        raise DataReadError(f"cannot safely parse delimited data: {exc}") from exc
    finally:
        csv.field_size_limit(previous_limit)


def _json_rows(path: Path, fmt: str) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding=sniff_encoding(path)) as handle:
        if fmt == "jsonl":

            def jsonl_values() -> Iterator[Any]:
                while line := handle.readline(MAX_JSONL_RECORD_CHARS + 1):
                    if len(line) > MAX_JSONL_RECORD_CHARS:
                        raise DataReadError("JSONL record exceeds the interactive size limit")
                    if line.strip():
                        yield json.loads(line)

            values = jsonl_values()
        else:
            parsed = json.load(handle)
            if isinstance(parsed, dict):
                for key in ("data", "rows", "records", "items"):
                    if isinstance(parsed.get(key), list):
                        parsed = parsed[key]
                        break
                else:
                    parsed = [parsed]
            if not isinstance(parsed, list):
                raise DataReadError("JSON must contain an object or an array of objects")
            values = iter(parsed)
        headers: list[str] | None = None
        for value in values:
            if not isinstance(value, dict):
                raise DataReadError("every JSON record must be an object")
            if headers is None:
                headers = validate_headers(list(value))
            yield {header: coerce_scalar(value.get(header)) for header in headers}


def _yaml_scalar(value: str) -> Any:
    stripped = value.strip().strip("'\"")
    return coerce_scalar(stripped)


def _yaml_rows(path: Path) -> Iterator[dict[str, Any]]:
    """Read the safe list-of-flat-mappings subset without constructing objects."""
    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in path.read_text(encoding=sniff_encoding(path)).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            current = {}
            rows.append(current)
            line = line[2:].strip()
        if current is None or ":" not in line:
            raise DataReadError("YAML support is limited to a list of flat mappings")
        key, _, value = line.partition(":")
        current[clean_header(key)] = _yaml_scalar(value)
    if not rows:
        raise DataReadError("YAML contains no rows")
    headers = validate_headers(list(rows[0]))
    for row in rows:
        yield {header: coerce_scalar(row.get(header)) for header in headers}


def _sqlite_rows(path: Path) -> Iterator[dict[str, Any]]:
    # ``as_uri`` percent-encodes query delimiters in hostile filenames; mode=ro
    # and immutable prevent journal/WAL writes from an interactive read.
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only=ON")
    except sqlite3.Error as exc:
        raise DataReadError(f"cannot open SQLite dataset: {exc}") from exc
    try:
        found = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name LIMIT 1"
        ).fetchone()
        if not found or not _SAFE_TABLE.fullmatch(str(found[0])):
            raise DataReadError("SQLite dataset contains no safe user table")
        table = str(found[0]).replace('"', '""')
        cursor = connection.execute(f'SELECT * FROM "{table}"')
        headers = validate_headers([item[0] for item in cursor.description or []])
        for values in cursor:
            yield {name: coerce_scalar(value) for name, value in zip(headers, values, strict=True)}
    except sqlite3.Error as exc:
        raise DataReadError(f"cannot read SQLite dataset: {exc}") from exc
    finally:
        connection.close()


def iter_rows(path: Path, fmt: str, *, max_rows: int = 250_000) -> Iterator[dict[str, Any]]:
    if fmt not in LOADABLE_FORMATS:
        raise DataReadError(
            f"{fmt} needs an optional data-science reader; convert it to CSV/JSON "
            "or use the registry"
        )
    if max_rows < 1:
        return
    if fmt in {"json", "yaml"} and path.stat().st_size > MAX_EAGER_FILE_BYTES:
        size_mib = MAX_EAGER_FILE_BYTES // (1024 * 1024)
        raise DataReadError(
            f"{fmt.upper()} exceeds the {size_mib} MiB eager-reader limit; "
            "use CSV or JSONL for larger data"
        )
    if fmt in {"csv", "tsv"}:
        source = _csv_rows(path, fmt)
    elif fmt in {"json", "jsonl"}:
        source = _json_rows(path, fmt)
    elif fmt == "yaml":
        source = _yaml_rows(path)
    else:
        source = _sqlite_rows(path)
    try:
        for index, row in enumerate(source):
            if index >= max_rows:
                raise DataReadError(f"dataset exceeds the {max_rows:,}-row interactive limit")
            yield row
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise DataReadError(f"cannot safely parse {fmt} data: {exc}") from exc


def sample_rows(path: Path, fmt: str, *, limit: int = 5_000) -> tuple[list[dict[str, Any]], bool]:
    """Return a row- and memory-bounded sample plus whether more data exists."""
    rows: list[dict[str, Any]] = []
    retained_bytes = 0
    iterator = iter_rows(path, fmt, max_rows=limit + 1)
    try:
        for row in iterator:
            row_bytes = sum(
                len(value.encode("utf-8")) if isinstance(value, str) else 16
                for value in row.values()
            )
            if rows and retained_bytes + row_bytes > MAX_SAMPLE_BYTES:
                return rows, True
            rows.append(row)
            retained_bytes += row_bytes
    except DataReadError as exc:
        # The max_rows sentinel means the first ``limit`` rows are still a valid sample.
        if "interactive limit" not in str(exc):
            raise
    return rows[:limit], len(rows) > limit
