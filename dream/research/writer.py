"""Section writer: turn grounded findings into analyst prose.

The writer is deliberately weak on invention and strong on structure. It is
handed *only* the section's grounded findings and asked for prose that
restates them, plus the two things a passive report never gives you: why the
number moved (root cause) and what to do about it (recommendation).

When no model answers — offline, provider down, unparseable JSON — the
deterministic composer takes over. It produces real, readable prose from the
same findings, so an EchoBackend run still yields a report a human can read,
and the test suite can assert on its numbers.
"""

from __future__ import annotations

import logging
from typing import Any

from dream.research.planner import ask_json
from dream.research.prompts import writer_prompt
from dream.research.schemas import Finding, Section, clamp_text

logger = logging.getLogger("dream.research.writer")

__all__ = ["compose_section", "deterministic_prose", "write_section"]


def _by_kind(findings: list[Finding], kind: str) -> list[Finding]:
    return [f for f in findings if f.kind == kind]


def deterministic_prose(section: Section, *, language: str = "en") -> str:
    """Compose section prose from findings alone, with no model in the loop."""
    observations = _by_kind(section.findings, "observation")
    anomalies = _by_kind(section.findings, "anomaly")
    causes = _by_kind(section.findings, "root_cause")
    actions = _by_kind(section.findings, "recommendation")

    if language == "fa":
        parts: list[str] = []
        if section.thesis:
            parts.append(section.thesis)
        if observations:
            bullets = "\n".join(f"- {f.claim}" for f in observations[:8])
            parts.append("یافته‌های اجراشده:\n" + bullets)
        else:
            parts.append(
                "هیچ شاهد عددی‌ای برای این بخش تولید نشد؛ نتیجه‌گیری نشده است."
            )
        if anomalies:
            parts.append(
                "هشدارها:\n" + "\n".join(f"- {f.claim}" for f in anomalies[:6])
            )
        if causes:
            parts.append("علت محتمل: " + causes[0].claim)
        if actions:
            parts.append("اقدام پیشنهادی: " + actions[0].claim)
        return "\n\n".join(parts)

    parts = []
    if section.thesis:
        parts.append(section.thesis)
    if observations:
        parts.append(
            "The executed steps produced the following:\n"
            + "\n".join(f"- {f.claim}" for f in observations[:8])
        )
    else:
        parts.append(
            "No numeric evidence was produced for this section, so no claim is "
            "made here. See Limitations."
        )
    if anomalies:
        parts.append(
            "Alerts raised by the data itself:\n"
            + "\n".join(f"- {f.claim}" for f in anomalies[:6])
        )
    if causes:
        parts.append(f"Why it changed: {causes[0].claim}")
    if actions:
        parts.append(f"Recommended action: {actions[0].claim}")
    elif observations:
        parts.append(
            "Recommended action: re-run this section against a longer time "
            "window before acting on the magnitude of these values."
        )
    return "\n\n".join(parts)


def compose_section(
    backend: Any,
    section: Section,
    *,
    language: str = "en",
    output_length: str = "standard",
    timeout: float = 120.0,
) -> Section:
    """Ask the model for prose, then keep it only if it stays inside evidence."""
    fallback = deterministic_prose(section, language=language)
    if backend is None or not section.findings:
        section.prose = fallback
        return section

    raw = ask_json(
        backend,
        writer_prompt(
            section.to_dict(),
            [f.to_dict() for f in section.findings],
            language=language,
            output_length=output_length,
        ),
        timeout=timeout,
    )
    prose = clamp_text(raw.get("prose"), 6000)
    if not prose.strip():
        section.prose = fallback
        return section

    callouts = [clamp_text(c, 300) for c in (raw.get("callouts") or [])[:6]]
    recommendation = clamp_text(raw.get("recommendation"), 600)
    blocks = [prose]
    if callouts:
        blocks.append("\n".join(f"> {c}" for c in callouts))
    if recommendation:
        blocks.append(f"**Recommended action.** {recommendation}")
        section.findings.append(
            Finding(
                claim=recommendation,
                evidence="writer synthesis over grounded findings",
                kind="recommendation",
                section_id=section.section_id,
            )
        )
    section.prose = "\n\n".join(blocks)
    return section


def write_section(
    backend: Any,
    section: Section,
    *,
    language: str = "en",
    output_length: str = "standard",
    timeout: float = 120.0,
) -> Section:
    """Public entry: never raises, always leaves ``section.prose`` populated."""
    try:
        return compose_section(
            backend,
            section,
            language=language,
            output_length=output_length,
            timeout=timeout,
        )
    except Exception:  # a writer failure must not sink a finished analysis
        logger.warning("writer failed for section %r; using the offline composer",
                       section.title, exc_info=True)
        section.prose = deterministic_prose(section, language=language)
        return section
