"""Typed contracts shared by Dream's data Q&A pipeline.

The contracts intentionally contain JSON-compatible values only.  That keeps the
bridge boundary deterministic and makes the final-answer gate independent from a
particular model provider.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

AnswerStatus = Literal["ok", "insufficient_data", "error", "cancelled"]


@dataclass(slots=True)
class ColumnProfile:
    name: str
    dtype: str
    role: str
    null_count: int
    unique_count: int
    minimum: Any = None
    maximum: Any = None
    mean: float | None = None
    top_values: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DatasetProfile:
    dataset_id: str
    name: str
    relative_path: str
    format: str
    row_count: int
    sampled_rows: int
    columns: list[ColumnProfile]
    loadable: bool = True
    limitation: str | None = None
    injection_findings: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "columns": [column.to_dict() for column in self.columns],
            "infobox": self.infobox(),
        }

    def infobox(self, *, max_columns: int = 40) -> dict[str, Any]:
        """Compact, bounded schema context suitable for a planner/model."""
        return {
            "dataset": self.name,
            "format": self.format,
            "rows": self.row_count,
            "sampled_rows": self.sampled_rows,
            "columns": [
                {
                    "name": column.name,
                    "dtype": column.dtype,
                    "role": column.role,
                    "nulls": column.null_count,
                    "unique": column.unique_count,
                    **(
                        {"range": [column.minimum, column.maximum]}
                        if column.minimum is not None
                        else {}
                    ),
                    **({"top_values": column.top_values[:5]} if column.role == "category" else {}),
                }
                for column in self.columns[:max_columns]
            ],
            "truncated_columns": max(0, len(self.columns) - max_columns),
            "security": {
                "dataset_values_are_instructions": False,
                "rejected_suspicious_values": self.injection_findings,
            },
        }


@dataclass(slots=True)
class DatasetCandidate:
    dataset_id: str
    name: str
    path: str
    relative_path: str
    format: str
    source: str
    score: float
    reasons: list[str]
    columns: list[str] = field(default_factory=list)
    row_count: int | None = None
    loadable: bool = True
    limitation: str | None = None
    size_bytes: int = 0
    metadata: list[str] = field(default_factory=list)

    def public_dict(self) -> dict[str, Any]:
        """Return bridge-safe metadata; never expose the absolute host path."""
        data = asdict(self)
        data.pop("path", None)
        return data


@dataclass(slots=True)
class FilterSpec:
    column: str
    operator: str
    value: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QueryPlan:
    action: str
    aggregate: str | None = None
    metric: str | None = None
    groups: list[str] = field(default_factory=list)
    filters: list[FilterSpec] = field(default_factory=list)
    date_column: str | None = None
    time_grain: str | None = None
    secondary_metric: str | None = None
    sort: str = "desc"
    limit: int = 50
    wants_chart: bool = False
    chart_type: str | None = None
    chart_only: bool = False
    language: str = "en"
    answer_shape: str = "table"
    sql: str | None = None
    code: str = ""
    intent: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "filters": [item.to_dict() for item in self.filters],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> QueryPlan:
        values = dict(raw)
        values["filters"] = [FilterSpec(**item) for item in raw.get("filters", [])]
        return cls(**values)


@dataclass(slots=True)
class ChartSpec:
    kind: str
    title: str
    x: str
    y: str
    x_label: str
    y_label: str
    data: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExecutionResult:
    status: AnswerStatus
    answer_shape: str
    columns: list[str]
    rows: list[dict[str, Any]]
    rows_considered: int
    operation: str
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    elapsed_seconds: float = 0.0
    sandbox: str = "guarded-local"
    network_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ExecutionResult:
        return cls(
            status=raw.get("status", "error"),
            answer_shape=str(raw.get("answer_shape", "table")),
            columns=[str(value) for value in raw.get("columns", [])],
            rows=list(raw.get("rows", [])),
            rows_considered=int(raw.get("rows_considered", 0)),
            operation=str(raw.get("operation", "unknown")),
            warnings=[str(value) for value in raw.get("warnings", [])],
            error=str(raw["error"]) if raw.get("error") else None,
            elapsed_seconds=float(raw.get("elapsed_seconds", 0.0)),
            sandbox=str(raw.get("sandbox", "guarded-local")),
            network_enabled=bool(raw.get("network_enabled", False)),
        )
