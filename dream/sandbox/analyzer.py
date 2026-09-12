"""Data Science Analyzer: Automated dataset profiling, statistics, and tabular analysis."""

from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path

from dream.sandbox.types import DatasetSummary
from dream.security.pathsafety import is_sensitive_path


class DataScienceAnalyzer:
    """Automated statistical summarization and column profiling for tabular datasets."""

    def analyze_tabular_data(
        self,
        data_content_or_path: str,
        delimiter: str = ",",
    ) -> DatasetSummary:
        """Parse raw CSV/JSON string or load from file, generating statistical breakdown."""
        raw_rows: list[dict[str, str]] = []
        content = ""
        is_path = False

        raw_str = data_content_or_path.strip()
        if (
            "\n" not in data_content_or_path
            and len(data_content_or_path) < 1024
            and not raw_str.startswith(("{", "["))
        ):
            try:
                p = Path(data_content_or_path)
                if p.exists() and p.is_file():
                    is_path = True
            except OSError:
                is_path = False

        if is_path:
            if is_sensitive_path(data_content_or_path):
                raise PermissionError(
                    f"Permission denied: '{data_content_or_path}' is a sensitive system path."
                )
            content = Path(data_content_or_path).read_text(encoding="utf-8")
        else:
            content = raw_str

        # Parse JSON or CSV
        if content.startswith("[") or content.startswith("{"):
            try:
                parsed_json = json.loads(content)
                if isinstance(parsed_json, list):
                    raw_rows = [
                        {k: str(v) for k, v in row.items()}
                        for row in parsed_json
                        if isinstance(row, dict)
                    ]
                elif isinstance(parsed_json, dict):
                    raw_rows = [{k: str(v) for k, v in parsed_json.items()}]
            except Exception:
                pass

        if not raw_rows:
            reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
            raw_rows = list(reader)

        if not raw_rows:
            return DatasetSummary(
                total_rows=0,
                total_columns=0,
                column_names=[],
                column_types={},
                null_counts={},
                numeric_stats={},
                sample_preview=[],
            )

        col_names = list(raw_rows[0].keys())
        total_rows = len(raw_rows)
        total_cols = len(col_names)

        col_types: dict[str, str] = {}
        null_counts: dict[str, int] = {}
        numeric_stats: dict[str, dict[str, float]] = {}

        for col in col_names:
            values = [row.get(col, "").strip() for row in raw_rows]
            nulls = sum(1 for v in values if v == "" or v.lower() in ("null", "none", "nan"))
            null_counts[col] = nulls

            # Check if numeric
            non_empty = [v for v in values if v not in ("", "null", "none", "nan")]
            is_num = False
            num_vals: list[float] = []

            if non_empty:
                try:
                    num_vals = [float(v.replace(",", "")) for v in non_empty]
                    is_num = True
                except ValueError:
                    is_num = False

            if is_num and num_vals:
                col_types[col] = "float" if any("." in v for v in non_empty) else "integer"
                avg = sum(num_vals) / len(num_vals)
                variance = (
                    sum((x - avg) ** 2 for x in num_vals) / len(num_vals)
                    if len(num_vals) > 1
                    else 0.0
                )
                numeric_stats[col] = {
                    "mean": round(avg, 2),
                    "min": round(min(num_vals), 2),
                    "max": round(max(num_vals), 2),
                    "std": round(math.sqrt(variance), 2),
                }
            else:
                col_types[col] = "string"

        return DatasetSummary(
            total_rows=total_rows,
            total_columns=total_cols,
            column_names=col_names,
            column_types=col_types,
            null_counts=null_counts,
            numeric_stats=numeric_stats,
            sample_preview=[dict(r) for r in raw_rows[:5]],
        )

    def format_summary_markdown(self, summary: DatasetSummary) -> str:
        """Format dataset profiling summary into a clean Markdown report."""
        lines = [
            "## 📊 گزارش تحلیل داده‌ها (Dataset Profile)",
            f"- تعداد سطرها (Rows): {summary.total_rows:,}",
            f"- تعداد ستون‌ها (Columns): {summary.total_columns}",
            "",
            "### 📋 جدول مشخصات ستون‌ها",
            "| ستون | نوع داده | مقادیر خالی (Nulls) | میانگین (Mean) | حداقل-حداکثر (Min-Max) |",
            "|---|---|---|---|---|",
        ]

        for col in summary.column_names:
            c_type = summary.column_types.get(col, "string")
            nulls = summary.null_counts.get(col, 0)
            stats = summary.numeric_stats.get(col)

            if stats:
                mean_str = f"{stats['mean']:.2f}"
                min_max_str = f"{stats['min']:.1f} - {stats['max']:.1f}"
            else:
                mean_str = "-"
                min_max_str = "-"

            lines.append(f"| `{col}` | {c_type} | {nulls} | {mean_str} | {min_max_str} |")

        return "\n".join(lines)
