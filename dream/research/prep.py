"""Execution-grounded data preparation (DeepPrep-style).

Cleaning is *proposed* from the profile of the real table, applied through the
existing validated pipeline in :mod:`dream.skills.data_science`, and then
re-profiled so the next proposal reacts to the table's new state. Nothing is
guessed: every operation is justified by a statistic that came out of the
sandbox, and the schema is tracked across renames and drops so a later
operation can never reference a column that no longer exists.

The engine calls this module; it never re-implements a cleaning op.
"""

from __future__ import annotations

import logging
from typing import Any

from dream.research.errors import ResearchError

logger = logging.getLogger("dream.research.prep")

__all__ = ["SchemaTracker", "propose_operations", "prepare_dataset"]

#: Below this fraction of missing values, imputing is noise; above it, the
#: column is too damaged to impute and is reported as a limitation instead.
_IMPUTE_FLOOR = 0.005
_IMPUTE_CEILING = 0.40


class SchemaTracker:
    """Follow column identity across a cleaning pipeline.

    ``clean_data`` validates each operation against the *current* column list,
    so the tracker mirrors its rules exactly: renames move a name, drops
    remove it, and one-hot encoding consumes the source column.
    """

    def __init__(self, columns: list[str]) -> None:
        self.columns = [str(c) for c in columns]
        self.history: list[dict[str, Any]] = []

    def apply(self, op: dict[str, Any]) -> None:
        tag = op.get("op")
        if tag == "rename_column":
            old, new = op.get("column"), op.get("new_name")
            self.columns = [new if c == old else c for c in self.columns]
        elif tag == "drop_column":
            self.columns = [c for c in self.columns if c != op.get("column")]
        elif tag == "encode_categorical" and op.get("method") == "onehot":
            self.columns = [c for c in self.columns if c != op.get("column")]
        self.history.append(dict(op))

    def knows(self, column: Any) -> bool:
        return column in self.columns


def propose_operations(
    profile: dict[str, Any],
    tracker: SchemaTracker,
    *,
    max_ops: int = 8,
) -> list[dict[str, Any]]:
    """Derive cleaning operations from an actual profile — runtime feedback in.

    Only three families are proposed, each with an explicit numeric trigger:
    duplicate removal, bounded imputation, and numeric coercion of a column
    pandas read as text. Anything more opinionated belongs to the analyst.
    """
    if not isinstance(profile, dict):
        raise ResearchError("profile must be an object")
    rows = int(profile.get("row_count") or 0)
    if rows <= 0:
        return []
    operations: list[dict[str, Any]] = []

    duplicates = profile.get("duplicate_rows")
    if isinstance(duplicates, int) and duplicates > 0:
        operations.append({"op": "remove_duplicates"})

    columns = profile.get("columns") or {}
    if not isinstance(columns, dict):
        return operations

    for name, entry in sorted(columns.items()):
        if len(operations) >= max_ops:
            break
        if not isinstance(entry, dict) or not tracker.knows(name):
            continue
        missing = float(entry.get("missing") or 0) / float(rows)
        role = entry.get("role")
        if _IMPUTE_FLOOR <= missing <= _IMPUTE_CEILING:
            if role == "numeric":
                operations.append({"op": "fill_na", "column": name, "strategy": "median"})
            elif role in ("categorical", "boolean"):
                operations.append({"op": "fill_na", "column": name, "strategy": "mode"})
    for op in operations:
        tracker.apply(op)
    return operations


def prepare_dataset(
    runtime: Any,
    dataset_id: str,
    *,
    max_rounds: int = 2,
    emit: Any = None,
) -> dict[str, Any]:
    """Iterate profile → propose → clean → re-profile until the table settles.

    Returns the prep trace: every round's trigger statistics, the operations
    applied, and the before/after row counts. The trace is what the report
    cites in its Methodology and Limitations sections — the numbers there are
    executed numbers, not claims.
    """
    if not isinstance(max_rounds, int) or not 1 <= max_rounds <= 5:
        raise ResearchError("max_rounds must be an integer in [1, 5]")

    def _emit(event: str, **payload: Any) -> None:
        if emit is not None:
            try:
                emit(event, **payload)
            except Exception:  # progress must never break the pipeline
                logger.debug("prep progress callback failed", exc_info=True)

    profile = runtime.profile_data(dataset_id)
    tracker = SchemaTracker([str(c) for c in (profile.get("columns") or {})])
    rounds: list[dict[str, Any]] = []
    limitations: list[str] = []

    columns = profile.get("columns") or {}
    rows = int(profile.get("row_count") or 0)
    for name, entry in sorted(columns.items()) if isinstance(columns, dict) else []:
        if not isinstance(entry, dict) or rows <= 0:
            continue
        missing = float(entry.get("missing") or 0) / float(rows)
        if missing > _IMPUTE_CEILING:
            limitations.append(
                f"column '{name}' is {missing * 100:.1f}% missing and was left "
                "un-imputed; treat its statistics as partial"
            )

    for index in range(max_rounds):
        operations = propose_operations(profile, tracker)
        if not operations:
            break
        _emit("prep.round", round=index + 1, operations=[op["op"] for op in operations])
        try:
            cleaned = runtime.clean_data(dataset_id, operations)
        except Exception as exc:  # degrade: keep the raw table, note why
            logger.info("cleaning round %d failed: %s", index + 1, exc)
            limitations.append(f"cleaning round {index + 1} failed: {str(exc)[:200]}")
            break
        rounds.append(
            {
                "round": index + 1,
                "operations": operations,
                "rows_before": cleaned.get("rows_before"),
                "rows_after": cleaned.get("rows_after"),
                "columns": cleaned.get("columns"),
            }
        )
        profile = runtime.profile_data(dataset_id)
        tracker = SchemaTracker([str(c) for c in (profile.get("columns") or {})])

    return {
        "dataset_id": dataset_id,
        "rounds": rounds,
        "final_profile": profile,
        "limitations": limitations,
        "cleaned": bool(rounds),
    }
