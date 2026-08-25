"""Trusted dependency-free worker for validated Data Q&A plans.

This file runs in an isolated, resource-limited subprocess. It never evaluates
source code and blocks socket creation before touching dataset values.
"""

from __future__ import annotations

import json
import math
import socket
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

# Imported only from trusted installation code. ``-I`` prevents cwd imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dream.dataqa.dataio import iter_rows  # noqa: E402
from dream.security.injection import scan_text  # noqa: E402

MAX_RESULT_ROWS = 200
MAX_OUTPUT_CHARS = 1_000_000


def _deny_network(*_args: Any, **_kwargs: Any) -> Any:
    raise PermissionError("network is disabled in the Data Q&A sandbox")


socket.socket = _deny_network  # type: ignore[assignment]
socket.create_connection = _deny_network  # type: ignore[assignment]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _matches(value: Any, operator: str, expected: Any) -> bool:
    if operator == "not_null":
        return value is not None
    if operator in {"in", "not_in"}:
        present = value in expected
        return present if operator == "in" else not present
    if operator in {"contains", "starts_with", "ends_with"}:
        left, right = str(value or "").casefold(), str(expected or "").casefold()
        return {
            "contains": right in left,
            "starts_with": left.startswith(right),
            "ends_with": left.endswith(right),
        }[operator]
    left_num, right_num = _number(value), _number(expected)
    left, right = (
        (left_num, right_num)
        if left_num is not None and right_num is not None
        else (value, expected)
    )
    try:
        return {
            "eq": left == right,
            "ne": left != right,
            "gt": left > right,
            "gte": left >= right,
            "lt": left < right,
            "lte": left <= right,
        }[operator]
    except (KeyError, TypeError):
        return False


def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _correlation(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs, strict=True)
    x_mean, y_mean = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    x_scale = math.sqrt(sum((x - x_mean) ** 2 for x in xs))
    y_scale = math.sqrt(sum((y - y_mean) ** 2 for y in ys))
    denominator = x_scale * y_scale
    return numerator / denominator if denominator else None


