"""Persian-aware dataset discovery and bounded schema profiling."""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from dream.dataqa.dataio import LOADABLE_FORMATS, DataReadError, detect_format, sample_rows
from dream.dataqa.models import ColumnProfile, DatasetCandidate, DatasetProfile
from dream.memory import normalize_fa
from dream.security.injection import scan_text

MAX_FILE_BYTES = 500 * 1024 * 1024
MAX_DISCOVERY_FILES = 2_000
_TOKEN = re.compile(r"[\w\u0600-\u06ff]+", re.UNICODE)
_SYNONYMS = {
    "sales": {"revenue", "amount", "orders", "فروش", "درآمد", "مبلغ"},
    "region": {"province", "city", "منطقه", "استان", "شهر", "ناحیه"},
    "date": {"year", "month", "time", "تاریخ", "سال", "ماه", "زمان"},
    "customer": {"client", "buyer", "مشتری", "خریدار"},
    "product": {"item", "category", "محصول", "کالا", "دسته"},
}


def workspace_root() -> Path:
    return Path(os.environ.get("DREAM_WORKSPACE_ROOT", Path.cwd())).resolve()


def _safe_path(raw: str | os.PathLike[str], root: Path) -> Path:
    path = Path(raw).expanduser()
    requested = root / path if not path.is_absolute() else path
    if requested.is_symlink():
        raise DataReadError("symbolic links are not accepted as dataset sources")
    path = requested.resolve()
    if not path.is_relative_to(root):
        raise DataReadError("dataset source must remain inside the Dream workspace")
    return path


def _tokens(text: str) -> set[str]:
    folded = normalize_fa(text).lower().replace("_", " ").replace("-", " ")
    base = set(_TOKEN.findall(folded))
    expanded = set(base)
    for concept, words in _SYNONYMS.items():
        family = {concept, *words}
        if base.intersection(family):
            expanded.update(family)
    return expanded


def _dataset_id(path: Path, source: str) -> str:
    return hashlib.sha256(f"{source}:{path}".encode()).hexdigest()[:24]


