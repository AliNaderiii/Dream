"""Data science pipeline: sandboxed pandas tools behind a dataset registry.

The agent never touches raw file paths after ingestion and the host never
imports pandas/matplotlib. Every heavy operation is compiled to a small,
parameter-driven Python script that runs inside an executor — by default the
P-08 Docker sandbox (`dream.docker_sandbox`) — with the dataset's directory
mounted read-write. Parameters travel via ``_params.json`` (never string
interpolation into code), results come back via ``_result.json``.

Layout on disk (under ``data/datasets/``)::

    index.json                      dataset registry
    {dataset_id}/source.{ext}       ingested copy of the original file
    {dataset_id}/cleaned.csv        output of clean_data (becomes active)
    {dataset_id}/charts/{id}.{ext}  chart exports (png/svg/pdf/html)
    {dataset_id}/report.pdf|md      generated report
    {dataset_id}/notebooks/*.ipynb  notebooks (see dream.skills.notebooks)

Validation happens host-side against strict allowlists (operation tags,
analysis kinds, chart types, themes, palettes, dtypes, operators) and a
conservative column-name regex, so no request can smuggle code or paths into
the sandbox.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dream.memory import normalize_fa

logger = logging.getLogger(__name__)

__all__ = [
    "ALLOWED_ANALYSES",
    "ALLOWED_CLEAN_OPS",
    "ALLOWED_DPIS",
    "ALLOWED_FORMATS",
    "ALLOWED_PALETTES",
    "ALLOWED_THEMES",
    "CHART_QUOTA_BYTES",
    "CHART_TYPES",
    "COLUMN_NAME_RE",
    "DataScienceError",
    "DataScienceRuntime",
    "DatasetManager",
    "DatasetRecord",
    "ExecResult",
    "LocalPythonExecutor",
    "SandboxCodeExecutor",
    "detect_format",
    "register_data_science_tools",
    "resolve_column",
    "sniff_text_encoding",
    "suggest_charts",
    "validate_analysis",
    "validate_chart_spec",
    "validate_clean_op",
]

# --------------------------------------------------------------------------- #
# Constants & validation tables
# --------------------------------------------------------------------------- #

#: Column names accepted anywhere in a request (G9: no injection vector).
COLUMN_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: Iranian office headers: Persian letters, ZWNJ, spaces, light punctuation
#: (unit-price-in-rial style). Path/injection characters stay forbidden.
_OFFICE_HEADER_RE = re.compile(
    r"^[\w\u0600-\u06FF\u200c][\w\u0600-\u06FF\u200c ()%.\-]*$",
    re.UNICODE,
)
MAX_COLUMN_NAME_LEN = 64
#: Text encodings ``load_data`` will sniff for CSV/TSV office exports.
SUPPORTED_TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "cp1256")

ALLOWED_FORMATS = ("csv", "tsv", "excel", "json", "yaml", "xml", "sqlite", "parquet")

ALLOWED_CLEAN_OPS = (
    "drop_na",
    "fill_na",
    "convert_dtype",
    "remove_duplicates",
    "rename_column",
    "drop_column",
    "filter_rows",
    "normalize_column",
    "encode_categorical",
    "handle_outliers",
)

ALLOWED_ANALYSES = (
    "correlation",
    "ttest",
    "anova",
    "chi_square",
    "linear_regression",
    "logistic_regression",
    "kmeans",
    "pca",
    "time_series_decompose",
)

CHART_TYPES = ("line", "bar", "scatter", "histogram", "box", "heatmap", "pie", "area", "bubble")

ALLOWED_THEMES = ("default", "minimal", "dark", "ggplot", "seaborn")

#: Strict palette allowlist — never interpolated as a path or module name.
ALLOWED_PALETTES = ("viridis", "plasma", "inferno", "Set1", "Set2", "Pastel1", "custom")

ALLOWED_DPIS = (72, 96, 150, 300)
MIN_WIDTH, MAX_WIDTH = 200, 4096
MIN_HEIGHT, MAX_HEIGHT = 150, 4096

FILTER_OPERATORS = ("eq", "ne", "gt", "ge", "lt", "le", "contains", "in", "not_in", "not_null")

DTYPES = ("int", "float", "str", "bool", "datetime", "category")

FILL_STRATEGIES = ("mean", "median", "mode", "constant", "ffill", "bfill")
NORMALIZE_METHODS = ("minmax", "zscore")
ENCODE_METHODS = ("onehot", "label")
OUTLIER_DETECT = ("iqr", "zscore")
OUTLIER_ACTIONS = ("clip", "drop")

REPORT_SECTIONS = (
    "abstract",
    "data_summary",
    "methodology",
    "results",
    "discussion",
    "conclusion",
    "references",
)

#: Per-chart export quota (G5/G9: sizes bounded).
CHART_QUOTA_BYTES = 5 * 1024 * 1024
#: Frames larger than this are profiled via chunked aggregation, never loaded whole.
CHUNK_THRESHOLD_BYTES = 100 * 1024 * 1024
#: Hard cap on ingested files.
MAX_SOURCE_BYTES = 500 * 1024 * 1024

_HEX_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class DataScienceError(ValueError):
    """A validation or execution failure with a user-presentable message."""


def _check_column(name: Any, *, what: str = "column") -> str:
    if not isinstance(name, str) or not (
        COLUMN_NAME_RE.match(name) or _OFFICE_HEADER_RE.match(name)
    ):
        raise DataScienceError(
            f"{what} must match ^[A-Za-z_][A-Za-z0-9_]*$ (got {str(name)[:80]!r})"
        )
    if len(name) > MAX_COLUMN_NAME_LEN:
        raise DataScienceError(f"{what} must be at most {MAX_COLUMN_NAME_LEN} characters")
    return name


def resolve_column(name: Any, columns: list[str], *, what: str = "column") -> str:
    """Return the *displayed* schema name that matches ``name``.

    Exact match wins. Otherwise both sides are folded with
    :func:`dream.memory.normalize_fa` (Arabic yeh/kaf, Persian digits).
    Displayed headers are never rewritten.
    """
    checked = _check_column(name, what=what)
    if checked in columns:
        return checked
    folded = normalize_fa(checked)
    hits = [col for col in columns if normalize_fa(col) == folded]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise DataScienceError(
            f"{what} {checked!r} matches more than one column after Persian folding"
        )
    raise DataScienceError(f"{what}: column {checked!r} is not in the dataset schema")


def _check_scalar(value: Any, *, what: str) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise DataScienceError(f"{what} must be a scalar (string, number, boolean, or null)")


# --------------------------------------------------------------------------- #
# Format detection
# --------------------------------------------------------------------------- #

_EXT_FORMAT: dict[str, str] = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".tab": "tsv",
    ".xlsx": "excel",
    ".xls": "excel",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".db": "sqlite",
    ".sqlite": "sqlite",
    ".sqlite3": "sqlite",
    ".parquet": "parquet",
    ".pq": "parquet",
}


def detect_format(path: Path) -> str:
    """Detect a dataset's format from its extension, sniffing ambiguous files.

    Extensions map directly; ``.txt``/unknown extensions are sniffed from the
    first bytes (SQLite/Parquet magic, XML/JSON prologue, then delimiter
    counting for CSV vs TSV).
    """
    ext = path.suffix.lower()
    if ext in _EXT_FORMAT:
        return _EXT_FORMAT[ext]
    try:
        head = path.open("rb").read(4096)
    except OSError as exc:
        raise DataScienceError(f"cannot read {path.name}: {exc}") from exc
    if head.startswith(b"SQLite format 3\x00"):
        return "sqlite"
    if head.startswith(b"PAR1"):
        return "parquet"
    text = head.decode("utf-8", errors="replace").lstrip("\ufeff \t\r\n")
    if text.startswith("<?xml") or text.startswith("<"):
        return "xml"
    if text.startswith("{") or text.startswith("["):
        return "json"
    first_line = text.splitlines()[0] if text.splitlines() else ""
    if first_line.count("\t") > first_line.count(","):
        return "tsv"
    if "," in first_line:
        return "csv"
    if ":" in text:
        return "yaml"
    raise DataScienceError(f"could not detect the format of {path.name}")


def sniff_text_encoding(path: Path, sample_size: int = 65536) -> str:
    """Sniff UTF-8, UTF-8-with-BOM, or Windows-1256 (cp1256) from a sample.

    Host-side, stdlib only — never loads the whole file (the 500 MB cap is
    enforced separately). Valid UTF-8 wins; otherwise the sample is treated
    as Windows Arabic/Persian (cp1256).
    """
    try:
        head = path.open("rb").read(sample_size)
    except OSError as exc:
        raise DataScienceError(f"cannot read {path.name}: {exc}") from exc
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        pass
    else:
        return "utf-8"
    try:
        head.decode("cp1256")
    except UnicodeDecodeError as exc:
        raise DataScienceError(
            f"{path.name} is not valid UTF-8 or Windows-1256 (cp1256)"
        ) from exc
    return "cp1256"


# --------------------------------------------------------------------------- #
# Request validators (host-side, no third-party imports)
# --------------------------------------------------------------------------- #


def validate_clean_op(op: Any, columns: list[str]) -> dict[str, Any]:
    """Validate one CleanOp tagged-union entry against the dataset schema.

    Returns the normalised operation dict. Raises :class:`DataScienceError`
    for unknown tags, malformed arguments, or references to absent columns.
    """
    if not isinstance(op, dict):
        raise DataScienceError("each operation must be an object with an 'op' tag")
    tag = op.get("op")
    if tag not in ALLOWED_CLEAN_OPS:
        raise DataScienceError(f"unknown cleaning op {str(tag)[:40]!r}; allowed: "
                               f"{', '.join(ALLOWED_CLEAN_OPS)}")

    def col(key: str = "column", *, required: bool = True) -> str | None:
        value = op.get(key)
        if value is None:
            if required:
                raise DataScienceError(f"{tag} requires {key!r}")
            return None
        return resolve_column(value, columns, what=key)

    out: dict[str, Any] = {"op": tag}
    if tag == "drop_na":
        how = op.get("how", "any")
        if how not in ("any", "all"):
            raise DataScienceError("drop_na: how must be 'any' or 'all'")
        subset = op.get("columns")
        if subset is not None:
            if not isinstance(subset, list) or not subset:
                raise DataScienceError("drop_na: columns must be a non-empty list")
            subset = [resolve_column(name, columns, what="columns entry") for name in subset]
        out.update(how=how, columns=subset)
    elif tag == "fill_na":
        strategy = op.get("strategy", "constant")
        if strategy not in FILL_STRATEGIES:
            raise DataScienceError(f"fill_na: strategy must be one of {FILL_STRATEGIES}")
        out.update(
            column=col(required=False),
            strategy=strategy,
            value=_check_scalar(op.get("value"), what="fill_na.value"),
        )
        if strategy == "constant" and out["value"] is None:
            raise DataScienceError("fill_na: constant strategy requires a value")
    elif tag == "convert_dtype":
        dtype = op.get("dtype")
        if dtype not in DTYPES:
            raise DataScienceError(f"convert_dtype: dtype must be one of {DTYPES}")
        fmt = op.get("format")
        if fmt is not None and not isinstance(fmt, str):
            raise DataScienceError("convert_dtype: format must be a string")
        if fmt is not None and len(fmt) > 64:
            raise DataScienceError("convert_dtype: format is too long")
        out.update(column=col(), dtype=dtype, format=fmt)
    elif tag == "remove_duplicates":
        subset = op.get("columns")
        if subset is not None:
            if not isinstance(subset, list) or not subset:
                raise DataScienceError("remove_duplicates: columns must be a non-empty list")
            subset = [resolve_column(name, columns, what="columns entry") for name in subset]
        out.update(columns=subset)
    elif tag == "rename_column":
        new_name = op.get("new_name")
        _check_column(new_name, what="new_name")
        if new_name in columns:
            raise DataScienceError(f"rename_column: {new_name!r} already exists")
        out.update(column=col(), new_name=new_name)
    elif tag == "drop_column":
        out.update(column=col())
    elif tag == "filter_rows":
        operator = op.get("operator")
        if operator not in FILTER_OPERATORS:
            raise DataScienceError(f"filter_rows: operator must be one of {FILTER_OPERATORS}")
        value = op.get("value")
        if operator in ("in", "not_in"):
            if not isinstance(value, list) or len(value) > 1000:
                raise DataScienceError("filter_rows: value must be a list of at most 1000 items")
            for item in value:
                _check_scalar(item, what="filter_rows.value item")
        elif operator != "not_null":
            _check_scalar(value, what="filter_rows.value")
            if value is None:
                raise DataScienceError(f"filter_rows: operator {operator} requires a value")
        out.update(column=col(), operator=operator, value=value)
    elif tag == "normalize_column":
        method = op.get("method", "minmax")
        if method not in NORMALIZE_METHODS:
            raise DataScienceError(f"normalize_column: method must be one of {NORMALIZE_METHODS}")
        out.update(column=col(), method=method)
    elif tag == "encode_categorical":
        method = op.get("method", "onehot")
        if method not in ENCODE_METHODS:
            raise DataScienceError(f"encode_categorical: method must be one of {ENCODE_METHODS}")
        out.update(column=col(), method=method)
    elif tag == "handle_outliers":
        detect = op.get("detect", "iqr")
        action = op.get("action", "clip")
        if detect not in OUTLIER_DETECT:
            raise DataScienceError(f"handle_outliers: detect must be one of {OUTLIER_DETECT}")
        if action not in OUTLIER_ACTIONS:
            raise DataScienceError(f"handle_outliers: action must be one of {OUTLIER_ACTIONS}")
        threshold = op.get("threshold", 1.5 if detect == "iqr" else 3.0)
        if not isinstance(threshold, (int, float)) or not 0 < float(threshold) <= 10:
            raise DataScienceError("handle_outliers: threshold must be in (0, 10]")
        out.update(column=col(), detect=detect, action=action, threshold=float(threshold))
    return out


def validate_analysis(analysis: Any, columns: list[str]) -> dict[str, Any]:
    """Validate one Analysis entry (kind + typed column references)."""
    if not isinstance(analysis, dict):
        raise DataScienceError("each analysis must be an object with a 'kind' tag")
    kind = analysis.get("kind")
    if kind not in ALLOWED_ANALYSES:
        raise DataScienceError(
            f"unknown analysis {str(kind)[:40]!r}; allowed: {', '.join(ALLOWED_ANALYSES)}"
        )

    def col(key: str, *, required: bool = True) -> str | None:
        value = analysis.get(key)
        if value is None:
            if required:
                raise DataScienceError(f"{kind} requires {key!r}")
            return None
        return resolve_column(value, columns, what=key)

    def cols(key: str, *, required: bool = False) -> list[str] | None:
        value = analysis.get(key)
        if value is None:
            if required:
                raise DataScienceError(f"{kind} requires {key!r}")
            return None
        if not isinstance(value, list) or not value:
            raise DataScienceError(f"{kind}: {key} must be a non-empty list of columns")
        return [resolve_column(name, columns, what=f"{key} entry") for name in value]

    out: dict[str, Any] = {"kind": kind}
    if kind == "correlation":
        method = analysis.get("method", "pearson")
        if method not in ("pearson", "spearman", "kendall"):
            raise DataScienceError("correlation: method must be pearson, spearman, or kendall")
        out.update(columns=cols("columns"), method=method)
    elif kind in ("ttest", "anova"):
        out.update(value_column=col("value_column"), group_column=col("group_column"))
    elif kind == "chi_square":
        out.update(column_a=col("column_a"), column_b=col("column_b"))
    elif kind in ("linear_regression", "logistic_regression"):
        target = col("target")
        features = cols("features", required=True)
        if target in (features or []):
            raise DataScienceError(f"{kind}: target must not be among the features")
        out.update(target=target, features=features)
    elif kind == "kmeans":
        k = analysis.get("k", 3)
        if not isinstance(k, int) or not 2 <= k <= 50:
            raise DataScienceError("kmeans: k must be an integer in [2, 50]")
        out.update(columns=cols("columns", required=True), k=k)
    elif kind == "pca":
        n = analysis.get("n_components", 2)
        if not isinstance(n, int) or not 1 <= n <= 50:
            raise DataScienceError("pca: n_components must be an integer in [1, 50]")
        out.update(columns=cols("columns", required=True), n_components=n)
    elif kind == "time_series_decompose":
        period = analysis.get("period")
        if period is not None and (not isinstance(period, int) or not 2 <= period <= 100_000):
            raise DataScienceError("time_series_decompose: period must be an integer >= 2")
        out.update(
            datetime_column=col("datetime_column"),
            value_column=col("value_column"),
            period=period,
        )
    return out


def validate_chart_spec(spec: Any, columns: list[str] | None = None) -> dict[str, Any]:
    """Validate a ChartSpec: type, columns, theme, palette, size, dpi.

    ``columns`` narrows the column check to a known schema; pass ``None`` to
    skip schema membership (spec-only validation).
    """
    if not isinstance(spec, dict):
        raise DataScienceError("chart_spec must be an object")
    ctype = spec.get("type")
    if ctype not in CHART_TYPES:
        raise DataScienceError(
            f"unknown chart type {str(ctype)[:40]!r}; allowed: {', '.join(CHART_TYPES)}"
        )

    def col(key: str, *, required: bool) -> str | None:
        value = spec.get(key)
        if value is None:
            if required:
                raise DataScienceError(f"{ctype} chart requires {key!r}")
            return None
        if columns is None:
            return _check_column(value, what=key)
        return resolve_column(value, columns, what=key)

    needs_y = ctype in ("line", "bar", "scatter", "area", "bubble", "box")
    x_required = ctype not in ("heatmap",)
    out: dict[str, Any] = {
        "type": ctype,
        "x": col("x", required=x_required),
        "y": col("y", required=needs_y),
        "color": col("color", required=False),
        "group": col("group", required=False),
        "size_by": col("size_by", required=False) if ctype == "bubble" else None,
    }

    theme = spec.get("theme", "default")
    if theme not in ALLOWED_THEMES:
        raise DataScienceError(f"theme must be one of {ALLOWED_THEMES}")
    palette = spec.get("palette", "viridis")
    if palette not in ALLOWED_PALETTES:
        raise DataScienceError(f"palette must be one of {ALLOWED_PALETTES}")
    custom_colors: list[str] | None = None
    if palette == "custom":
        raw = spec.get("colors")
        if not isinstance(raw, list) or not raw or len(raw) > 32:
            raise DataScienceError("custom palette requires colors: a list of 1-32 hex strings")
        for color in raw:
            if not isinstance(color, str) or not re.match(r"^#[0-9A-Fa-f]{6}$", color):
                raise DataScienceError(f"invalid custom color {str(color)[:20]!r}; use #RRGGBB")
        custom_colors = raw

    size = spec.get("size") or {}
    if not isinstance(size, dict):
        raise DataScienceError("size must be an object {width, height, dpi}")
    width = size.get("width", 960)
    height = size.get("height", 600)
    dpi = size.get("dpi", 96)
    if not isinstance(width, int) or not MIN_WIDTH <= width <= MAX_WIDTH:
        raise DataScienceError(f"size.width must be an integer in [{MIN_WIDTH}, {MAX_WIDTH}]")
    if not isinstance(height, int) or not MIN_HEIGHT <= height <= MAX_HEIGHT:
        raise DataScienceError(f"size.height must be an integer in [{MIN_HEIGHT}, {MAX_HEIGHT}]")
    if dpi not in ALLOWED_DPIS:
        raise DataScienceError(f"size.dpi must be one of {ALLOWED_DPIS}")

    title = spec.get("title")
    if title is not None and (not isinstance(title, str) or len(title) > 200):
        raise DataScienceError("title must be a string of at most 200 characters")
    legend = spec.get("legend", True)
    if not isinstance(legend, bool):
        raise DataScienceError("legend must be a boolean")
    annotations = spec.get("annotations")
    if annotations is not None:
        if not isinstance(annotations, list) or len(annotations) > 20:
            raise DataScienceError("annotations must be a list of at most 20 entries")
        for note in annotations:
            if not isinstance(note, str) or len(note) > 200:
                raise DataScienceError("each annotation must be a string of <= 200 characters")

    out.update(
        theme=theme,
        palette=palette,
        colors=custom_colors,
        width=width,
        height=height,
        dpi=dpi,
        title=title,
        legend=legend,
        annotations=annotations or [],
    )
    return out


# --------------------------------------------------------------------------- #
# Auto chart selection (host-side, deterministic)
# --------------------------------------------------------------------------- #


def suggest_charts(
    columns: list[dict[str, Any]],
    max_charts: int = 6,
) -> list[dict[str, Any]]:
    """Rank chart suggestions from column metadata.

    ``columns`` entries carry ``{name, role, cardinality}`` where role is one
    of ``numeric | categorical | datetime | boolean | text``. The scoring is a
    fixed rubric on (x, y) type pairs and cardinality, so identical metadata
    always yields identical suggestions (G5 determinism).
    """
    if not isinstance(max_charts, int) or not 1 <= max_charts <= 24:
        raise DataScienceError("max_charts must be an integer in [1, 24]")
    numeric = [c for c in columns if c.get("role") == "numeric"]
    categorical = [
        c for c in columns if c.get("role") in ("categorical", "boolean", "text")
        and 0 < int(c.get("cardinality") or 0) <= 50
    ]
    datetimes = [c for c in columns if c.get("role") == "datetime"]

    suggestions: list[tuple[float, dict[str, Any]]] = []

    def add(score: float, spec: dict[str, Any], reason: str) -> None:
        spec = {"theme": "default", "palette": "viridis", **spec}
        suggestions.append((score, {**spec, "score": round(score, 4), "reason": reason}))

    for dt in datetimes:
        for num in numeric:
            add(
                0.95,
                {"type": "line", "x": dt["name"], "y": num["name"]},
                f"{num['name']} over time ({dt['name']})",
            )
    for cat in categorical:
        card = int(cat.get("cardinality") or 0)
        for num in numeric:
            if card <= 20:
                add(
                    0.9 - card * 0.01,
                    {"type": "bar", "x": cat["name"], "y": num["name"]},
                    f"{num['name']} by {cat['name']} ({card} groups)",
                )
            if 2 <= card <= 12:
                add(
                    0.7 - card * 0.01,
                    {"type": "box", "x": cat["name"], "y": num["name"]},
                    f"distribution of {num['name']} across {cat['name']}",
                )
    for i, a in enumerate(numeric):
        for b in numeric[i + 1:]:
            add(
                0.75,
                {"type": "scatter", "x": a["name"], "y": b["name"]},
                f"{a['name']} vs {b['name']}",
            )
    for num in numeric:
        add(0.6, {"type": "histogram", "x": num["name"]}, f"distribution of {num['name']}")
    if len(numeric) >= 3:
        add(0.65, {"type": "heatmap"}, "correlation matrix of numeric columns")
    for cat in categorical:
        card = int(cat.get("cardinality") or 0)
        if 2 <= card <= 6:
            add(0.5, {"type": "pie", "x": cat["name"]}, f"share of {cat['name']}")

    suggestions.sort(key=lambda pair: (-pair[0], pair[1]["type"], pair[1].get("x") or ""))
    return [spec for _, spec in suggestions[:max_charts]]


# --------------------------------------------------------------------------- #
# Executors
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class ExecResult:
    """Outcome of one sandboxed script run."""

    stdout: str = ""
    stderr: str = ""
    return_code: int = -1
    timed_out: bool = False
    elapsed_seconds: float = 0.0


def _await(coro: Any) -> Any:
    """Run a coroutine to completion from sync code, loop or no loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class LocalPythonExecutor:
    """Run scripts with the host interpreter in an isolated subprocess.

    Development/test fallback only: the bridge uses the Docker sandbox by
    default (G9). The subprocess runs with ``-I`` (isolated mode), a working
    directory pinned to the dataset workspace, and no inherited environment
    beyond PATH — but it is *not* a security boundary the way Docker is, so it
    must be opted into explicitly.
    """

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
            proc = subprocess.run(
                [self.python, "-I", str(script)],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            return ExecResult(
                stdout=proc.stdout,
                stderr=proc.stderr,
                return_code=proc.returncode,
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


class SandboxCodeExecutor:
    """Route script execution through the P-08 Docker sandbox.

    The dataset directory is mounted read-write; network stays disabled and
    the container keeps every P-08 hardening flag (cap-drop, seccomp,
    no-new-privileges, pids/memory limits).
    """

    def __init__(self, sandbox: Any, *, memory_mb: int = 2048) -> None:
        self.sandbox = sandbox
        self.memory_mb = memory_mb

    def run(self, code: str, workspace: Path, timeout: int = 120) -> ExecResult:
        from dream.docker_sandbox import ResourceLimits

        limits = ResourceLimits(
            memory_mb=self.memory_mb,
            network_enabled=False,
            timeout_seconds=timeout,
        )
        result = _await(
            self.sandbox.run_code(
                code=code,
                language="python",
                workspace_path=workspace,
                resource_limits=limits,
                mount_workspace_read_write=True,
                timeout=timeout,
            )
        )
        return ExecResult(
            stdout=result.stdout,
            stderr=result.stderr,
            return_code=result.return_code,
            timed_out=result.timed_out,
            elapsed_seconds=result.elapsed_seconds,
        )


# --------------------------------------------------------------------------- #
# Dataset registry
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class DatasetRecord:
    """One registered dataset. Referenced only by id — never by raw path."""

    dataset_id: str
    name: str
    filename: str
    format: str
    created_at: float
    active_file: str = ""
    shape: list[int] = field(default_factory=lambda: [0, 0])
    columns: list[str] = field(default_factory=list)
    dtypes: dict[str, str] = field(default_factory=dict)
    column_meta: list[dict[str, Any]] = field(default_factory=list)
    memory_bytes: int = 0
    cleaned: bool = False
    encoding: str = "utf-8"

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "name": self.name,
            "filename": self.filename,
            "format": self.format,
            "created_at": self.created_at,
            "active_file": self.active_file,
            "shape": self.shape,
            "columns": self.columns,
            "dtypes": self.dtypes,
            "column_meta": self.column_meta,
            "memory_bytes": self.memory_bytes,
            "cleaned": self.cleaned,
            "encoding": self.encoding,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DatasetRecord:
        return cls(
            dataset_id=str(raw["dataset_id"]),
            name=str(raw.get("name", "")),
            filename=str(raw.get("filename", "")),
            format=str(raw.get("format", "csv")),
            created_at=float(raw.get("created_at", 0.0)),
            active_file=str(raw.get("active_file", "")),
            shape=list(raw.get("shape", [0, 0])),
            columns=list(raw.get("columns", [])),
            dtypes=dict(raw.get("dtypes", {})),
            column_meta=list(raw.get("column_meta", [])),
            memory_bytes=int(raw.get("memory_bytes", 0)),
            cleaned=bool(raw.get("cleaned", False)),
            encoding=str(raw.get("encoding", "utf-8")),
        )


class DatasetManager:
    """File-backed dataset registry under ``data/datasets/``."""

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        self.root = Path(root or os.environ.get("DREAM_DATASETS_DIR", "data/datasets"))
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / "index.json"
        self._records: dict[str, DatasetRecord] = {}
        self._load_index()

    def _load_index(self) -> None:
        if not self._index_path.exists():
            return
        try:
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
            for entry in raw.get("datasets", []):
                record = DatasetRecord.from_dict(entry)
                self._records[record.dataset_id] = record
        except (OSError, ValueError, KeyError):
            logger.warning("dataset index unreadable; starting empty", exc_info=True)

    def _save_index(self) -> None:
        payload = {"datasets": [r.to_dict() for r in self._records.values()]}
        tmp = self._index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._index_path)

    def create(
        self, name: str, source: Path, fmt: str, encoding: str = "utf-8"
    ) -> DatasetRecord:
        dataset_id = uuid.uuid4().hex
        dataset_dir = self.root / dataset_id
        dataset_dir.mkdir(parents=True, exist_ok=True)
        stored = dataset_dir / f"source{source.suffix.lower() or '.dat'}"
        shutil.copyfile(source, stored)
        record = DatasetRecord(
            dataset_id=dataset_id,
            name=name or source.stem,
            filename=source.name,
            format=fmt,
            created_at=time.time(),
            active_file=stored.name,
            encoding=encoding,
        )
        self._records[dataset_id] = record
        self._save_index()
        return record

    def get(self, dataset_id: Any) -> DatasetRecord:
        if not isinstance(dataset_id, str) or not _HEX_ID_RE.match(dataset_id):
            raise DataScienceError("dataset_id must be a 32-character hex id")
        record = self._records.get(dataset_id)
        if record is None:
            raise DataScienceError(f"unknown dataset: {dataset_id}")
        return record

    def dir_for(self, record: DatasetRecord) -> Path:
        return self.root / record.dataset_id

    def list(self) -> list[DatasetRecord]:
        return sorted(self._records.values(), key=lambda r: -r.created_at)

    def update(self, record: DatasetRecord) -> None:
        self._records[record.dataset_id] = record
        self._save_index()

    def delete(self, dataset_id: str) -> bool:
        record = self.get(dataset_id)
        shutil.rmtree(self.dir_for(record), ignore_errors=True)
        del self._records[dataset_id]
        self._save_index()
        return True


# --------------------------------------------------------------------------- #
# Script generation
# --------------------------------------------------------------------------- #

# The prelude every generated script shares. Parameters are read from
# ``_params.json`` (written by the host), never interpolated into code.
_PRELUDE = textwrap.dedent(
    """
    import json, math, os, warnings
    warnings.filterwarnings("ignore")
    import numpy as np
    import pandas as pd

    with open("_params.json", encoding="utf-8") as fh:
        P = json.load(fh)

    def _clean(obj):
        if isinstance(obj, dict):
            return {str(k): _clean(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_clean(v) for v in obj]
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating, float)):
            v = float(obj)
            return None if (math.isnan(v) or math.isinf(v)) else v
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (pd.Timestamp,)):
            return obj.isoformat()
        if obj is pd.NaT:
            return None
        return obj

    def emit(obj):
        with open("_result.json", "w", encoding="utf-8") as fh:
            json.dump(_clean(obj), fh, ensure_ascii=False, default=str)

    _FA_DIGIT_MAP = str.maketrans(
        {0x06F0 + i: 48 + i for i in range(10)}
        | {0x0660 + i: 48 + i for i in range(10)}
        | {0x066B: 46, 0x066C: None}
    )

    def fold_fa_cell(value):
        if isinstance(value, str):
            return value.translate(_FA_DIGIT_MAP)
        return value

    def fold_fa_numerics(df):
        # Persian/Arabic digits -> Latin, then coerce a column to numeric
        # only when every non-blank cell converts. Displayed headers are
        # left untouched (yeh/kaf folding is host-side matching only).
        for name in df.columns:
            series = df[name]
            if series.dtype != object and not pd.api.types.is_string_dtype(series):
                continue
            folded = series.map(fold_fa_cell)
            as_num = pd.to_numeric(folded, errors="coerce")
            present = folded.notna()
            blanks = folded.map(lambda v: isinstance(v, str) and not str(v).strip())
            present = present & ~blanks
            if present.any() and as_num[present].notna().all():
                df[name] = as_num
            else:
                df[name] = folded
        return df

    def load_df(path, fmt):
        enc = P.get("encoding") or "utf-8"
        if fmt == "csv":
            df = pd.read_csv(path, encoding=enc)
        elif fmt == "tsv":
            df = pd.read_csv(path, sep="\\t", encoding=enc)
        elif fmt == "excel":
            df = pd.read_excel(path)
        elif fmt == "json":
            try:
                df = pd.read_json(path)
            except ValueError:
                df = pd.json_normalize(json.load(open(path, encoding="utf-8")))
        elif fmt == "yaml":
            try:
                import yaml
                data = yaml.safe_load(open(path, encoding="utf-8"))
            except ImportError:
                data = _mini_yaml(open(path, encoding="utf-8").read())
            df = pd.json_normalize(data)
        elif fmt == "xml":
            df = pd.read_xml(path)
        elif fmt == "sqlite":
            import sqlite3
            con = sqlite3.connect(path)
            try:
                tables = [r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
                if not tables:
                    raise ValueError("sqlite file contains no tables")
                df = pd.read_sql_query(f'SELECT * FROM \\"{tables[0]}\\"', con)
            finally:
                con.close()
        elif fmt == "parquet":
            df = pd.read_parquet(path)
        else:
            raise ValueError(f"unsupported format: {fmt}")
        return fold_fa_numerics(df)


    def _mini_yaml(text):
        # Fallback list-of-flat-mappings parser for fixture-grade YAML when
        # PyYAML is absent. Handles '- key: value' blocks only.
        rows, current = [], None
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("- "):
                current = {}
                rows.append(current)
                stripped = stripped[2:]
            if ":" in stripped and current is not None:
                key, _, value = stripped.partition(":")
                value = value.strip()
                if value.lower() in ("true", "false"):
                    value = value.lower() == "true"
                else:
                    try:
                        value = int(value)
                    except ValueError:
                        try:
                            value = float(value)
                        except ValueError:
                            value = value.strip("'\\\"")
                current[key.strip()] = value
        return rows

    def active_df():
        df = load_df(P["active_file"], P["active_format"])
        # CSV round-trips lose dtype information; re-apply the dtypes the
        # registry recorded after the last clean/convert.
        for name, dtype in (P.get("known_dtypes") or {}).items():
            if name not in df.columns:
                continue
            try:
                if dtype.startswith("datetime64"):
                    df[name] = pd.to_datetime(df[name], errors="coerce")
                elif dtype == "boolean":
                    df[name] = df[name].astype("boolean")
                elif dtype == "category":
                    df[name] = df[name].astype("category")
            except (TypeError, ValueError):
                pass
        return df
    """
).strip()


_COLUMN_META_SNIPPET = textwrap.dedent(
    """
    def column_meta(df):
        meta = []
        for name in df.columns:
            series = df[name]
            if pd.api.types.is_bool_dtype(series):
                role = "boolean"
            elif pd.api.types.is_numeric_dtype(series):
                role = "numeric"
            elif pd.api.types.is_datetime64_any_dtype(series):
                role = "datetime"
            else:
                nunique = int(series.nunique(dropna=True))
                role = "categorical" if nunique <= max(50, len(df) // 20) else "text"
            meta.append({
                "name": str(name),
                "role": role,
                "dtype": str(series.dtype),
                "cardinality": int(series.nunique(dropna=True)),
                "missing": int(series.isna().sum()),
            })
        return meta
    """
).strip()


def _script(body: str) -> str:
    return _PRELUDE + "\n\n" + _COLUMN_META_SNIPPET + "\n\n" + textwrap.dedent(body).strip() + "\n"


_LOAD_BODY = """
df = active_df()
preview = json.loads(df.head(P["preview_rows"]).to_json(orient="records", date_format="iso"))
emit({
    "shape": [int(df.shape[0]), int(df.shape[1])],
    "columns": [str(c) for c in df.columns],
    "dtypes": {str(c): str(t) for c, t in df.dtypes.items()},
    "memory_bytes": int(df.memory_usage(deep=True).sum()),
    "column_meta": column_meta(df),
    "preview": preview,
})
"""

_PROFILE_BODY = """
def numeric_stats(series):
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return {"count": 0}
    q1, med, q3 = (float(values.quantile(q)) for q in (0.25, 0.5, 0.75))
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    std = float(values.std(ddof=1)) if len(values) > 1 else 0.0
    mean = float(values.mean())
    if std > 0:
        z = ((values - mean) / std).abs()
        z_outliers = int((z > 3).sum())
    else:
        z_outliers = 0
    return {
        "count": int(values.count()),
        "mean": mean,
        "std": std,
        "min": float(values.min()),
        "q1": q1,
        "median": med,
        "q3": q3,
        "max": float(values.max()),
        "outliers_iqr": int(((values < lo) | (values > hi)).sum()),
        "outliers_zscore": z_outliers,
    }

if P.get("chunked"):
    # Memory-bound path: single pass of chunked aggregation for numeric
    # moments plus a bounded sample for quantiles. Never materialises the
    # whole frame (files > 100 MB).
    sep = "\\t" if P["active_format"] == "tsv" else ","
    count = {}
    total = {}
    total_sq = {}
    minimum = {}
    maximum = {}
    sample = None
    rows = 0
    for chunk in pd.read_csv(
        P["active_file"], sep=sep, encoding=P.get("encoding") or "utf-8",
        chunksize=100_000,
    ):
        chunk = fold_fa_numerics(chunk)
        rows += len(chunk)
        if sample is None:
            sample = chunk
        numerics = chunk.select_dtypes(include="number")
        for name in numerics.columns:
            values = numerics[name].dropna()
            count[name] = count.get(name, 0) + int(values.count())
            total[name] = total.get(name, 0.0) + float(values.sum())
            total_sq[name] = total_sq.get(name, 0.0) + float((values ** 2).sum())
            if len(values):
                minimum[name] = min(minimum.get(name, float("inf")), float(values.min()))
                maximum[name] = max(maximum.get(name, float("-inf")), float(values.max()))
    df = sample if sample is not None else pd.DataFrame()
    columns = {}
    for name in df.columns:
        series = df[name]
        entry = {"dtype": str(series.dtype), "missing": int(series.isna().sum())}
        if name in count and count[name] > 1:
            n, s, ss = count[name], total[name], total_sq[name]
            mean = s / n
            variance = max((ss - n * mean * mean) / (n - 1), 0.0)
            entry.update({
                "count": n, "mean": mean, "std": variance ** 0.5,
                "min": minimum[name], "max": maximum[name],
                "approximate_quantiles": True,
            })
            entry.update({k: v for k, v in numeric_stats(series).items()
                          if k in ("q1", "median", "q3")})
        columns[str(name)] = entry
    emit({
        "sampled": True,
        "row_count": rows,
        "column_count": int(df.shape[1]),
        "columns": columns,
        "column_meta": column_meta(df),
        "duplicate_rows": None,
        "missing_pct": None,
    })
else:
    df = active_df()
    max_categories = int(P.get("max_categories", 20))
    columns = {}
    for name in df.columns:
        series = df[name]
        entry = {
            "dtype": str(series.dtype),
            "missing": int(series.isna().sum()),
            "missing_pct": float(series.isna().mean() * 100.0),
            "unique": int(series.nunique(dropna=True)),
        }
        if pd.api.types.is_bool_dtype(series):
            entry["role"] = "boolean"
            entry["true_count"] = int(series.fillna(False).sum())
        elif pd.api.types.is_numeric_dtype(series):
            entry["role"] = "numeric"
            entry.update(numeric_stats(series))
        elif pd.api.types.is_datetime64_any_dtype(series):
            entry["role"] = "datetime"
            valid = series.dropna()
            if len(valid):
                entry["min"] = valid.min().isoformat()
                entry["max"] = valid.max().isoformat()
        else:
            entry["role"] = "categorical" if entry["unique"] <= max(50, len(df) // 20) else "text"
            top = series.astype("string").value_counts().head(max_categories)
            entry["top_values"] = [
                {"value": str(v), "count": int(c)} for v, c in top.items()
            ]
            lengths = series.dropna().astype(str).str.len()
            if len(lengths):
                entry["avg_length"] = float(lengths.mean())
        if entry.get("role") == "numeric" and entry.get("count"):
            hist_values = pd.to_numeric(series, errors="coerce").dropna()
            counts, edges = np.histogram(hist_values, bins=min(20, max(5, entry["unique"])))
            entry["histogram"] = {
                "counts": [int(c) for c in counts],
                "edges": [float(e) for e in edges],
            }
        columns[str(name)] = entry
    emit({
        "sampled": False,
        "row_count": int(df.shape[0]),
        "column_count": int(df.shape[1]),
        "duplicate_rows": int(df.duplicated().sum()),
        "missing_pct": float(df.isna().mean().mean() * 100.0) if df.size else 0.0,
        "memory_bytes": int(df.memory_usage(deep=True).sum()),
        "columns": columns,
        "column_meta": column_meta(df),
    })
"""

_CLEAN_BODY = """
df = active_df()
rows_before = int(df.shape[0])
applied = []
for op in P["operations"]:
    tag = op["op"]
    if tag == "drop_na":
        df = df.dropna(how=op.get("how", "any"), subset=op.get("columns") or None)
    elif tag == "fill_na":
        column = op.get("column")
        strategy = op["strategy"]
        targets = [column] if column else list(df.columns)
        for name in targets:
            series = df[name]
            if strategy == "mean" and pd.api.types.is_numeric_dtype(series):
                df[name] = series.fillna(series.mean())
            elif strategy == "median" and pd.api.types.is_numeric_dtype(series):
                df[name] = series.fillna(series.median())
            elif strategy == "mode":
                mode = series.mode(dropna=True)
                if len(mode):
                    df[name] = series.fillna(mode.iloc[0])
            elif strategy == "constant":
                df[name] = series.fillna(op.get("value"))
            elif strategy == "ffill":
                df[name] = series.ffill()
            elif strategy == "bfill":
                df[name] = series.bfill()
    elif tag == "convert_dtype":
        name, dtype = op["column"], op["dtype"]
        if dtype == "datetime":
            df[name] = pd.to_datetime(df[name], format=op.get("format"), errors="coerce")
        elif dtype == "int":
            df[name] = pd.to_numeric(df[name], errors="coerce").astype("Int64")
        elif dtype == "float":
            df[name] = pd.to_numeric(df[name], errors="coerce").astype(float)
        elif dtype == "bool":
            df[name] = df[name].map(
                {True: True, False: False, "true": True, "false": False,
                 "True": True, "False": False, 1: True, 0: False, "1": True, "0": False}
            ).astype("boolean")
        elif dtype == "category":
            df[name] = df[name].astype("category")
        else:
            df[name] = df[name].astype("string")
    elif tag == "remove_duplicates":
        df = df.drop_duplicates(subset=op.get("columns") or None)
    elif tag == "rename_column":
        df = df.rename(columns={op["column"]: op["new_name"]})
    elif tag == "drop_column":
        df = df.drop(columns=[op["column"]])
    elif tag == "filter_rows":
        name, operator, value = op["column"], op["operator"], op.get("value")
        series = df[name]
        if operator == "eq":
            mask = series == value
        elif operator == "ne":
            mask = series != value
        elif operator == "gt":
            mask = series > value
        elif operator == "ge":
            mask = series >= value
        elif operator == "lt":
            mask = series < value
        elif operator == "le":
            mask = series <= value
        elif operator == "contains":
            mask = series.astype("string").str.contains(str(value), regex=False, na=False)
        elif operator == "in":
            mask = series.isin(value)
        elif operator == "not_in":
            mask = ~series.isin(value)
        else:  # not_null
            mask = series.notna()
        df = df[mask]
    elif tag == "normalize_column":
        name = op["column"]
        values = pd.to_numeric(df[name], errors="coerce")
        if op["method"] == "minmax":
            span = values.max() - values.min()
            df[name] = (values - values.min()) / span if span else 0.0
        else:
            std = values.std(ddof=0)
            df[name] = (values - values.mean()) / std if std else 0.0
    elif tag == "encode_categorical":
        name = op["column"]
        if op["method"] == "onehot":
            dummies = pd.get_dummies(df[name], prefix=name, dtype=int)
            df = pd.concat([df.drop(columns=[name]), dummies], axis=1)
        else:
            codes, _ = pd.factorize(df[name], use_na_sentinel=True)
            df[name] = pd.Series(codes, index=df.index).replace(-1, pd.NA).astype("Int64")
    elif tag == "handle_outliers":
        name = op["column"]
        values = pd.to_numeric(df[name], errors="coerce")
        threshold = float(op["threshold"])
        if op["detect"] == "iqr":
            q1, q3 = values.quantile(0.25), values.quantile(0.75)
            iqr = q3 - q1
            lo, hi = q1 - threshold * iqr, q3 + threshold * iqr
        else:
            mean, std = values.mean(), values.std(ddof=1)
            lo, hi = mean - threshold * std, mean + threshold * std
        if op["action"] == "clip":
            df[name] = values.clip(lower=lo, upper=hi)
        else:
            df = df[(values >= lo) & (values <= hi) | values.isna()]
    applied.append(tag)

df.to_csv("cleaned.csv", index=False)
preview = json.loads(df.head(P["preview_rows"]).to_json(orient="records", date_format="iso"))
emit({
    "rows_before": rows_before,
    "rows_after": int(df.shape[0]),
    "shape": [int(df.shape[0]), int(df.shape[1])],
    "columns": [str(c) for c in df.columns],
    "dtypes": {str(c): str(t) for c, t in df.dtypes.items()},
    "column_meta": column_meta(df),
    "operations_applied": applied,
    "preview": preview,
})
"""

_ANALYZE_BODY = """
from scipy import stats as scipy_stats

df = active_df()
results = []

def numeric(series, name):
    values = pd.to_numeric(series, errors="coerce")
    if values.notna().sum() == 0:
        raise ValueError(f"column {name!r} has no numeric values")
    return values

for analysis in P["analyses"]:
    kind = analysis["kind"]
    entry = {"kind": kind}
    try:
        if kind == "correlation":
            columns = analysis.get("columns") or [
                c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])
            ]
            frame = df[columns].apply(lambda s: pd.to_numeric(s, errors="coerce"))
            matrix = frame.corr(method=analysis.get("method", "pearson"))
            entry["columns"] = [str(c) for c in matrix.columns]
            entry["matrix"] = [[None if pd.isna(v) else float(v) for v in row]
                               for row in matrix.values]
        elif kind == "ttest":
            groups = df[analysis["group_column"]].dropna().unique()
            if len(groups) != 2:
                raise ValueError(
                    f"ttest requires a 2-level categorical group column; "
                    f"{analysis['group_column']!r} has {len(groups)} levels")
            a = numeric(df[df[analysis["group_column"]] == groups[0]]
                        [analysis["value_column"]], analysis["value_column"]).dropna()
            b = numeric(df[df[analysis["group_column"]] == groups[1]]
                        [analysis["value_column"]], analysis["value_column"]).dropna()
            stat, pvalue = scipy_stats.ttest_ind(a, b)
            entry.update(groups=[str(groups[0]), str(groups[1])],
                         statistic=float(stat), p_value=float(pvalue),
                         mean_a=float(a.mean()), mean_b=float(b.mean()),
                         n_a=int(len(a)), n_b=int(len(b)))
        elif kind == "anova":
            samples = [numeric(group[analysis["value_column"]],
                               analysis["value_column"]).dropna()
                       for _, group in df.groupby(analysis["group_column"], observed=True)]
            samples = [s for s in samples if len(s) > 1]
            if len(samples) < 2:
                raise ValueError("anova requires at least two groups with n > 1")
            stat, pvalue = scipy_stats.f_oneway(*samples)
            entry.update(statistic=float(stat), p_value=float(pvalue),
                         groups=len(samples))
        elif kind == "chi_square":
            table = pd.crosstab(df[analysis["column_a"]], df[analysis["column_b"]])
            stat, pvalue, dof, _ = scipy_stats.chi2_contingency(table)
            entry.update(statistic=float(stat), p_value=float(pvalue), dof=int(dof),
                         table_shape=[int(v) for v in table.shape])
        elif kind == "linear_regression":
            from sklearn.linear_model import LinearRegression
            frame = df[[analysis["target"], *analysis["features"]]].apply(
                lambda s: pd.to_numeric(s, errors="coerce")).dropna()
            X = frame[analysis["features"]].values
            y = frame[analysis["target"]].values
            model = LinearRegression().fit(X, y)
            entry.update(
                coefficients={f: float(c) for f, c in
                              zip(analysis["features"], model.coef_)},
                intercept=float(model.intercept_),
                r_squared=float(model.score(X, y)),
                n=int(len(frame)))
        elif kind == "logistic_regression":
            from sklearn.linear_model import LogisticRegression
            frame = df[[analysis["target"], *analysis["features"]]].dropna()
            y_raw = frame[analysis["target"]]
            levels = y_raw.unique()
            if len(levels) != 2:
                raise ValueError("logistic_regression requires a binary target")
            X = frame[analysis["features"]].apply(
                lambda s: pd.to_numeric(s, errors="coerce")).dropna()
            frame = frame.loc[X.index]
            y = (frame[analysis["target"]] == levels[1]).astype(int).values
            model = LogisticRegression(max_iter=1000).fit(X.values, y)
            entry.update(
                classes=[str(levels[0]), str(levels[1])],
                coefficients={f: float(c) for f, c in
                              zip(analysis["features"], model.coef_[0])},
                intercept=float(model.intercept_[0]),
                accuracy=float(model.score(X.values, y)),
                n=int(len(frame)))
        elif kind == "kmeans":
            from sklearn.cluster import KMeans
            from sklearn.preprocessing import StandardScaler
            frame = df[analysis["columns"]].apply(
                lambda s: pd.to_numeric(s, errors="coerce")).dropna()
            scaled = StandardScaler().fit_transform(frame.values)
            model = KMeans(n_clusters=analysis["k"], n_init=10, random_state=0).fit(scaled)
            counts = pd.Series(model.labels_).value_counts().sort_index()
            entry.update(
                k=analysis["k"],
                inertia=float(model.inertia_),
                cluster_sizes=[int(c) for c in counts],
                n=int(len(frame)))
        elif kind == "pca":
            from sklearn.decomposition import PCA
            from sklearn.preprocessing import StandardScaler
            frame = df[analysis["columns"]].apply(
                lambda s: pd.to_numeric(s, errors="coerce")).dropna()
            n_components = min(analysis["n_components"], frame.shape[1], len(frame))
            scaled = StandardScaler().fit_transform(frame.values)
            model = PCA(n_components=n_components).fit(scaled)
            entry.update(
                n_components=n_components,
                explained_variance_ratio=[float(v) for v in
                                          model.explained_variance_ratio_],
                components={
                    f"PC{i + 1}": {c: float(w) for c, w in
                                   zip(analysis["columns"], component)}
                    for i, component in enumerate(model.components_)},
                n=int(len(frame)))
        elif kind == "time_series_decompose":
            dt_col = analysis["datetime_column"]
            series = df[[dt_col, analysis["value_column"]]].copy()
            series[dt_col] = pd.to_datetime(series[dt_col], errors="coerce")
            if series[dt_col].isna().all():
                raise ValueError(
                    f"time_series_decompose requires a datetime column; "
                    f"{dt_col!r} could not be parsed")
            series = series.dropna().sort_values(dt_col).set_index(dt_col)
            values = pd.to_numeric(series[analysis["value_column"]], errors="coerce").dropna()
            period = analysis.get("period") or 7
            if len(values) < 2 * period:
                raise ValueError("time_series_decompose needs at least two full periods")
            trend = values.rolling(window=period, center=True, min_periods=1).mean()
            detrended = values - trend
            seasonal = detrended.groupby(np.arange(len(values)) % period).transform("mean")
            residual = values - trend - seasonal
            def tail(s, n=200):
                return [None if pd.isna(v) else float(v) for v in s.tail(n)]
            entry.update(
                period=period,
                n=int(len(values)),
                index=[ts.isoformat() for ts in values.tail(200).index],
                observed=tail(values), trend=tail(trend),
                seasonal=tail(seasonal), residual=tail(residual))
        entry["status"] = "ok"
    except Exception as exc:  # per-analysis failure never kills the batch
        entry.update(status="error", error=f"{type(exc).__name__}: {exc}")
    results.append(entry)

emit({"results": results})
"""

_CHART_BODY = """
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

spec = P["spec"]
df = active_df()

theme_map = {
    "default": "default",
    "minimal": "fast",
    "dark": "dark_background",
    "ggplot": "ggplot",
    "seaborn": "seaborn-v0_8",
}
style = theme_map.get(spec["theme"], "default")
try:
    plt.style.use(style)
except OSError:
    plt.style.use("default")  # missing style/fonts fall back gracefully

if spec["palette"] == "custom":
    colors = spec["colors"]
else:
    cmap = plt.get_cmap(spec["palette"])
    colors = [matplotlib.colors.to_hex(cmap(i / 8.0)) for i in range(9)]

width, height, dpi = spec["width"], spec["height"], spec["dpi"]
fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)

ctype = spec["type"]
x_name, y_name = spec.get("x"), spec.get("y")
plot_payload = {"data": [], "layout": {"title": spec.get("title") or ""}}

def agg_xy():
    if pd.api.types.is_numeric_dtype(df[x_name]):
        frame = df[[x_name, y_name]].dropna().sort_values(x_name)
        return frame[x_name], frame[y_name]
    grouped = df.groupby(x_name, observed=True)[y_name].mean()
    return grouped.index, grouped.values

try:
    import seaborn as sns
    have_seaborn = True
except ImportError:
    have_seaborn = False

if ctype in ("line", "area"):
    frame = df[[x_name, y_name]].dropna().sort_values(x_name)
    ax.plot(frame[x_name], frame[y_name], color=colors[0])
    if ctype == "area":
        ax.fill_between(frame[x_name], frame[y_name], alpha=0.35, color=colors[0])
    plot_payload["data"].append({
        "type": "scatter", "mode": "lines",
        "fill": "tozeroy" if ctype == "area" else "none",
        "x": [str(v) for v in frame[x_name]],
        "y": [None if pd.isna(v) else float(v) for v in frame[y_name]],
        "line": {"color": colors[0]},
    })
elif ctype == "bar":
    xs, ys = agg_xy()
    bar_colors = [colors[i % len(colors)] for i in range(len(xs))]
    ax.bar([str(v) for v in xs], ys, color=bar_colors)
    plot_payload["data"].append({
        "type": "bar",
        "x": [str(v) for v in xs],
        "y": [None if pd.isna(v) else float(v) for v in ys],
        "marker": {"color": bar_colors},
    })
elif ctype in ("scatter", "bubble"):
    wanted = []
    for c in (x_name, y_name, spec.get("size_by"), spec.get("color")):
        if c and c not in wanted:
            wanted.append(c)
    frame = df[wanted].dropna()
    sizes = 36.0
    if ctype == "bubble" and spec.get("size_by"):
        raw = pd.to_numeric(frame[spec["size_by"]], errors="coerce").fillna(0)
        span = raw.max() - raw.min()
        sizes = 20 + 180 * (raw - raw.min()) / span if span else 40.0
    ax.scatter(frame[x_name], frame[y_name], s=sizes, alpha=0.7, color=colors[0])
    plot_payload["data"].append({
        "type": "scatter", "mode": "markers",
        "x": [None if pd.isna(v) else (float(v) if isinstance(v, (int, float))
              else str(v)) for v in frame[x_name]],
        "y": [None if pd.isna(v) else float(v) for v in
              pd.to_numeric(frame[y_name], errors="coerce")],
        "marker": {"color": colors[0]},
    })
elif ctype == "histogram":
    values = pd.to_numeric(df[x_name], errors="coerce").dropna()
    ax.hist(values, bins=30, color=colors[0], edgecolor="white")
    plot_payload["data"].append({
        "type": "histogram", "x": [float(v) for v in values], "marker": {"color": colors[0]},
    })
elif ctype == "box":
    if have_seaborn:
        sns.boxplot(data=df, x=x_name, y=y_name, ax=ax, palette=colors[:8])
    else:
        groups = [g[y_name].dropna() for _, g in df.groupby(x_name, observed=True)]
        ax.boxplot(groups)
    for label, group in df.groupby(x_name, observed=True):
        plot_payload["data"].append({
            "type": "box", "name": str(label),
            "y": [float(v) for v in pd.to_numeric(group[y_name], errors="coerce").dropna()],
        })
elif ctype == "heatmap":
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    matrix = df[numeric_cols].corr()
    if have_seaborn:
        sns.heatmap(matrix, annot=len(numeric_cols) <= 12, cmap=spec["palette"]
                    if spec["palette"] != "custom" else "viridis", ax=ax)
    else:
        ax.imshow(matrix.values)
        ax.set_xticks(range(len(numeric_cols)), numeric_cols, rotation=45)
        ax.set_yticks(range(len(numeric_cols)), numeric_cols)
    plot_payload["data"].append({
        "type": "heatmap",
        "x": [str(c) for c in matrix.columns], "y": [str(c) for c in matrix.index],
        "z": [[None if pd.isna(v) else float(v) for v in row] for row in matrix.values],
    })
elif ctype == "pie":
    counts = df[x_name].astype("string").value_counts().head(12)
    ax.pie(counts.values, labels=[str(v) for v in counts.index],
           colors=[colors[i % len(colors)] for i in range(len(counts))],
           autopct="%1.0f%%")
    plot_payload["data"].append({
        "type": "pie", "labels": [str(v) for v in counts.index],
        "values": [int(v) for v in counts.values],
    })

if spec.get("title"):
    ax.set_title(spec["title"])
if x_name and ctype != "pie":
    ax.set_xlabel(x_name)
if y_name:
    ax.set_ylabel(y_name)
if spec.get("legend") and ctype in ("box",) and have_seaborn:
    pass  # seaborn draws its own legend when hue is used
for i, note in enumerate(spec.get("annotations") or []):
    ax.annotate(note, xy=(0.02, 0.95 - i * 0.06), xycoords="axes fraction", fontsize=8)
if ctype != "pie":
    fig.autofmt_xdate(rotation=30)
fig.tight_layout()

base = P["chart_basename"]
files = {}
for ext in ("png", "svg", "pdf"):
    path = f"charts/{base}.{ext}"
    fig.savefig(path, format=ext, dpi=dpi)
    files[ext] = path
plt.close(fig)

html = (
    "<!DOCTYPE html><html><head><meta charset='utf-8'>"
    "<script src='https://cdn.plot.ly/plotly-2.35.2.min.js'></script>"
    "</head><body style='margin:0'><div id='chart' style='width:100%;height:100vh'></div>"
    "<script>var payload = " + json.dumps(plot_payload)
    + ";Plotly.newPlot('chart', payload.data, payload.layout, {responsive: true});"
    "</script></body></html>"
)
html_path = f"charts/{base}.html"
with open(html_path, "w", encoding="utf-8") as fh:
    fh.write(html)
files["html"] = html_path

emit({
    "files": files,
    "sizes": {ext: os.path.getsize(path) for ext, path in files.items()},
})
"""

_REPORT_BODY = """
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42  # embed TrueType so text stays extractable
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

df = active_df()
title = P["title"]
sections = P["sections"]
charts = P.get("chart_files") or []

numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
summary_lines = [
    f"Rows: {df.shape[0]}    Columns: {df.shape[1]}",
    f"Missing cells: {int(df.isna().sum().sum())} "
    f"({df.isna().mean().mean() * 100:.2f}% of all cells)",
    f"Duplicate rows: {int(df.duplicated().sum())}",
    f"Numeric columns: {len(numeric_cols)}",
]
stats_rows = []
for name in numeric_cols[:12]:
    values = pd.to_numeric(df[name], errors="coerce").dropna()
    if values.empty:
        continue
    stats_rows.append([name, f"{values.mean():.4g}", f"{values.std(ddof=1):.4g}"
                       if len(values) > 1 else "0", f"{values.min():.4g}",
                       f"{values.max():.4g}"])

section_text = {
    "abstract": (
        f"This report summarises the dataset '{P['dataset_name']}' "
        f"({df.shape[0]} rows x {df.shape[1]} columns). It covers data "
        "quality, descriptive statistics, and the charts generated during "
        "the analysis session."),
    "data_summary": "\\n".join(summary_lines),
    "methodology": (
        "Data was ingested through Dream's sandboxed data-science pipeline. "
        "Profiling, cleaning, and statistical analyses ran inside an "
        "isolated container using pandas, numpy, scipy, and scikit-learn. "
        "No data left the local machine."),
    "results": (
        "Descriptive statistics for the numeric columns appear in the table "
        "below; generated charts follow on the next page."),
    "discussion": (
        "Interpretation should account for missing values and potential "
        "outliers noted in the data summary. Correlations do not imply "
        "causation."),
    "conclusion": (
        "The dataset is ready for downstream analysis. Re-run profiling "
        "after any further cleaning to keep the summary current."),
    "references": (
        "[1] pandas development team, doi:10.5281/zenodo.3509134\\n"
        "[2] Virtanen et al., SciPy 1.0, doi:10.1038/s41592-019-0686-2\\n"
        "[3] Pedregosa et al., scikit-learn, JMLR 12 (2011)"),
}

with PdfPages("report.pdf") as pdf:
    # Page 1: title + sections.
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.text(0.5, 0.94, title, ha="center", fontsize=18, weight="bold")
    fig.text(0.5, 0.905, P["dataset_name"], ha="center", fontsize=11, color="#555555")
    cursor = 0.86
    for section in sections:
        text = section_text.get(section, "")
        fig.text(0.08, cursor, section.replace("_", " ").title(), fontsize=13, weight="bold")
        cursor -= 0.025
        for line in text.split("\\n"):
            wrapped = [line[i:i + 95] for i in range(0, max(len(line), 1), 95)]
            for piece in wrapped:
                fig.text(0.08, cursor, piece, fontsize=9)
                cursor -= 0.018
        cursor -= 0.02
        if cursor < 0.1:
            break
    pdf.savefig(fig)
    plt.close(fig)

    # Page 2: numeric summary table.
    if stats_rows:
        fig, ax = plt.subplots(figsize=(8.27, 11.69))
        ax.axis("off")
        ax.set_title("Numeric summary", fontsize=13, weight="bold", loc="left")
        table = ax.table(
            cellText=stats_rows,
            colLabels=["column", "mean", "std", "min", "max"],
            loc="upper center", cellLoc="left")
        table.scale(1, 1.4)
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        pdf.savefig(fig)
        plt.close(fig)

    # Pages 3-5: charts, two per page.
    for start in range(0, min(len(charts), 6), 2):
        fig, axes = plt.subplots(2, 1, figsize=(8.27, 11.69))
        for ax, chart_path in zip(axes, charts[start:start + 2]):
            ax.axis("off")
            try:
                ax.imshow(plt.imread(chart_path))
            except Exception:
                ax.text(0.5, 0.5, f"chart unavailable: {chart_path}", ha="center")
        for ax in axes[len(charts[start:start + 2]):]:
            ax.axis("off")
        pdf.savefig(fig)
        plt.close(fig)

markdown = ["# " + title, ""]
for section in sections:
    markdown.append("## " + section.replace("_", " ").title())
    markdown.append("")
    markdown.append(section_text.get(section, ""))
    markdown.append("")
if charts:
    markdown.append("## Charts")
    markdown.append("")
    for chart_path in charts:
        markdown.append(f"![chart]({chart_path})")
    markdown.append("")
with open("report.md", "w", encoding="utf-8") as fh:
    fh.write("\\n".join(markdown))

emit({
    "pdf": "report.pdf",
    "markdown": "report.md",
    "size_bytes": os.path.getsize("report.pdf"),
    "sections": sections,
    "charts_embedded": len(charts[:6]),
})
"""


# --------------------------------------------------------------------------- #
# Runtime
# --------------------------------------------------------------------------- #


class DataScienceRuntime:
    """Synchronous facade over the dataset registry + sandboxed executor.

    All public methods validate on the host, write ``_params.json``, run one
    generated script, and read back ``_result.json``. They are safe to call
    from a worker thread (the bridge wraps them in ``asyncio.to_thread``).
    """

    def __init__(
        self,
        datasets: DatasetManager | None = None,
        executor: Any = None,
        *,
        preview_rows: int = 50,
        default_timeout: int = 120,
    ) -> None:
        self.datasets = datasets or DatasetManager()
        if executor is None:
            executor = self._default_executor()
        self.executor = executor
        self.preview_rows = preview_rows
        self.default_timeout = default_timeout

    @staticmethod
    def _default_executor() -> Any:
        if os.environ.get("DREAM_DATA_LOCAL_EXEC", "").strip().lower() in {"1", "true", "yes"}:
            return LocalPythonExecutor()
        try:
            from dream.docker_sandbox import DockerSandbox
        except ImportError:  # pragma: no cover - dream package always present
            return LocalPythonExecutor()
        return SandboxCodeExecutor(DockerSandbox())

    # -- plumbing --------------------------------------------------------- #

    def _run(
        self,
        record: DatasetRecord,
        body: str,
        params: dict[str, Any],
        *,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        workspace = self.datasets.dir_for(record)
        params = {
            "active_file": record.active_file,
            "active_format": "csv" if record.cleaned else record.format,
            "preview_rows": self.preview_rows,
            "known_dtypes": record.dtypes if record.cleaned else {},
            "encoding": "utf-8" if record.cleaned else (record.encoding or "utf-8"),
            **params,
        }
        params_path = workspace / "_params.json"
        result_path = workspace / "_result.json"
        params_path.write_text(json.dumps(params, ensure_ascii=False), encoding="utf-8")
        result_path.unlink(missing_ok=True)
        try:
            outcome = self.executor.run(
                _script(body), workspace, timeout or self.default_timeout
            )
            if outcome.timed_out:
                raise DataScienceError("the operation timed out inside the sandbox")
            if not result_path.exists():
                tail = (outcome.stderr or outcome.stdout or "no output").strip()[-2000:]
                raise DataScienceError(f"sandbox execution failed: {tail}")
            return json.loads(result_path.read_text(encoding="utf-8"))
        finally:
            params_path.unlink(missing_ok=True)
            result_path.unlink(missing_ok=True)

    # -- tools ------------------------------------------------------------ #

    def load_data(self, file_path: str, name: str | None = None) -> dict[str, Any]:
        """Ingest a file into the registry and return its shape/schema/preview."""
        if not isinstance(file_path, str) or not file_path.strip():
            raise DataScienceError("file_path must be a non-empty string")
        source = Path(os.path.expanduser(file_path.strip())).resolve()
        if not source.is_file():
            raise DataScienceError(f"file not found: {file_path}")
        size = source.stat().st_size
        if size == 0:
            raise DataScienceError(f"{source.name} is empty")
        if size > MAX_SOURCE_BYTES:
            raise DataScienceError(
                f"{source.name} is {size // (1024 * 1024)} MB; the limit is "
                f"{MAX_SOURCE_BYTES // (1024 * 1024)} MB"
            )
        fmt = detect_format(source)
        encoding = sniff_text_encoding(source) if fmt in ("csv", "tsv") else "utf-8"
        if name is not None and (not isinstance(name, str) or len(name) > 120):
            raise DataScienceError("name must be a string of at most 120 characters")
        record = self.datasets.create(
            name or source.stem, source, fmt, encoding=encoding
        )
        try:
            result = self._run(record, _LOAD_BODY, {"preview_rows": self.preview_rows})
        except Exception:
            self.datasets.delete(record.dataset_id)
            raise
        record.shape = [int(v) for v in result["shape"]]
        record.columns = [str(c) for c in result["columns"]]
        record.dtypes = {str(k): str(v) for k, v in result["dtypes"].items()}
        record.column_meta = result.get("column_meta", [])
        record.memory_bytes = int(result.get("memory_bytes", 0))
        self.datasets.update(record)
        return {
            "dataset_id": record.dataset_id,
            "name": record.name,
            "filename": record.filename,
            "format": fmt,
            "shape": record.shape,
            "columns": record.columns,
            "dtypes": record.dtypes,
            "memory_bytes": record.memory_bytes,
            "preview": result.get("preview", []),
        }

    def profile_data(self, dataset_id: str, max_categories: int = 20) -> dict[str, Any]:
        """Per-column + summary statistics, chunked for very large files."""
        if not isinstance(max_categories, int) or not 1 <= max_categories <= 200:
            raise DataScienceError("max_categories must be an integer in [1, 200]")
        record = self.datasets.get(dataset_id)
        active = self.datasets.dir_for(record) / record.active_file
        chunked = (
            active.exists()
            and active.stat().st_size > CHUNK_THRESHOLD_BYTES
            and (record.format in ("csv", "tsv") or record.cleaned)
        )
        result = self._run(
            record,
            _PROFILE_BODY,
            {"max_categories": max_categories, "chunked": chunked},
            timeout=max(self.default_timeout, 300 if chunked else 0),
        )
        if result.get("column_meta"):
            record.column_meta = result["column_meta"]
            self.datasets.update(record)
        result["dataset_id"] = record.dataset_id
        return result

    def clean_data(self, dataset_id: str, operations: Any) -> dict[str, Any]:
        """Apply a validated pipeline of cleaning operations; writes cleaned.csv."""
        record = self.datasets.get(dataset_id)
        if not isinstance(operations, list) or not operations:
            raise DataScienceError("operations must be a non-empty list")
        if len(operations) > 50:
            raise DataScienceError("at most 50 operations per call")
        columns = list(record.columns)
        validated = []
        for op in operations:
            checked = validate_clean_op(op, columns)
            validated.append(checked)
            # Track schema changes so later ops validate against the new shape.
            if checked["op"] == "rename_column":
                columns = [checked["new_name"] if c == checked["column"] else c
                           for c in columns]
            elif checked["op"] == "drop_column":
                columns = [c for c in columns if c != checked["column"]]
            elif checked["op"] == "encode_categorical" and checked["method"] == "onehot":
                columns = [c for c in columns if c != checked["column"]]
        result = self._run(record, _CLEAN_BODY, {"operations": validated})
        record.active_file = "cleaned.csv"
        record.cleaned = True
        record.encoding = "utf-8"
        record.shape = [int(v) for v in result["shape"]]
        record.columns = [str(c) for c in result["columns"]]
        record.dtypes = {str(k): str(v) for k, v in result["dtypes"].items()}
        record.column_meta = result.get("column_meta", [])
        self.datasets.update(record)
        return {
            "dataset_id": record.dataset_id,
            "rows_before": result["rows_before"],
            "rows_after": result["rows_after"],
            "shape": record.shape,
            "columns": record.columns,
            "dtypes": record.dtypes,
            "operations_applied": result["operations_applied"],
            "preview": result.get("preview", []),
        }

    def analyze_data(self, dataset_id: str, analyses: Any) -> dict[str, Any]:
        """Run validated statistical analyses; one failure never kills the batch."""
        record = self.datasets.get(dataset_id)
        if not isinstance(analyses, list) or not analyses:
            raise DataScienceError("analyses must be a non-empty list")
        if len(analyses) > 20:
            raise DataScienceError("at most 20 analyses per call")
        validated = [validate_analysis(a, record.columns) for a in analyses]
        result = self._run(
            record, _ANALYZE_BODY, {"analyses": validated}, timeout=self.default_timeout * 2
        )
        return {"dataset_id": record.dataset_id, "results": result["results"]}

    def auto_chart(self, dataset_id: str, max_charts: int = 6) -> dict[str, Any]:
        """Rank chart suggestions from the dataset's column metadata."""
        record = self.datasets.get(dataset_id)
        meta = record.column_meta
        if not meta:
            profile = self.profile_data(dataset_id)
            meta = profile.get("column_meta", [])
        specs = suggest_charts(meta, max_charts=max_charts)
        for spec in specs:
            spec["dataset_id"] = record.dataset_id
        return {"dataset_id": record.dataset_id, "charts": specs}

    def create_chart(self, chart_spec: Any) -> dict[str, Any]:
        """Render one chart to PNG/SVG/PDF (matplotlib) + HTML (plotly payload)."""
        if not isinstance(chart_spec, dict):
            raise DataScienceError("chart_spec must be an object")
        record = self.datasets.get(chart_spec.get("dataset_id"))
        spec = validate_chart_spec(chart_spec, record.columns)
        chart_id = uuid.uuid4().hex[:12]
        charts_dir = self.datasets.dir_for(record) / "charts"
        charts_dir.mkdir(exist_ok=True)
        result = self._run(record, _CHART_BODY, {"spec": spec, "chart_basename": chart_id})
        oversize = {ext: size for ext, size in result["sizes"].items()
                    if size > CHART_QUOTA_BYTES}
        if oversize:
            for rel in result["files"].values():
                (self.datasets.dir_for(record) / rel).unlink(missing_ok=True)
            raise DataScienceError(
                f"chart exceeds the {CHART_QUOTA_BYTES // (1024 * 1024)} MB quota: "
                + ", ".join(f"{ext}={size}" for ext, size in oversize.items())
            )
        files = {
            ext: str(self.datasets.dir_for(record) / rel)
            for ext, rel in result["files"].items()
        }
        return {
            "chart_id": chart_id,
            "dataset_id": record.dataset_id,
            "spec": spec,
            "files": files,
            "sizes": result["sizes"],
        }

    def generate_report(
        self,
        dataset_id: str,
        title: str,
        sections: Any = None,
    ) -> dict[str, Any]:
        """Produce report.pdf (<= 5 pages) and report.md for the dataset."""
        record = self.datasets.get(dataset_id)
        if not isinstance(title, str) or not title.strip():
            raise DataScienceError("title must be a non-empty string")
        if len(title) > 200:
            raise DataScienceError("title must be at most 200 characters")
        if sections is None:
            sections = list(REPORT_SECTIONS)
        if not isinstance(sections, list) or not sections:
            raise DataScienceError("sections must be a non-empty list")
        for section in sections:
            if section not in REPORT_SECTIONS:
                raise DataScienceError(
                    f"unknown section {str(section)[:40]!r}; allowed: "
                    f"{', '.join(REPORT_SECTIONS)}"
                )
        charts_dir = self.datasets.dir_for(record) / "charts"
        chart_files = sorted(
            f"charts/{p.name}" for p in charts_dir.glob("*.png")
        ) if charts_dir.is_dir() else []
        result = self._run(
            record,
            _REPORT_BODY,
            {
                "title": title.strip(),
                "sections": sections,
                "dataset_name": record.name,
                "chart_files": chart_files[:6],
            },
            timeout=self.default_timeout * 2,
        )
        return {
            "dataset_id": record.dataset_id,
            "title": title.strip(),
            "pdf_path": str(self.datasets.dir_for(record) / result["pdf"]),
            "markdown_path": str(self.datasets.dir_for(record) / result["markdown"]),
            "size_bytes": result["size_bytes"],
            "sections": result["sections"],
            "charts_embedded": result["charts_embedded"],
        }

    # -- registry --------------------------------------------------------- #

    def list_datasets(self) -> list[dict[str, Any]]:
        return [
            {
                "dataset_id": r.dataset_id,
                "name": r.name,
                "filename": r.filename,
                "format": r.format,
                "created_at": r.created_at,
                "shape": r.shape,
                "columns": r.columns,
                "cleaned": r.cleaned,
            }
            for r in self.datasets.list()
        ]

    def delete_dataset(self, dataset_id: str) -> bool:
        return self.datasets.delete(dataset_id)

    def read_markdown_report(self, dataset_id: str) -> str | None:
        """Return report.md content when a report has been generated."""
        record = self.datasets.get(dataset_id)
        path = self.datasets.dir_for(record) / "report.md"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Agent-facing tool registration
# --------------------------------------------------------------------------- #


def register_data_science_tools(runtime: DataScienceRuntime) -> list[str]:
    """Register the data tools on the shared registry (idempotent).

    Returns the list of registered tool names. Tools are ``guarded`` — they
    read user files and spawn sandbox containers, but cannot write outside
    ``data/datasets/``.
    """
    from dream.tools import REGISTRY, tool

    if "load_data" in REGISTRY:
        return [name for name in _TOOL_NAMES if name in REGISTRY]

    @tool(risk="guarded")
    def load_data(file_path: str, name: str = "") -> dict[str, Any]:
        """Load a dataset file (CSV/TSV/Excel/JSON/YAML/XML/SQLite/Parquet).

        :param file_path: Path to the data file to ingest.
        :param name: Optional display name for the dataset.
        """
        return runtime.load_data(file_path, name or None)

    @tool(risk="safe")
    def profile_data(dataset_id: str, max_categories: int = 20) -> dict[str, Any]:
        """Profile a dataset: per-column stats, missing values, outliers.

        :param dataset_id: Dataset id returned by load_data.
        :param max_categories: Top categories to report per text column.
        """
        return runtime.profile_data(dataset_id, max_categories)

    @tool(risk="guarded")
    def clean_data(dataset_id: str, operations: list) -> dict[str, Any]:
        """Apply cleaning operations (drop_na, fill_na, convert_dtype, ...).

        :param dataset_id: Dataset id returned by load_data.
        :param operations: List of tagged operations, each {"op": ..., ...}.
        """
        return runtime.clean_data(dataset_id, operations)

    @tool(risk="safe")
    def analyze_data(dataset_id: str, analyses: list) -> dict[str, Any]:
        """Run statistical analyses (correlation, ttest, regression, ...).

        :param dataset_id: Dataset id returned by load_data.
        :param analyses: List of analyses, each {"kind": ..., ...}.
        """
        return runtime.analyze_data(dataset_id, analyses)

    @tool(risk="safe")
    def auto_chart(dataset_id: str, max_charts: int = 6) -> dict[str, Any]:
        """Suggest the best charts for a dataset, ranked by fit.

        :param dataset_id: Dataset id returned by load_data.
        :param max_charts: Maximum number of suggestions.
        """
        return runtime.auto_chart(dataset_id, max_charts)

    @tool(risk="guarded")
    def create_chart(chart_spec: dict) -> dict[str, Any]:
        """Render a chart to PNG/SVG/PDF/HTML from a ChartSpec.

        :param chart_spec: Spec with type, dataset_id, x, y, theme, palette.
        """
        return runtime.create_chart(chart_spec)

    @tool(risk="guarded")
    def generate_report(dataset_id: str, title: str, sections: list | None = None) -> dict:
        """Generate a PDF report (abstract, summary, results, charts).

        :param dataset_id: Dataset id returned by load_data.
        :param title: Report title.
        :param sections: Optional section list; defaults to all sections.
        """
        return runtime.generate_report(dataset_id, title, sections)

    return list(_TOOL_NAMES)


_TOOL_NAMES = (
    "load_data",
    "profile_data",
    "clean_data",
    "analyze_data",
    "auto_chart",
    "create_chart",
    "generate_report",
)


def make_sample_workspace() -> Path:  # pragma: no cover - dev helper
    """Create a throwaway workspace directory for ad-hoc experiments."""
    return Path(tempfile.mkdtemp(prefix="dream-data-"))
