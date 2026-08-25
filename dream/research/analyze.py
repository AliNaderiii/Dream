"""Analysis, chart selection, and the report's numeric tables.

Everything in this module is a thin, deterministic layer over
:mod:`dream.skills.data_science`: analyses are picked from the *profiled*
column roles (never from a model's guess about the schema), charts come from
the existing suggestion + validation path, and tables are built from executed
results only.

The other job of this module is :func:`extract_numbers`, which harvests every
numeric literal an executed step produced. That set is the grounding ledger:
the proofreader rejects any number in the report that is not in it.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from dream.research.errors import ResearchError
from dream.research.schemas import Finding

logger = logging.getLogger("dream.research.analyze")

__all__ = [
    "build_tables",
    "detect_anomalies",
    "extract_numbers",
    "format_number",
    "plan_analyses",
    "render_charts",
    "run_analyses",
]

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
MAX_ANALYSES = 8
MAX_CHARTS = 4


def format_number(value: Any) -> str:
    """Canonical numeric rendering, so grounding compares like with like."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer() and abs(number) < 1e15:
        return str(int(number))
    return f"{number:.4g}"


def extract_numbers(payload: Any, *, limit: int = 2000) -> set[str]:
    """Collect every number an executed step produced, canonicalised.

    Walks dicts, lists, and strings. Strings are scanned with a numeric regex
    so a value printed inside stdout still counts as grounded evidence.
    """
    found: set[str] = set()

    def walk(node: Any, depth: int = 0) -> None:
        if len(found) >= limit or depth > 12:
            return
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            found.add(format_number(node))
        elif isinstance(node, str):
            for match in _NUMBER_RE.findall(node)[:200]:
                found.add(format_number(match))
        elif isinstance(node, dict):
            for key, value in node.items():
                walk(key, depth + 1)
                walk(value, depth + 1)
        elif isinstance(node, (list, tuple, set)):
            for item in node:
                walk(item, depth + 1)

    walk(payload)
    return found


def plan_analyses(profile: dict[str, Any], *, max_analyses: int = MAX_ANALYSES) -> list[dict]:
    """Choose analyses from real column roles — the schema is already known.

    Deterministic, so the offline (Echo) run and a live-model run analyse the
    same table the same way and the tests can assert on the numbers.
    """
    columns = profile.get("columns") or {}
    if not isinstance(columns, dict):
        return []
    numeric = [name for name, e in sorted(columns.items())
               if isinstance(e, dict) and e.get("role") == "numeric"]
    categorical = [name for name, e in sorted(columns.items())
                   if isinstance(e, dict) and e.get("role") == "categorical"]

    analyses: list[dict[str, Any]] = []
    if len(numeric) >= 2:
        analyses.append({"kind": "correlation", "columns": numeric[:8], "method": "pearson"})
    for name in numeric[:3]:
        analyses.append({"kind": "distribution", "column": name})
    if categorical and numeric:
        analyses.append(
            {"kind": "groupby", "group_column": categorical[0],
             "value_column": numeric[0], "agg": "mean"}
        )
    if len(numeric) >= 2:
        analyses.append(
            {"kind": "regression", "target": numeric[0], "features": numeric[1:4]}
        )
    return analyses[:max_analyses]


