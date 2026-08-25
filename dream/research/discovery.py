"""Multi-source discovery: find and profile the data a topic actually needs.

A research *space* is one workspace folder. The engine walks it once, refuses
anything outside it (no traversal, no symlink escape), ingests supported
sources through the existing dataset registry — so from that moment on the
agent only ever sees a 32-hex ``dataset_id``, never a raw path — and scores
each source for relevance to the objective.

Relevance is deterministic on purpose: a lexical overlap between the objective
and the source's name plus column headers, with Persian normalisation applied
so «فروش» and "فروش" match. Offline runs and LLM runs therefore discover the
same sources, which is what makes the whole engine testable with EchoBackend.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from dream.memory import normalize_fa
from dream.research.errors import ResearchError, ResearchSecurityError

logger = logging.getLogger("dream.research.discovery")

__all__ = [
    "DEFAULT_MAX_SOURCES",
    "SUPPORTED_SUFFIXES",
    "discover_sources",
    "relevance_score",
    "safe_workspace",
]

SUPPORTED_SUFFIXES = {
    ".csv": "csv",
    ".tsv": "tsv",
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
}

#: Read as *context*, never ingested as a table.
DOC_SUFFIXES = {".md", ".txt"}

DEFAULT_MAX_SOURCES = 8
MAX_WALK_ENTRIES = 5000
MAX_DOC_CHARS = 20000

_WORD_RE = re.compile(r"[0-9A-Za-z\u0600-\u06FF]{2,}")
_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "from", "that", "this", "into", "over",
        "what", "why", "how", "are", "was", "were", "our", "their", "data",
        "dataset", "analysis", "report", "csv", "xlsx",
        "از", "به", "در", "را", "که", "این", "آن", "برای", "با", "های", "ها",
    }
)


def safe_workspace(path: Any) -> Path:
    """Resolve a research space, refusing anything unusable or sensitive.

    The space is the agent's whole world (Hops' scoping principle): it is
    resolved once, checked against Dream's sensitive-path denylist — a system
    directory, a credential store, or Dream's own private data can never be a
    research space — and everything discovered later must stay inside it.
    """
    from dream.security.pathsafety import is_sensitive_path

    if not isinstance(path, str) or not path.strip():
        raise ResearchError("workspace must be a non-empty path string")
    resolved = Path(os.path.expanduser(path.strip())).resolve()
    if not resolved.is_dir():
        raise ResearchError(f"workspace is not a directory: {path}")
    hit = is_sensitive_path(resolved)
    if hit is not None:
        raise ResearchSecurityError(
            f"refusing to use a sensitive location as a research space: {hit.reason_en}"
        )
    return resolved


def _tokens(text: str) -> set[str]:
    folded = normalize_fa(str(text or "")).lower()
    return {word for word in _WORD_RE.findall(folded) if word not in _STOPWORDS}


def relevance_score(objective: str, name: str, columns: list[str]) -> float:
    """Lexical overlap in [0, 1] between an objective and a source's schema.

    Deterministic by construction: the same objective and schema always score
    the same, offline or online.
    """
    goal = _tokens(objective)
    if not goal:
        return 0.0
    haystack = _tokens(name) | {tok for column in columns for tok in _tokens(str(column))}
    if not haystack:
        return 0.0
    hits = goal & haystack
    # Weight column hits slightly above name hits: a matching column is real
    # evidence the table carries the measure being asked about.
    column_tokens = {tok for column in columns for tok in _tokens(str(column))}
    weighted = sum(1.0 if token in column_tokens else 0.7 for token in hits)
    return round(min(1.0, weighted / max(3.0, float(len(goal)))), 4)


def _iter_candidates(root: Path) -> list[Path]:
    found: list[Path] = []
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "charts")
        for filename in sorted(filenames):
            seen += 1
            if seen > MAX_WALK_ENTRIES:
                logger.warning("workspace walk hit the %d-entry cap", MAX_WALK_ENTRIES)
                return found
            candidate = Path(dirpath) / filename
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if not resolved.is_relative_to(root):  # symlink escape
                logger.warning("skipping %s: resolves outside the workspace", filename)
                continue
            if resolved.is_file():
                found.append(resolved)
    return found


def read_methodology_doc(root: Path) -> str:
    """Return a user-authored methodology doc, guarded as untrusted text.

    Document-as-instruction: a ``METHODOLOGY.md``/``RESEARCH.md`` in the space
    steers the plan. It still crosses the injection gate first — it is user
    guidance, not a privileged instruction channel.
    """
    from dream.security.injection import guard_untrusted

    for name in ("METHODOLOGY.md", "methodology.md", "RESEARCH.md", "research.md"):
        candidate = root / name
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")[:MAX_DOC_CHARS]
        except OSError:
            continue
        return guard_untrusted(text, source=f"research.methodology:{name}")
    return ""


def discover_sources(
    runtime: Any,
    workspace: str | Path,
    objective: str,
    *,
    max_sources: int = DEFAULT_MAX_SOURCES,
    min_relevance: float = 0.0,
) -> list[dict[str, Any]]:
    """Ingest and rank the workspace's data sources for one objective.

    Each returned entry is registry-shaped (``dataset_id``, ``name``,
    ``format``, ``shape``, ``columns``, ``relevance``). Sources that fail to
    ingest are reported with an ``error`` instead of aborting discovery: one
    corrupt CSV must not sink a research run.
    """
    root = workspace if isinstance(workspace, Path) else safe_workspace(workspace)
    if not isinstance(max_sources, int) or not 1 <= max_sources <= 50:
        raise ResearchError("max_sources must be an integer in [1, 50]")

    results: list[dict[str, Any]] = []
    for candidate in _iter_candidates(root):
        suffix = candidate.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            continue
        if candidate.name.startswith("_") or candidate.name == "index.json":
            continue
        try:
            loaded = runtime.load_data(str(candidate), candidate.stem)
        except ResearchSecurityError:
            raise
        except Exception as exc:  # a bad file is a finding, not a crash
            logger.info("skipping unreadable source %s: %s", candidate.name, exc)
            results.append(
                {
                    "name": candidate.stem,
                    "filename": candidate.name,
                    "format": SUPPORTED_SUFFIXES[suffix],
                    "error": str(exc)[:300],
                    "relevance": 0.0,
                }
            )
            continue
        entry = {
            "dataset_id": loaded["dataset_id"],
            "name": loaded["name"],
            "filename": loaded["filename"],
            "format": loaded["format"],
            "shape": loaded["shape"],
            "columns": loaded["columns"],
            "relevance": relevance_score(objective, loaded["name"], loaded["columns"]),
        }
        results.append(entry)

    usable = [r for r in results if r.get("dataset_id")]
    failed = [r for r in results if not r.get("dataset_id")]
    usable.sort(key=lambda r: (-r["relevance"], r["name"]))
    selected = [r for r in usable if r["relevance"] >= min_relevance][:max_sources]
    if not selected:
        # Relevance is a ranking aid, never a reason to end up with nothing.
        selected = usable[:max_sources]
    return selected + failed[: max(0, max_sources - len(selected))]
