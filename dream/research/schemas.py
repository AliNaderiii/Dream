"""Structured data model + tolerant JSON parsing for the research engine.

Two responsibilities live here:

* the dataclasses that make up a research session (plan, sections,
  iterations, observations, findings, report) — all JSON round-trippable so a
  session can be persisted and resumed;
* :func:`parse_json_object`, the tolerant parser used for every structured
  model reply (fenced blocks, prose preamble, trailing commas, single
  quotes), plus small validators that keep model output inside hard bounds.

Nothing here imports pandas, matplotlib, or a backend: the schema layer is
importable in any environment.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from dream.research.errors import ResearchError

__all__ = [
    "MAX_SECTIONS",
    "STATUSES",
    "Finding",
    "Iteration",
    "Observation",
    "Plan",
    "ReportRef",
    "ResearchConfig",
    "Section",
    "SessionRecord",
    "ToolCallRecord",
    "clamp_text",
    "new_id",
    "parse_json_object",
]

#: The session state machine (see ``docs/architecture/data-science.md``).
STATUSES = (
    "IDLE",
    "PLANNING",
    "APPROVAL_PENDING",
    "IN_PROGRESS",
    "PROOFREAD",
    "COMPILING",
    "COMPLETE",
    "FAILED",
    "CANCELLED",
)

#: Legal transitions. Anything else is a programming error and is refused.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "IDLE": ("PLANNING", "CANCELLED", "FAILED"),
    "PLANNING": ("APPROVAL_PENDING", "PLANNING", "FAILED", "CANCELLED"),
    "APPROVAL_PENDING": ("PLANNING", "IN_PROGRESS", "CANCELLED", "FAILED"),
    "IN_PROGRESS": ("IN_PROGRESS", "PROOFREAD", "FAILED", "CANCELLED"),
    "PROOFREAD": ("COMPILING", "FAILED", "CANCELLED"),
    "COMPILING": ("COMPLETE", "FAILED", "CANCELLED"),
    "COMPLETE": (),
    "FAILED": (),
    "CANCELLED": (),
}

MAX_SECTIONS = 12
MAX_QUESTIONS = 12
MAX_TEXT = 4000
_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def new_id() -> str:
    """A 32-hex identifier, matching the dataset-registry id shape."""
    return uuid.uuid4().hex


def is_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_ID_RE.match(value))


def clamp_text(value: Any, limit: int = MAX_TEXT, *, what: str = "text") -> str:
    """Coerce to a bounded, single-object string (never None, never a dict)."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(item) for item in value)
    if not isinstance(value, str):
        value = str(value)
    value = value.replace("\x00", "")
    if len(value) > limit:
        value = value[:limit].rstrip() + " …"
    del what
    return value


