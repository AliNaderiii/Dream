"""Quota-bounded, accessible SVG charts built only from execution evidence."""

# ruff: noqa: E501 -- SVG element literals remain safer and clearer as single strings.

from __future__ import annotations

import html
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from dream.dataqa.models import ChartSpec, QueryPlan

MAX_CHARTS_PER_SESSION = 32
MAX_CHART_DIRECTORY_BYTES = 4 * 1024 * 1024
MAX_SVG_BYTES = 512 * 1024


def choose_chart(plan: QueryPlan, rows: list[dict[str, Any]]) -> ChartSpec | None:
    """Choose a chart only when the executed result can support it."""
    if not plan.wants_chart or not rows:
        return None
    kind = plan.chart_type
    if not kind:
        if plan.action == "relationship":
            kind = "scatter"
        elif plan.action == "distribution":
            kind = "histogram"
        elif plan.action == "correlation":
            kind = "heatmap"
        elif plan.date_column:
            kind = "line"
        elif plan.groups:
            kind = "bar"
        else:
            return None

    if kind in {"bar", "line"}:
        x = plan.groups[0] if plan.groups else plan.date_column
        y = "count_rows" if plan.aggregate == "count" else f"{plan.aggregate}_{plan.metric}"
        if not x or y not in rows[0]:
            return None
        title = f"{y} by {x}"
    elif kind == "scatter":
        x, y = plan.metric, plan.secondary_metric
        if not x or not y:
            return None
        title = f"{y} versus {x}"
    elif kind == "histogram":
        x, y = "bin_start", "count"
        if not {"bin_start", "bin_end", "count"}.issubset(rows[0]):
            return None
        title = f"Distribution of {plan.metric}"
    elif kind == "box":
        x, y = plan.metric, "value"
        if not {"minimum", "q1", "median", "q3", "maximum"}.issubset(rows[0]):
            return None
        title = f"Box plot of {plan.metric}"
    elif kind == "heatmap":
        x, y = "x", "correlation"
        if not {"x", "y", "correlation"}.issubset(rows[0]):
            return None
        title = "Correlation heatmap"
    else:
        return None

    return ChartSpec(
        kind=kind,
        title=title,
        x=str(x),
        y=str(y),
        x_label=str(x),
        y_label=str(y),
        data=rows[:200],
    )


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _scale(value: float, minimum: float, maximum: float, start: float, end: float) -> float:
    if maximum == minimum:
        return (start + end) / 2
    return start + ((value - minimum) / (maximum - minimum)) * (end - start)


def _text(value: Any, *, limit: int = 28) -> str:
    rendered = str(value)
    if len(rendered) > limit:
        rendered = rendered[: limit - 1] + "…"
    return html.escape(rendered, quote=True)


def _axes(spec: ChartSpec) -> list[str]:
    return [
        '<line x1="70" y1="20" x2="70" y2="300" stroke="currentColor"/>',
        '<line x1="70" y1="300" x2="620" y2="300" stroke="currentColor"/>',
        f'<text x="345" y="348" text-anchor="middle">{_text(spec.x_label)}</text>',
        f'<text x="18" y="160" text-anchor="middle" transform="rotate(-90 18 160)">{_text(spec.y_label)}</text>',
    ]


def _bar_or_histogram(spec: ChartSpec) -> list[str]:
    rows = spec.data[:50]
    values = [_number(row.get(spec.y)) or 0.0 for row in rows]
    minimum = min([0.0, *values])
    maximum = max([0.0, *values])
    baseline = _scale(0.0, minimum, maximum, 300, 30)
    slot = 530 / max(1, len(rows))
    width = max(2.0, slot * 0.7)
    parts = _axes(spec)
    for index, (row, value) in enumerate(zip(rows, values, strict=True)):
        x = 80 + index * slot
        value_y = _scale(value, minimum, maximum, 300, 30)
        y, height = min(value_y, baseline), max(1.0, abs(value_y - baseline))
        label = row.get(spec.x)
        if spec.kind == "histogram":
            label = f"{row.get('bin_start'):g}–{row.get('bin_end'):g}"
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
            f'fill="var(--accent, #6d5dfc)"><title>{_text(label)}: {_text(value)}</title></rect>'
        )
        parts.append(
            f'<text x="{x + width / 2:.1f}" y="320" text-anchor="middle" font-size="10">'
            f"{_text(label, limit=12)}</text>"
        )
    return parts


def _line(spec: ChartSpec) -> list[str]:
    rows = spec.data[:100]
    values = [_number(row.get(spec.y)) for row in rows]
    valid = [(index, value) for index, value in enumerate(values) if value is not None]
    if not valid:
        return _axes(spec)
    numeric = [value for _, value in valid]
    minimum, maximum = min(numeric), max(numeric)
    parts = _axes(spec)
    points: list[str] = []
    for index, value in valid:
        x = 80 + index * (530 / max(1, len(rows) - 1))
        y = _scale(value, minimum, maximum, 290, 30)
        points.append(f"{x:.1f},{y:.1f}")
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="var(--accent, #6d5dfc)">'
            f"<title>{_text(rows[index].get(spec.x))}: {_text(value)}</title></circle>"
        )
    parts.insert(
        4,
        f'<polyline points="{" ".join(points)}" fill="none" stroke="var(--accent, #6d5dfc)" stroke-width="3"/>',
    )
    return parts