def _infer_dtype(values: list[Any]) -> tuple[str, str]:
    present = [value for value in values if value is not None]
    if not present:
        return "unknown", "unknown"
    if all(isinstance(value, bool) for value in present):
        return "boolean", "category"
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in present):
        return "number", "measure"
    dates = 0
    for value in present[:200]:
        if isinstance(value, str):
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
                dates += 1
            except ValueError:
                pass
    if dates >= max(2, math.ceil(min(len(present), 200) * 0.8)):
        return "datetime", "time"
    unique = len({str(value) for value in present})
    return "string", "category" if unique <= min(100, max(20, len(present) // 2)) else "text"


def profile_candidate(candidate: DatasetCandidate, *, sample_limit: int = 5_000) -> DatasetProfile:
    requested_path = Path(candidate.path)
    path = requested_path.resolve()
    if (
        requested_path.is_symlink()
        or not path.is_file()
        or not path.is_relative_to(workspace_root())
    ):
        raise DataReadError("dataset path must remain a regular file inside the Dream workspace")
    if not candidate.loadable:
        return DatasetProfile(
            dataset_id=candidate.dataset_id,
            name=candidate.name,
            relative_path=candidate.relative_path,
            format=candidate.format,
            row_count=candidate.row_count or 0,
            sampled_rows=0,
            columns=[],
            loadable=False,
            limitation=candidate.limitation,
        )
    rows, truncated = sample_rows(path, candidate.format, limit=sample_limit)
    headers = list(rows[0]) if rows else candidate.columns
    profiles: list[ColumnProfile] = []
    findings = 0
    for header in headers:
        values = [row.get(header) for row in rows]
        present = [value for value in values if value is not None]
        dtype, role = _infer_dtype(values)
        counts = Counter(str(value)[:200] for value in present)
        numeric = [
            float(value)
            for value in present
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        if dtype == "number" and numeric:
            minimum: Any = min(numeric)
            maximum: Any = max(numeric)
            mean = sum(numeric) / len(numeric)
        else:
            strings = [str(value) for value in present]
            minimum = min(strings) if strings else None
            maximum = max(strings) if strings else None
            mean = None
        profiles.append(
            ColumnProfile(
                name=header,
                dtype=dtype,
                role=role,
                null_count=len(values) - len(present),
                unique_count=len(counts),
                minimum=minimum,
                maximum=maximum,
                mean=mean,
                top_values=[
                    {"value": value, "count": count} for value, count in counts.most_common(5)
                ],
            )
        )
        for value in present[:250]:
            if isinstance(value, str) and not scan_text(value, mode="strip").clean:
                findings += 1
    row_count = len(rows) if not truncated else max(candidate.row_count or 0, len(rows))
    return DatasetProfile(
        dataset_id=candidate.dataset_id,
        name=candidate.name,
        relative_path=candidate.relative_path,
        format=candidate.format,
        row_count=row_count,
        sampled_rows=len(rows),
        columns=profiles,
        loadable=True,
        injection_findings=findings,
    )


def _registry_candidates(root: Path) -> list[DatasetCandidate]:
    registry = Path(os.environ.get("DREAM_DATASETS_DIR", root / "data/datasets"))
    registry = registry.resolve()
    index = registry / "index.json"
    if not index.exists() or not registry.is_relative_to(root):
        return []
    try:
        import json

        entries = json.loads(index.read_text(encoding="utf-8")).get("datasets", [])
    except (OSError, ValueError):
        return []
    found: list[DatasetCandidate] = []
    for entry in entries[:MAX_DISCOVERY_FILES]:
        dataset_id = str(entry.get("dataset_id", ""))
        requested_path = registry / dataset_id / str(entry.get("active_file", ""))
        path = requested_path.resolve()
        if requested_path.is_symlink() or not path.is_file() or not path.is_relative_to(root):
            continue
        fmt = str(entry.get("format") or detect_format(path) or "unknown")
        shape = entry.get("shape") or [None, None]
        tags = entry.get("tags", [])
        metadata = [str(entry.get("description", ""))[:500]]
        if isinstance(tags, list):
            metadata.extend(str(tag)[:100] for tag in tags[:20])
        found.append(
            DatasetCandidate(
                dataset_id=dataset_id,
                name=str(entry.get("name") or path.stem),
                path=str(path),
                relative_path=str(path.relative_to(root)),
                format=fmt,
                source="registry",
                score=0,
                reasons=[],
                columns=[str(value) for value in entry.get("columns", [])],
                row_count=shape[0] if isinstance(shape, list) and shape else None,
                loadable=fmt in LOADABLE_FORMATS,
                limitation=None
                if fmt in LOADABLE_FORMATS
                else "optional data reader is not installed",
                size_bytes=path.stat().st_size,
                metadata=[item for item in metadata if item],
            )
        )
    return found


def rank_candidate(candidate: DatasetCandidate, query: str) -> None:
    """Apply bounded lexical/light-semantic relevance scoring in-place."""
    wanted = _tokens(query)
    name_tokens = _tokens(candidate.name)
    path_tokens = _tokens(candidate.relative_path)
    schema_tokens = _tokens(" ".join(candidate.columns))
    metadata_tokens = _tokens(" ".join(candidate.metadata))
    all_tokens = name_tokens | path_tokens | schema_tokens | metadata_tokens
    overlap = wanted.intersection(all_tokens)
    name_overlap = wanted.intersection(name_tokens)
    schema_overlap = wanted.intersection(schema_tokens)
    metadata_overlap = wanted.intersection(metadata_tokens)
    denominator = max(1, len(wanted))

    candidate.score = round(
        len(overlap) / denominator * 0.55
        + len(name_overlap) / denominator * 0.25
        + len(schema_overlap) / denominator * 0.15
        + len(metadata_overlap) / denominator * 0.05,
        4,
    )
    candidate.reasons = []
    if name_overlap:
        candidate.reasons.append("dataset name matches: " + ", ".join(sorted(name_overlap)[:5]))
    if schema_overlap:
        candidate.reasons.append("schema matches: " + ", ".join(sorted(schema_overlap)[:5]))
    if metadata_overlap:
        candidate.reasons.append("metadata matches: " + ", ".join(sorted(metadata_overlap)[:5]))
    path_only = overlap - name_overlap - schema_overlap - metadata_overlap
    if path_only:
        candidate.reasons.append("path matches: " + ", ".join(sorted(path_only)[:5]))
    if candidate.source == "registry":
        candidate.score += 0.05
        candidate.reasons.append("registered Dream dataset")
    if not wanted:
        candidate.score += 0.01
        candidate.reasons.append("available dataset")
    if not candidate.loadable:
        candidate.score -= 0.1


def discover(
    query: str = "", source: str | None = None, *, limit: int = 20
) -> list[DatasetCandidate]:
    root = workspace_root()
    candidates: list[DatasetCandidate] = []
    if source in (None, "", "everything", "registry"):
        candidates.extend(_registry_candidates(root))
    if source not in (None, "", "everything", "registry"):
        selected = _safe_path(source, root)
        if not selected.exists():
            raise DataReadError("dataset source does not exist")
        paths = [selected] if selected.is_file() else selected.rglob("*")
    elif source in (None, "", "everything"):
        paths = root.rglob("*")
    else:
        paths = []
    known = {Path(item.path) for item in candidates}
    for path in paths:
        if len(candidates) >= MAX_DISCOVERY_FILES:
            break
        if not path.is_file() or path.is_symlink() or path in known:
            continue
        fmt = detect_format(path)
        if not fmt:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_FILE_BYTES:
            continue
        rel = str(path.resolve().relative_to(root))
        candidates.append(
            DatasetCandidate(
                dataset_id=_dataset_id(path.resolve(), "file"),
                name=path.stem,
                path=str(path.resolve()),
                relative_path=rel,
                format=fmt,
                source="folder",
                score=0,
                reasons=[],
                loadable=fmt in LOADABLE_FORMATS,
                limitation=None
                if fmt in LOADABLE_FORMATS
                else "optional data reader is not installed",
                size_bytes=size,
            )
        )
    for candidate in candidates:
        rank_candidate(candidate, query)
    candidates.sort(key=lambda item: (-item.score, item.name.lower(), item.relative_path))
    return candidates[: max(1, min(limit, 100))]