def _aggregate(values: list[Any], kind: str) -> int | float | None:
    if kind == "count":
        return len(values)
    numbers = [value for value in (_number(item) for item in values) if value is not None]
    if not numbers:
        return None
    if kind == "sum":
        return sum(numbers)
    if kind == "mean":
        return sum(numbers) / len(numbers)
    if kind == "min":
        return min(numbers)
    if kind == "max":
        return max(numbers)
    if kind == "median":
        return statistics.median(numbers)
    return None


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    plan = payload["plan"]
    root = Path(payload["workspace_root"]).resolve()
    requested_path = Path(payload["dataset_path"])
    path = requested_path.resolve()
    if requested_path.is_symlink() or not path.is_file() or not path.is_relative_to(root):
        raise PermissionError("dataset path escaped the Dream workspace")
    rows = list(iter_rows(path, payload["format"], max_rows=250_000))
    considered = len(rows)
    safe_rows = [
        row
        for row in rows
        if not any(
            isinstance(value, str) and not scan_text(value, mode="strip").clean
            for value in row.values()
        )
    ]
    rejected_rows = len(rows) - len(safe_rows)
    rows = safe_rows
    for spec in plan.get("filters", []):
        rows = [
            row
            for row in rows
            if _matches(row.get(spec["column"]), spec["operator"], spec.get("value"))
        ]
    action = plan.get("action")
    result: list[dict[str, Any]]
    columns: list[str]
    if action == "aggregate":
        groups = plan.get("groups", [])
        aggregate = plan.get("aggregate", "count")
        metric = plan.get("metric")
        value_name = "count_rows" if aggregate == "count" else f"{aggregate}_{metric}"
        if groups:
            buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                buckets[tuple(row.get(group) for group in groups)].append(row)
            result = []
            for key, bucket in buckets.items():
                values = bucket if aggregate == "count" else [row.get(metric) for row in bucket]
                result.append(
                    {
                        **dict(zip(groups, key, strict=True)),
                        value_name: _aggregate(values, aggregate),
                    }
                )
            if plan.get("date_column"):
                result.sort(key=lambda row: str(row.get(plan["date_column"], "")))
            else:
                result.sort(
                    key=lambda row: (row.get(value_name) is not None, row.get(value_name)),
                    reverse=plan.get("sort", "desc") == "desc",
                )
            columns = [*groups, value_name]
        else:
            values = rows if aggregate == "count" else [row.get(metric) for row in rows]
            result = [{value_name: _aggregate(values, aggregate)}]
            columns = [value_name]
    elif action == "distribution":
        values = [
            value
            for value in (_number(row.get(plan.get("metric"))) for row in rows)
            if value is not None
        ]
        if not values:
            result = []
        elif plan.get("chart_type") == "box":
            result = [
                {
                    "minimum": min(values),
                    "q1": _quantile(values, 0.25),
                    "median": statistics.median(values),
                    "q3": _quantile(values, 0.75),
                    "maximum": max(values),
                    "count": len(values),
                }
            ]
        else:
            minimum, maximum = min(values), max(values)
            bin_count = min(10, max(1, math.ceil(math.sqrt(len(values)))))
            width = (maximum - minimum) / bin_count if maximum != minimum else 1.0
            counts = [0] * bin_count
            for value in values:
                index = min(bin_count - 1, int((value - minimum) / width))
                counts[index] += 1
            result = [
                {
                    "bin_start": minimum + index * width,
                    "bin_end": minimum + (index + 1) * width,
                    "count": count,
                }
                for index, count in enumerate(counts)
            ]
        columns = list(result[0]) if result else []
    elif action == "relationship":
        columns = [plan["metric"], plan["secondary_metric"]]
        result = [
            {name: row.get(name) for name in columns}
            for row in rows
            if all(_number(row.get(name)) is not None for name in columns)
        ]
    elif action == "correlation":
        names = plan.get("groups", [])[:12]
        columns = ["x", "y", "correlation"]
        result = []
        for x_name in names:
            for y_name in names:
                pairs = [
                    (x, y)
                    for row in rows
                    if (x := _number(row.get(x_name))) is not None
                    and (y := _number(row.get(y_name))) is not None
                ]
                result.append({"x": x_name, "y": y_name, "correlation": _correlation(pairs)})
    else:
        selected = plan.get("groups") or (list(rows[0]) if rows else [])
        columns = selected[:40]
        result = [{name: row.get(name) for name in columns} for row in rows]
    result = result[: min(MAX_RESULT_ROWS, int(plan.get("limit", MAX_RESULT_ROWS)))]
    status = (
        "ok"
        if result and any(value is not None for row in result for value in row.values())
        else "insufficient_data"
    )
    output = {
        "status": status,
        "answer_shape": plan.get("answer_shape", "table"),
        "columns": columns,
        "rows": result,
        "rows_considered": considered,
        "operation": action,
        "warnings": (
            [f"Rejected {rejected_rows} suspicious data row(s) as prompt injection."]
            if rejected_rows
            else []
        ),
        "elapsed_seconds": time.monotonic() - started,
        "sandbox": "guarded-local",
        "network_enabled": False,
    }
    if len(json.dumps(output, ensure_ascii=False)) > MAX_OUTPUT_CHARS:
        output["rows"] = output["rows"][:20]
        output["warnings"].append("Result was truncated to the output quota")
    return output


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read(MAX_OUTPUT_CHARS))
        result = execute(payload)
    except Exception as exc:
        result = {
            "status": "error",
            "answer_shape": "table",
            "columns": [],
            "rows": [],
            "rows_considered": 0,
            "operation": "worker",
            "warnings": [],
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            "sandbox": "guarded-local",
            "network_enabled": False,
        }
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
