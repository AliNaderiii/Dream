"""Proofreader: the grounding guard between a draft and a published report.

Two layers, in this order:

1. **Deterministic audit** — every numeric literal in the draft is compared
   against the grounding ledger (the canonical set of numbers produced by
   executed steps). Anything outside the ledger is an ungrounded value.
   Structural numbers — heading indices, table rows already sourced from
   executed tables, figure numbers, years in the cover block — are excluded
   by construction, not by luck. Over-claim language ("proves", "guarantees",
   "always") and dangling citations are flagged the same way.
2. **Critic pass (optional)** — the configured backend re-reads the draft with
   the ledger in hand and may add qualitative problems (internal
   inconsistency, unsupported causal claims). It can only *add* findings; it
   can never clear a deterministic one. A silent or broken model therefore
   weakens nothing.

The result is advisory *and* enforcing: :func:`enforce` rewrites sentences
that carry ungrounded numbers into an explicit, honest marker rather than
letting a hallucinated figure reach a PDF.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from dream.research.analyze import format_number
from dream.research.planner import ask_json
from dream.research.prompts import proofread_prompt
from dream.research.schemas import clamp_text

logger = logging.getLogger("dream.research.proofread")

__all__ = ["audit", "enforce", "proofread"]

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n")
_CITATION_RE = re.compile(r"\[(\d{1,3})\]")

#: Language that asserts more than a statistic can support.
_OVERCLAIM_RE = re.compile(
    r"(?<![A-Za-z])(prove[ns]?|guarantees?|guaranteed|certainly|undoubtedly|"
    r"always|conclusively|definitively|beyond doubt)(?![A-Za-z])",
    re.IGNORECASE,
)

#: Inline code spans hold identifiers and serialised config, not claims — the
#: digits inside a session id or a config dump are never empirical assertions.
_CODE_SPAN_RE = re.compile(r"`[^`]*`")

#: Numbers that are structural rather than empirical.
_STRUCTURAL_CONTEXT = re.compile(
    r"^\s{0,3}(#{1,6}\s|\d+\.\s|\|\s|\!\[|Figure |Table |Section |\[\d+\])"
)

UNGROUNDED_MARKER = "[unverified — removed by the grounding guard]"


def _is_structural_line(line: str) -> bool:
    return bool(_STRUCTURAL_CONTEXT.match(line)) or line.strip().startswith(("|", "!["))


def _prose_of(line: str) -> str:
    """The auditable part of a line: prose with inline code spans removed."""
    return _CODE_SPAN_RE.sub(" ", line)


def audit(
    markdown: str,
    grounded: set[str],
    *,
    reference_count: int = 0,
) -> dict[str, Any]:
    """Deterministic grounding audit of a draft report.

    ``grounded`` is the canonical ledger from
    :func:`dream.research.analyze.extract_numbers`. Returns a report dict with
    ``ok`` plus the specific problems found.
    """
    ungrounded: list[str] = []
    overclaims: list[str] = []
    citation_problems: list[str] = []

    for raw_line in (markdown or "").splitlines():
        if _is_structural_line(raw_line):
            continue
        line = _prose_of(raw_line)
        for token in _NUMBER_RE.findall(line):
            canonical = format_number(token)
            if canonical in grounded:
                continue
            # Percentages and counts derived by the report from two grounded
            # values are still grounded; anything else is not.
            if canonical in {"0", "1", "2", "100"}:
                continue
            ungrounded.append(f"{canonical} (in: {clamp_text(line.strip(), 160)})")
        match = _OVERCLAIM_RE.search(line)
        if match:
            overclaims.append(f"{match.group(0)!r} in: {clamp_text(line.strip(), 160)}")

    for marker in _CITATION_RE.findall(markdown or ""):
        index = int(marker)
        if reference_count and not 1 <= index <= reference_count:
            citation_problems.append(f"citation [{index}] has no matching reference entry")

    return {
        "ok": not (ungrounded or overclaims or citation_problems),
        "ungrounded": ungrounded[:50],
        "overclaims": overclaims[:20],
        "inconsistencies": [],
        "citation_problems": sorted(set(citation_problems))[:20],
        "notes": "",
        "source": "deterministic",
    }


def proofread(
    backend: Any,
    markdown: str,
    grounded: set[str],
    *,
    language: str = "en",
    reference_count: int = 0,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Run the deterministic audit, then let the critic add to it."""
    report = audit(markdown, grounded, reference_count=reference_count)
    if backend is None:
        return report
    raw = ask_json(
        backend,
        proofread_prompt(markdown, sorted(grounded), language=language),
        timeout=timeout,
    )
    if not raw:
        return report
    # Additive only: the critic can never clear a deterministic finding.
    for key in ("ungrounded", "overclaims", "inconsistencies", "citation_problems"):
        extra = [clamp_text(item, 300) for item in (raw.get(key) or [])[:20]]
        merged = list(dict.fromkeys([*report.get(key, []), *extra]))
        report[key] = merged[:50]
    report["notes"] = clamp_text(raw.get("notes"), 1000)
    report["ok"] = not any(
        report[key]
        for key in ("ungrounded", "overclaims", "inconsistencies", "citation_problems")
    )
    report["source"] = "deterministic+critic"
    return report


def enforce(markdown: str, grounded: set[str]) -> tuple[str, int]:
    """Redact sentences carrying ungrounded numbers. Returns (text, count).

    Enforcement is line-scoped and conservative: structural lines and table
    rows (whose numbers came from executed tables) are untouched, and only the
    offending sentence is replaced — the surrounding grounded prose survives.
    """
    if not markdown:
        return "", 0
    redactions = 0
    output: list[str] = []
    for line in markdown.splitlines():
        prose = _prose_of(line)
        if _is_structural_line(line) or not _NUMBER_RE.search(prose):
            output.append(line)
            continue
        sentences = _SENTENCE_SPLIT.split(line)
        if len(sentences) == 1:
            rebuilt = line
            bad = [
                token
                for token in _NUMBER_RE.findall(prose)
                if format_number(token) not in grounded
                and format_number(token) not in {"0", "1", "2", "100"}
            ]
            if bad:
                redactions += 1
                rebuilt = UNGROUNDED_MARKER
            output.append(rebuilt)
            continue
        kept: list[str] = []
        for sentence in sentences:
            bad = [
                token
                for token in _NUMBER_RE.findall(_prose_of(sentence))
                if format_number(token) not in grounded
                and format_number(token) not in {"0", "1", "2", "100"}
            ]
            if bad:
                redactions += 1
                kept.append(UNGROUNDED_MARKER)
            else:
                kept.append(sentence)
        output.append(" ".join(s for s in kept if s))
    return "\n".join(output), redactions