# --------------------------------------------------------------------------- #
# Tolerant JSON parsing for model output
# --------------------------------------------------------------------------- #

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def _balanced_object(text: str) -> str | None:
    """Return the first balanced ``{...}`` span, ignoring braces in strings."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _repair(candidate: str) -> str:
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)  # trailing commas
    candidate = candidate.replace("\u200c", "").replace("\ufeff", "")
    return candidate


def parse_json_object(text: Any) -> dict[str, Any]:
    """Parse a JSON object out of a model reply. Never raises on junk input.

    Tries, in order: the raw text, a fenced code block, the first balanced
    brace span, and a light repair pass (trailing commas, zero-width joiners).
    Returns ``{}`` when nothing parses — callers degrade to a deterministic
    fallback rather than hanging on a retry loop.
    """
    if isinstance(text, dict):
        return dict(text)
    if not isinstance(text, str) or not text.strip():
        return {}
    candidates: list[str] = [text.strip()]
    fence = _FENCE_RE.search(text)
    if fence:
        candidates.append(fence.group(1).strip())
    balanced = _balanced_object(text)
    if balanced:
        candidates.append(balanced)
    for candidate in list(candidates):
        candidates.append(_repair(candidate))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            return {"items": parsed}
    return {}


# --------------------------------------------------------------------------- #
# Session dataclasses
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class ResearchConfig:
    """Bounded knobs for one research run. Every value is hard-clamped."""

    max_iterations: int = 3
    max_time_seconds: float = 900.0
    step_timeout_seconds: float = 120.0
    max_retries: int = 2
    max_sections: int = 6
    language: str = "en"
    autonomous: bool = False
    allow_network: bool = False
    max_pages: int = 20
    output_length: str = "standard"

    def __post_init__(self) -> None:
        self.max_iterations = _clamp_int(self.max_iterations, 1, 10, "max_iterations")
        self.max_time_seconds = _clamp_float(self.max_time_seconds, 5.0, 24 * 3600.0)
        self.step_timeout_seconds = _clamp_float(self.step_timeout_seconds, 1.0, 3600.0)
        self.max_retries = _clamp_int(self.max_retries, 0, 5, "max_retries")
        self.max_sections = _clamp_int(self.max_sections, 1, MAX_SECTIONS, "max_sections")
        if self.language not in ("en", "fa"):
            raise ResearchError("language must be 'en' or 'fa'")
        self.autonomous = bool(self.autonomous)
        self.allow_network = bool(self.allow_network)
        self.max_pages = _clamp_int(self.max_pages, 1, 200, "max_pages")
        if self.output_length not in ("brief", "standard", "detailed"):
            raise ResearchError("output_length must be brief|standard|detailed")

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_iterations": self.max_iterations,
            "max_time_seconds": self.max_time_seconds,
            "step_timeout_seconds": self.step_timeout_seconds,
            "max_retries": self.max_retries,
            "max_sections": self.max_sections,
            "language": self.language,
            "autonomous": self.autonomous,
            "allow_network": self.allow_network,
            "max_pages": self.max_pages,
            "output_length": self.output_length,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> ResearchConfig:
        raw = raw if isinstance(raw, dict) else {}
        known = {
            key: raw[key]
            for key in (
                "max_iterations",
                "max_time_seconds",
                "step_timeout_seconds",
                "max_retries",
                "max_sections",
                "language",
                "autonomous",
                "allow_network",
                "max_pages",
                "output_length",
            )
            if key in raw
        }
        return cls(**known)


def _clamp_int(value: Any, low: int, high: int, what: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ResearchError(f"{what} must be an integer") from None
    return max(low, min(high, number))


def _clamp_float(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ResearchError("expected a number") from None
    return max(low, min(high, number))


@dataclass(slots=True)
class ToolCallRecord:
    """One tool invocation inside an iteration."""

    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    error: str = ""
    summary: str = ""
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "arguments": self.arguments,
            "ok": self.ok,
            "error": self.error,
            "summary": self.summary,
            "elapsed_seconds": self.elapsed_seconds,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ToolCallRecord:
        return cls(
            tool=str(raw.get("tool", "")),
            arguments=dict(raw.get("arguments") or {}),
            ok=bool(raw.get("ok", True)),
            error=str(raw.get("error", "")),
            summary=str(raw.get("summary", "")),
            elapsed_seconds=float(raw.get("elapsed_seconds", 0.0)),
        )


@dataclass(slots=True)
class Observation:
    """The digested runtime output of one iteration — the grounding unit."""

    stdout: str = ""
    stderr: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    facts: list[str] = field(default_factory=list)
    error: str = ""
    converged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "result": self.result,
            "facts": self.facts,
            "error": self.error,
            "converged": self.converged,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Observation:
        return cls(
            stdout=str(raw.get("stdout", "")),
            stderr=str(raw.get("stderr", "")),
            result=dict(raw.get("result") or {}),
            facts=[str(f) for f in raw.get("facts") or []],
            error=str(raw.get("error", "")),
            converged=bool(raw.get("converged", False)),
        )


@dataclass(slots=True)
class Iteration:
    """One turn of the KnowledgeGap → ToolSelector → CodeAct → Observe loop."""

    index: int
    knowledge_gap: str = ""
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    code: str = ""
    observation: Observation = field(default_factory=Observation)
    reflection: str = ""
    retries: int = 0
    started_at: float = field(default_factory=time.time)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "knowledge_gap": self.knowledge_gap,
            "tool_calls": [c.to_dict() for c in self.tool_calls],
            "code": self.code,
            "observation": self.observation.to_dict(),
            "reflection": self.reflection,
            "retries": self.retries,
            "started_at": self.started_at,
            "elapsed_seconds": self.elapsed_seconds,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Iteration:
        return cls(
            index=int(raw.get("index", 0)),
            knowledge_gap=str(raw.get("knowledge_gap", "")),
            tool_calls=[ToolCallRecord.from_dict(c) for c in raw.get("tool_calls") or []],
            code=str(raw.get("code", "")),
            observation=Observation.from_dict(raw.get("observation") or {}),
            reflection=str(raw.get("reflection", "")),
            retries=int(raw.get("retries", 0)),
            started_at=float(raw.get("started_at", 0.0)),
            elapsed_seconds=float(raw.get("elapsed_seconds", 0.0)),
        )


@dataclass(slots=True)
class Finding:
    """A grounded statement: a claim plus the evidence that produced it."""

    claim: str
    evidence: str = ""
    metric: str = ""
    value: Any = None
    kind: str = "observation"  # observation | anomaly | root_cause | recommendation
    section_id: str = ""
    iteration: int = 0
    grounded: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "evidence": self.evidence,
            "metric": self.metric,
            "value": self.value,
            "kind": self.kind,
            "section_id": self.section_id,
            "iteration": self.iteration,
            "grounded": self.grounded,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Finding:
        return cls(
            claim=str(raw.get("claim", "")),
            evidence=str(raw.get("evidence", "")),
            metric=str(raw.get("metric", "")),
            value=raw.get("value"),
            kind=str(raw.get("kind", "observation")),
            section_id=str(raw.get("section_id", "")),
            iteration=int(raw.get("iteration", 0)),
            grounded=bool(raw.get("grounded", True)),
        )


@dataclass(slots=True)
class Section:
    """One report section: a thesis, its iterations, findings, and prose."""

    section_id: str
    title: str
    thesis: str = ""
    questions: list[str] = field(default_factory=list)
    status: str = "PENDING"  # PENDING | RUNNING | DONE | SKIPPED | FAILED
    iterations: list[Iteration] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    charts: list[str] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    prose: str = ""
    rationale: str = ""
    editable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "thesis": self.thesis,
            "questions": self.questions,
            "status": self.status,
            "iterations": [i.to_dict() for i in self.iterations],
            "findings": [f.to_dict() for f in self.findings],
            "charts": self.charts,
            "tables": self.tables,
            "prose": self.prose,
            "rationale": self.rationale,
            "editable": self.editable,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Section:
        return cls(
            section_id=str(raw.get("section_id") or new_id()),
            title=str(raw.get("title", "")),
            thesis=str(raw.get("thesis", "")),
            questions=[str(q) for q in raw.get("questions") or []],
            status=str(raw.get("status", "PENDING")),
            iterations=[Iteration.from_dict(i) for i in raw.get("iterations") or []],
            findings=[Finding.from_dict(f) for f in raw.get("findings") or []],
            charts=[str(c) for c in raw.get("charts") or []],
            tables=list(raw.get("tables") or []),
            prose=str(raw.get("prose", "")),
            rationale=str(raw.get("rationale", "")),
            editable=bool(raw.get("editable", True)),
        )


@dataclass(slots=True)
class Plan:
    """The study design produced by the planner and shown for approval."""

    objective: str = ""
    questions: list[str] = field(default_factory=list)
    hypotheses: list[str] = field(default_factory=list)
    methodology: str = ""
    sections: list[Section] = field(default_factory=list)
    datasets: list[str] = field(default_factory=list)
    revision: int = 0
    approved: bool = False
    source: str = "model"  # model | fallback | user

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "questions": self.questions,
            "hypotheses": self.hypotheses,
            "methodology": self.methodology,
            "sections": [s.to_dict() for s in self.sections],
            "datasets": self.datasets,
            "revision": self.revision,
            "approved": self.approved,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Plan:
        raw = raw if isinstance(raw, dict) else {}
        return cls(
            objective=str(raw.get("objective", "")),
            questions=[str(q) for q in raw.get("questions") or []],
            hypotheses=[str(h) for h in raw.get("hypotheses") or []],
            methodology=str(raw.get("methodology", "")),
            sections=[Section.from_dict(s) for s in raw.get("sections") or []],
            datasets=[str(d) for d in raw.get("datasets") or []],
            revision=int(raw.get("revision", 0)),
            approved=bool(raw.get("approved", False)),
            source=str(raw.get("source", "model")),
        )


@dataclass(slots=True)
class ReportRef:
    """Where the compiled artifacts landed, plus their provenance links."""

    markdown_path: str = ""
    pdf_path: str = ""
    bundle_path: str = ""
    record_ids: list[str] = field(default_factory=list)
    pages: int = 0
    proofread: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "markdown_path": self.markdown_path,
            "pdf_path": self.pdf_path,
            "bundle_path": self.bundle_path,
            "record_ids": self.record_ids,
            "pages": self.pages,
            "proofread": self.proofread,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ReportRef:
        raw = raw if isinstance(raw, dict) else {}
        return cls(
            markdown_path=str(raw.get("markdown_path", "")),
            pdf_path=str(raw.get("pdf_path", "")),
            bundle_path=str(raw.get("bundle_path", "")),
            record_ids=[str(r) for r in raw.get("record_ids") or []],
            pages=int(raw.get("pages", 0)),
            proofread=dict(raw.get("proofread") or {}),
        )


@dataclass(slots=True)
class SessionRecord:
    """The persisted shape of a research session."""

    session_id: str
    topic: str
    workspace: str = ""
    status: str = "IDLE"
    config: ResearchConfig = field(default_factory=ResearchConfig)
    plan: Plan = field(default_factory=Plan)
    sources: list[dict[str, Any]] = field(default_factory=list)
    report: ReportRef = field(default_factory=ReportRef)
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cost_estimate: dict[str, Any] = field(default_factory=dict)
    published: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "topic": self.topic,
            "workspace": self.workspace,
            "status": self.status,
            "config": self.config.to_dict(),
            "plan": self.plan.to_dict(),
            "sources": self.sources,
            "report": self.report.to_dict(),
            "events": self.events[-500:],
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "cost_estimate": self.cost_estimate,
            "published": self.published,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SessionRecord:
        return cls(
            session_id=str(raw["session_id"]),
            topic=str(raw.get("topic", "")),
            workspace=str(raw.get("workspace", "")),
            status=str(raw.get("status", "IDLE")),
            config=ResearchConfig.from_dict(raw.get("config")),
            plan=Plan.from_dict(raw.get("plan")),
            sources=list(raw.get("sources") or []),
            report=ReportRef.from_dict(raw.get("report")),
            events=list(raw.get("events") or []),
            error=str(raw.get("error", "")),
            created_at=float(raw.get("created_at", 0.0)),
            updated_at=float(raw.get("updated_at", 0.0)),
            cost_estimate=dict(raw.get("cost_estimate") or {}),
            published=bool(raw.get("published", False)),
        )