def run_analyses(
    runtime: Any,
    dataset_id: str,
    analyses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Execute a batch, tolerating individual failures.

    ``analyze_data`` already isolates one failing analysis from the batch; a
    whole-batch failure (a bad column list, a sandbox error) degrades to an
    empty result plus the error text so the loop can reflect on it.
    """
    if not analyses:
        return {"results": [], "error": ""}
    try:
        outcome = runtime.analyze_data(dataset_id, analyses[:MAX_ANALYSES])
    except Exception as exc:
        logger.info("analysis batch failed: %s", exc)
        return {"results": [], "error": str(exc)[:500]}
    return {"results": outcome.get("results") or [], "error": ""}


def detect_anomalies(profile: dict[str, Any]) -> list[Finding]:
    """Proactive alerts: spikes, drops, and outliers visible in the profile.

    WisdomAI's point — a report should surface *what changed*, not only
    tabulate. Each alert carries the statistic that triggered it, so it stays
    grounded.
    """
    findings: list[Finding] = []
    rows = int(profile.get("row_count") or 0)
    columns = profile.get("columns") or {}
    if not isinstance(columns, dict) or rows <= 0:
        return findings

    duplicates = profile.get("duplicate_rows")
    if isinstance(duplicates, int) and duplicates > 0:
        share = duplicates / rows * 100
        findings.append(
            Finding(
                claim=f"{duplicates} duplicate rows ({share:.1f}% of {rows}) are present",
                evidence=f"profile.duplicate_rows={duplicates}, row_count={rows}",
                metric="duplicate_rows",
                value=duplicates,
                kind="anomaly",
            )
        )

    for name, entry in sorted(columns.items()):
        if not isinstance(entry, dict):
            continue
        missing = int(entry.get("missing") or 0)
        if missing and missing / rows >= 0.10:
            findings.append(
                Finding(
                    claim=(
                        f"column '{name}' is missing {missing} of {rows} values "
                        f"({missing / rows * 100:.1f}%)"
                    ),
                    evidence=f"profile.columns['{name}'].missing={missing}",
                    metric=f"{name}.missing",
                    value=missing,
                    kind="anomaly",
                )
            )
        if entry.get("role") != "numeric":
            continue
        mean, std = entry.get("mean"), entry.get("std")
        maximum, minimum = entry.get("max"), entry.get("min")
        if isinstance(mean, (int, float)) and isinstance(std, (int, float)) and std > 0:
            for label, value in (("high", maximum), ("low", minimum)):
                if not isinstance(value, (int, float)):
                    continue
                z = abs(value - mean) / std
                if z >= 3.0:
                    direction = "spike" if label == "high" else "drop"
                    findings.append(
                        Finding(
                            claim=(
                                f"'{name}' shows a {direction}: {label} value "
                                f"{format_number(value)} is {z:.1f} standard "
                                f"deviations from the mean {format_number(mean)}"
                            ),
                            evidence=(
                                f"profile.columns['{name}']: {label}={format_number(value)}, "
                                f"mean={format_number(mean)}, std={format_number(std)}"
                            ),
                            metric=f"{name}.{label}",
                            value=value,
                            kind="anomaly",
                        )
                    )
    return findings


def build_tables(profile: dict[str, Any], *, max_rows: int = 12) -> list[dict[str, Any]]:
    """Numeric summary tables built strictly from profiled statistics."""
    columns = profile.get("columns") or {}
    if not isinstance(columns, dict):
        return []
    rows: list[list[str]] = []
    for name, entry in sorted(columns.items()):
        if not isinstance(entry, dict) or entry.get("role") != "numeric":
            continue
        rows.append(
            [
                str(name),
                format_number(entry.get("count", "")),
                format_number(entry.get("mean", "")),
                format_number(entry.get("std", "")),
                format_number(entry.get("min", "")),
                format_number(entry.get("max", "")),
            ]
        )
        if len(rows) >= max_rows:
            break
    if not rows:
        return []
    return [
        {
            "title": "Descriptive statistics (executed)",
            "header": ["column", "count", "mean", "std", "min", "max"],
            "rows": rows,
        }
    ]


def render_charts(
    runtime: Any,
    dataset_id: str,
    *,
    max_charts: int = MAX_CHARTS,
) -> list[dict[str, Any]]:
    """Suggest, validate, and export charts through the existing chart path.

    A chart that fails validation or blows the per-export quota is skipped
    with a log line; a section without a figure is a smaller problem than a
    research run that dies rendering one.
    """
    if not isinstance(max_charts, int) or not 1 <= max_charts <= 12:
        raise ResearchError("max_charts must be an integer in [1, 12]")
    try:
        suggestions = runtime.auto_chart(dataset_id, max_charts).get("charts") or []
    except Exception as exc:
        logger.info("chart suggestion failed: %s", exc)
        return []
    rendered: list[dict[str, Any]] = []
    for spec in suggestions[:max_charts]:
        try:
            rendered.append(runtime.create_chart(dict(spec)))
        except Exception as exc:
            logger.info("chart render skipped (%s): %s", spec.get("type"), exc)
    return rendered