def _scatter(spec: ChartSpec) -> list[str]:
    points = [
        (x, y)
        for row in spec.data[:200]
        if (x := _number(row.get(spec.x))) is not None
        and (y := _number(row.get(spec.y))) is not None
    ]
    if not points:
        return _axes(spec)
    xs, ys = zip(*points, strict=True)
    parts = _axes(spec)
    for x_value, y_value in points:
        x = _scale(x_value, min(xs), max(xs), 80, 610)
        y = _scale(y_value, min(ys), max(ys), 290, 30)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="var(--accent, #6d5dfc)" fill-opacity=".75">'
            f"<title>{_text(x_value)}, {_text(y_value)}</title></circle>"
        )
    return parts


def _box(spec: ChartSpec) -> list[str]:
    row = spec.data[0]
    values = {name: _number(row.get(name)) for name in ("minimum", "q1", "median", "q3", "maximum")}
    if any(value is None for value in values.values()):
        return _axes(spec)
    minimum, q1, median, q3, maximum = (
        values[name] for name in ("minimum", "q1", "median", "q3", "maximum")
    )
    assert all(value is not None for value in (minimum, q1, median, q3, maximum))
    lo, hi = float(minimum), float(maximum)
    x = {
        name: _scale(float(value), lo, hi, 90, 600)
        for name, value in values.items()
        if value is not None
    }
    parts = _axes(spec)
    parts.extend(
        [
            f'<line x1="{x["minimum"]:.1f}" y1="160" x2="{x["maximum"]:.1f}" y2="160" stroke="var(--accent, #6d5dfc)" stroke-width="3"/>',
            f'<rect x="{x["q1"]:.1f}" y="110" width="{max(1.0, x["q3"] - x["q1"]):.1f}" height="100" fill="var(--accent, #6d5dfc)" fill-opacity=".35" stroke="var(--accent, #6d5dfc)"/>',
            f'<line x1="{x["median"]:.1f}" y1="110" x2="{x["median"]:.1f}" y2="210" stroke="currentColor" stroke-width="3"/>',
            f'<line x1="{x["minimum"]:.1f}" y1="135" x2="{x["minimum"]:.1f}" y2="185" stroke="currentColor"/>',
            f'<line x1="{x["maximum"]:.1f}" y1="135" x2="{x["maximum"]:.1f}" y2="185" stroke="currentColor"/>',
        ]
    )
    return parts


def _heatmap(spec: ChartSpec) -> list[str]:
    rows = spec.data[:144]
    names = list(dict.fromkeys(str(row.get("x")) for row in rows))[:12]
    index = {name: position for position, name in enumerate(names)}
    cell = min(38.0, 470 / max(1, len(names)))
    parts: list[str] = []
    for row in rows:
        x_name, y_name = str(row.get("x")), str(row.get("y"))
        if x_name not in index or y_name not in index:
            continue
        value = _number(row.get("correlation"))
        intensity = 0.0 if value is None else min(1.0, abs(value))
        color = f"rgba({55 if (value or 0) >= 0 else 220}, {110 if (value or 0) >= 0 else 70}, {220 if (value or 0) >= 0 else 80}, {0.15 + intensity * 0.85:.2f})"
        x, y = 130 + index[x_name] * cell, 40 + index[y_name] * cell
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell:.1f}" height="{cell:.1f}" fill="{color}">'
            f"<title>{_text(x_name)} / {_text(y_name)}: {_text(value)}</title></rect>"
        )
    for name, position in index.items():
        offset = 130 + position * cell + cell / 2
        parts.append(
            f'<text x="{offset:.1f}" y="30" text-anchor="middle" font-size="10">{_text(name, limit=10)}</text>'
        )
        parts.append(
            f'<text x="120" y="{45 + position * cell + cell / 2:.1f}" text-anchor="end" font-size="10">{_text(name, limit=10)}</text>'
        )
    return parts


def _enforce_directory_quota(output: Path, incoming_bytes: int) -> None:
    if output.parent.is_symlink():
        raise ValueError("chart storage contains an unsafe symbolic link")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink() or not output.parent.resolve().is_dir():
        raise ValueError("chart storage is not a regular directory")
    entries = [path for path in output.parent.iterdir() if path.suffix == ".svg"]
    if output.is_symlink() or any(path.is_symlink() for path in entries):
        raise ValueError("chart storage contains an unsafe symbolic link")
    assets = [path for path in entries if path.is_file()]
    existing_size = sum(path.stat().st_size for path in assets if path != output)
    existing_count = len([path for path in assets if path != output])
    if existing_count >= MAX_CHARTS_PER_SESSION:
        raise ValueError("chart asset count quota exceeded")
    if incoming_bytes > MAX_SVG_BYTES or existing_size + incoming_bytes > MAX_CHART_DIRECTORY_BYTES:
        raise ValueError("chart storage quota exceeded")


def render_svg(spec: ChartSpec, output: Path) -> Path:
    """Render a small SVG without external chart dependencies or script content."""
    if spec.kind in {"bar", "histogram"}:
        parts = _bar_or_histogram(spec)
    elif spec.kind == "line":
        parts = _line(spec)
    elif spec.kind == "scatter":
        parts = _scatter(spec)
    elif spec.kind == "box":
        parts = _box(spec)
    elif spec.kind == "heatmap":
        parts = _heatmap(spec)
    else:
        raise ValueError(f"unsupported chart kind: {spec.kind}")

    description = f"{spec.title}. Horizontal axis: {spec.x_label}. Vertical axis: {spec.y_label}."
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360" '
        f'role="img" aria-labelledby="chart-title chart-description"><title id="chart-title">{_text(spec.title)}</title>'
        f'<desc id="chart-description">{_text(description, limit=500)}</desc>'
        '<g font-family="system-ui,sans-serif" fill="currentColor">' + "".join(parts) + "</g></svg>"
    )
    encoded = svg.encode("utf-8")
    _enforce_directory_quota(output, len(encoded))
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.stem}-", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output
