"""The research session: state machine, persistence, and the run pipeline.

A session is the unit the bridge, the UI, and the CLI all talk to. It owns:

* the state machine ``IDLE → PLANNING → APPROVAL_PENDING → IN_PROGRESS →
  PROOFREAD → COMPILING → COMPLETE | FAILED | CANCELLED`` with only legal
  transitions, persisted after every one of them so a crash resumes instead of
  restarting;
* the human-in-the-loop checkpoint (``approve`` / ``modify`` / ``cancel``),
  including a user-edited outline — the plan is a document the analyst can
  refine before anything expensive runs;
* the run pipeline: discover → plan → (approve) → per-section iterate →
  write → proofread → compile → publish;
* the hard guarantees: a global deadline, a cancellation flag checked at every
  step boundary, and a controlled ``FAILED`` transition for anything that
  escapes. A session cannot hang: it either finishes, fails, or is cancelled.

Storage is JSON files under ``data/research/`` (one per session plus an
index), written atomically. Nothing in this module imports pandas.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from dream.research.errors import (
    ResearchCancelled,
    ResearchError,
    ResearchSecurityError,
    ResearchTimeout,
)
from dream.research.schemas import (
    STATUSES,
    TRANSITIONS,
    Plan,
    ResearchConfig,
    Section,
    SessionRecord,
    clamp_text,
    is_id,
    new_id,
)

logger = logging.getLogger("dream.research.session")

__all__ = ["ResearchEngine", "ResearchSession", "RunContext", "SessionStore"]

_MAX_EVENTS = 2000


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #


class SessionStore:
    """Atomic, file-backed session persistence under ``data/research/``."""

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        self.root = Path(root or os.environ.get("DREAM_RESEARCH_DIR", "data/research"))
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, session_id: str) -> Path:
        if not is_id(session_id):
            raise ResearchError("session_id must be a 32-character hex id")
        return self.root / f"{session_id}.json"

    def save(self, record: SessionRecord) -> None:
        record.updated_at = time.time()
        payload = record.to_dict()
        with self._lock:
            path = self._path(record.session_id)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(path)

    def load(self, session_id: str) -> SessionRecord:
        path = self._path(session_id)
        if not path.exists():
            raise ResearchError(f"unknown research session: {session_id}")
        try:
            return SessionRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError) as exc:
            raise ResearchError(f"research session {session_id} is unreadable: {exc}") from None

    def exists(self, session_id: str) -> bool:
        return self._path(session_id).exists()

    def list(self) -> list[SessionRecord]:
        records: list[SessionRecord] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                records.append(
                    SessionRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
                )
            except (OSError, ValueError, KeyError):
                logger.warning("skipping unreadable session file %s", path.name)
        records.sort(key=lambda r: -r.created_at)
        return records

    def delete(self, session_id: str) -> bool:
        path = self._path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True


# --------------------------------------------------------------------------- #
# Run context
# --------------------------------------------------------------------------- #


class RunContext:
    """Everything a loop step needs, plus the deadlines that bound it."""

    def __init__(
        self,
        *,
        session: ResearchSession,
        runtime: Any,
        executor: Any,
        broker: Any,
        backend: Any,
        config: ResearchConfig,
        cancelled: threading.Event,
        emit: Callable[..., None],
    ) -> None:
        self.session = session
        self.runtime = runtime
        self.executor = executor
        self.broker = broker
        self.backend = backend
        self.config = config
        self.cancelled = cancelled
        self._emit = emit
        self.started = time.monotonic()
        self.profiles: dict[str, dict[str, Any]] = {}
        self.grounded_values: set[str] = set()

    @property
    def step_timeout(self) -> float:
        return self.config.step_timeout_seconds

    @property
    def section_budget(self) -> float:
        """Fair share of the global budget for one section, with a floor."""
        sections = max(1, len(self.session.record.plan.sections))
        return max(30.0, self.config.max_time_seconds / sections)

    def remaining(self) -> float:
        return max(1.0, self.config.max_time_seconds - (time.monotonic() - self.started))

    def out_of_time(self) -> bool:
        return (time.monotonic() - self.started) >= self.config.max_time_seconds

    def raise_if_cancelled(self) -> None:
        if self.cancelled.is_set():
            raise ResearchCancelled("the research session was cancelled")
        if self.out_of_time():
            raise ResearchTimeout(
                f"the session exceeded its {self.config.max_time_seconds:.0f}s budget"
            )

    def emit(self, event: str, **payload: Any) -> None:
        self._emit(event, **payload)


# --------------------------------------------------------------------------- #
# Session
# --------------------------------------------------------------------------- #


class ResearchSession:
    """One research project, from topic to published report."""

    def __init__(
        self,
        record: SessionRecord,
        *,
        store: SessionStore,
        runtime: Any = None,
        backend: Any = None,
        approver: Callable[[str, dict[str, Any]], bool] | None = None,
        tracker: Any = None,
        artifacts: Any = None,
        exporter: Any = None,
    ) -> None:
        self.record = record
        self.store = store
        self._runtime = runtime
        self.backend = backend
        self.approver = approver
        self.tracker = tracker
        self.artifacts = artifacts
        self.exporter = exporter
        self.cancelled = threading.Event()
        self._lock = threading.RLock()
        self._listeners: list[Callable[[dict[str, Any]], None]] = []

    # -- lazy runtime ------------------------------------------------------ #

    @property
    def runtime(self) -> Any:
        """The data-science runtime, built on first use (pandas stays lazy)."""
        if self._runtime is None:
            from dream.skills.data_science import DataScienceRuntime

            self._runtime = DataScienceRuntime()
        return self._runtime

    # -- state machine ----------------------------------------------------- #

    @property
    def status(self) -> str:
        return self.record.status

    def transition(self, target: str) -> None:
        """Move to ``target`` if the transition is legal, then persist."""
        with self._lock:
            current = self.record.status
            if target not in STATUSES:
                raise ResearchError(f"unknown status: {target}")
            if target not in TRANSITIONS.get(current, ()):  # closed transition table
                raise ResearchError(f"illegal transition {current} → {target}")
            self.record.status = target
            self.emit("status", status=target)
            self.store.save(self.record)

    # -- progress ----------------------------------------------------------- #

    def subscribe(self, listener: Callable[[dict[str, Any]], None]) -> None:
        self._listeners.append(listener)

    def emit(self, event: str, **payload: Any) -> None:
        """Record and fan out a progress event. Never raises into the loop."""
        from dream.security.secrets import redact_structure

        entry = {"event": str(event), "ts": time.time()}
        try:
            entry.update(redact_structure(payload))
        except Exception:
            entry.update({k: clamp_text(v, 400) for k, v in payload.items()})
        entry = {k: (clamp_text(v, 1000) if isinstance(v, str) else v)
                 for k, v in entry.items()}
        self.record.events.append(entry)
        if len(self.record.events) > _MAX_EVENTS:
            del self.record.events[: len(self.record.events) - _MAX_EVENTS]
        for listener in list(self._listeners):
            try:
                listener(entry)
            except Exception:
                logger.debug("progress listener failed", exc_info=True)

    def events_since(self, index: int = 0) -> list[dict[str, Any]]:
        return self.record.events[max(0, index) :]

    # -- discovery + planning ------------------------------------------------ #

    def discover(self) -> list[dict[str, Any]]:
        """Ingest and rank the workspace's sources (idempotent per session)."""
        from dream.research.discovery import discover_sources, safe_workspace

        if self.record.sources:
            return self.record.sources
        root = safe_workspace(self.record.workspace)
        self.emit("discovery.start", workspace=str(root))
        sources = discover_sources(self.runtime, root, self.record.topic)
        self.record.sources = sources
        self.emit(
            "discovery.end",
            found=len([s for s in sources if s.get("dataset_id")]),
            failed=len([s for s in sources if s.get("error")]),
        )
        self.store.save(self.record)
        return sources

    def plan(self, *, force: bool = False) -> Plan:
        """Produce (or re-produce) the study plan and pause for approval."""
        from dream.research.discovery import read_methodology_doc, safe_workspace
        from dream.research.planner import build_plan

        with self._lock:
            if self.record.status in ("COMPLETE", "CANCELLED", "FAILED"):
                raise ResearchError(f"session is {self.record.status}; create a new one")
            if self.record.plan.sections and not force:
                return self.record.plan
            if self.record.status != "PLANNING":
                self.transition("PLANNING")
        try:
            # A fresh planning pass re-arms the provider circuit breaker: a
            # provider that was wedged an hour ago deserves another chance.
            from dream.research.planner import reset_circuit

            reset_circuit()
            sources = self.discover()
            doc = read_methodology_doc(safe_workspace(self.record.workspace))
            self.emit("plan.start", sources=len(sources))
            plan = build_plan(
                self.backend,
                self.record.topic,
                sources,
                language=self.record.config.language,
                max_sections=self.record.config.max_sections,
                methodology_doc=doc,
                timeout=self.record.config.step_timeout_seconds,
            )
        except ResearchError as exc:
            self.fail(str(exc))
            raise
        plan.revision = self.record.plan.revision + 1 if self.record.plan.sections else 1
        self.record.plan = plan
        self.record.cost_estimate = self.estimate_cost()
        self.emit(
            "plan.ready",
            sections=[s.title for s in plan.sections],
            revision=plan.revision,
            source=plan.source,
        )
        self.transition("APPROVAL_PENDING")
        return plan

    def estimate_cost(self) -> dict[str, Any]:
        """A pre-run cost/effort estimate, so nothing expensive starts blind."""
        sections = max(1, len(self.record.plan.sections))
        iterations = sections * self.record.config.max_iterations
        # 4 model steps per iteration (gap, tool, code, reflect) + writer +
        # proofreader; ~900 tokens per step is Dream's observed average.
        model_calls = iterations * 4 + sections + 1
        return {
            "sections": sections,
            "max_iterations": self.record.config.max_iterations,
            "estimated_model_calls": model_calls,
            "estimated_tokens": model_calls * 900,
            "estimated_sandbox_runs": iterations,
            "max_wall_clock_seconds": self.record.config.max_time_seconds,
            "backend": type(self.backend).__name__ if self.backend else "offline",
        }

    # -- approval checkpoint --------------------------------------------------- #

    def approve(self) -> Plan:
        """The human checkpoint: unblock execution."""
        with self._lock:
            if self.record.status != "APPROVAL_PENDING":
                raise ResearchError(
                    f"nothing to approve: the session is {self.record.status}"
                )
            self.record.plan.approved = True
            self.emit("plan.approved", revision=self.record.plan.revision)
            self.store.save(self.record)
            return self.record.plan

    def modify(self, changes: dict[str, Any]) -> Plan:
        """Refine the plan by hand (Prophecy-style), or ask for a re-plan.

        ``changes`` may carry ``objective``, ``questions``, ``hypotheses``,
        ``methodology``, and ``sections`` (a user-edited outline). Passing
        ``{"replan": true}`` discards the outline and asks the planner again.
        """
        if not isinstance(changes, dict) or not changes:
            raise ResearchError("changes must be a non-empty object")
        with self._lock:
            if self.record.status not in ("APPROVAL_PENDING", "PLANNING"):
                raise ResearchError(f"the plan is not editable while {self.record.status}")
            if changes.get("replan"):
                self.record.plan.approved = False
                self.transition("PLANNING")
                return self.plan(force=True)

            plan = self.record.plan
            if "objective" in changes:
                plan.objective = clamp_text(changes["objective"], 1000)
            if "methodology" in changes:
                plan.methodology = clamp_text(changes["methodology"], 2000)
            for key in ("questions", "hypotheses"):
                if key in changes:
                    values = changes[key]
                    if not isinstance(values, list):
                        raise ResearchError(f"{key} must be a list")
                    setattr(plan, key, [clamp_text(v, 300) for v in values[:12]])
            if "sections" in changes:
                raw = changes["sections"]
                if not isinstance(raw, list) or not raw:
                    raise ResearchError("sections must be a non-empty list")
                if len(raw) > self.record.config.max_sections:
                    raise ResearchError(
                        f"at most {self.record.config.max_sections} sections are allowed"
                    )
                sections: list[Section] = []
                for entry in raw:
                    if not isinstance(entry, dict):
                        raise ResearchError("each section must be an object")
                    title = clamp_text(entry.get("title"), 160)
                    if not title:
                        raise ResearchError("each section needs a title")
                    sections.append(
                        Section(
                            section_id=str(entry.get("section_id") or new_id()),
                            title=title,
                            thesis=clamp_text(entry.get("thesis"), 600),
                            questions=[
                                clamp_text(q, 300) for q in (entry.get("questions") or [])[:12]
                            ],
                        )
                    )
                plan.sections = sections
            plan.revision += 1
            plan.approved = False
            plan.source = "user"
            self.record.cost_estimate = self.estimate_cost()
            self.emit("plan.modified", revision=plan.revision)
            self.store.save(self.record)
            return plan

    def cancel(self) -> None:
        """Cooperative cancellation: the next step boundary stops the run."""
        self.cancelled.set()
        with self._lock:
            self.emit("cancelled")
            if self.record.status in ("COMPLETE", "FAILED", "CANCELLED"):
                self.store.save(self.record)
                return
            self.record.status = "CANCELLED"
            self.store.save(self.record)

    def fail(self, reason: str) -> None:
        with self._lock:
            self.record.error = clamp_text(reason, 1000)
            self.emit("failed", reason=self.record.error)
            if self.record.status not in ("COMPLETE", "CANCELLED", "FAILED"):
                self.record.status = "FAILED"
            self.store.save(self.record)

    # -- execution ----------------------------------------------------------- #

    def start(self) -> SessionRecord:
        """Run the approved plan to a compiled report.

        Fail-closed: any escaping exception lands the session in ``FAILED``
        with a reason, never in a hung ``IN_PROGRESS``.
        """
        from dream.research.executor import CodeActExecutor
        from dream.research.iterate import ToolBroker

        with self._lock:
            if self.record.status in ("COMPLETE", "FAILED", "CANCELLED"):
                raise ResearchError(
                    f"the session is {self.record.status}; create a new one to re-run"
                )
            if self.record.status == "IN_PROGRESS":
                raise ResearchError("the session is already running")
            if not self.record.plan.sections:
                raise ResearchError("plan the session before starting it")
            if not self.record.plan.approved and not self.record.config.autonomous:
                raise ResearchError(
                    "the plan must be approved before an interactive run starts"
                )
            self.cancelled.clear()
            self.transition("IN_PROGRESS")

        executor = CodeActExecutor(
            self.runtime,
            default_timeout=self.record.config.step_timeout_seconds,
        )
        broker = ToolBroker(
            self.runtime,
            autonomous=self.record.config.autonomous,
            approver=self.approver,
            allow_network=self.record.config.allow_network,
        )
        ctx = RunContext(
            session=self,
            runtime=self.runtime,
            executor=executor,
            broker=broker,
            backend=self.backend,
            config=self.record.config,
            cancelled=self.cancelled,
            emit=self.emit,
        )
        self.emit(
            "run.start",
            sandbox="docker" if CodeActExecutor.docker_available() else "local-subprocess",
            autonomous=self.record.config.autonomous,
        )
        try:
            self._run_sections(ctx)
            self._prepare_data(ctx)
            self._write_and_proofread(ctx)
            self._compile(ctx, executor)
        except ResearchCancelled:
            self.cancel()
            return self.record
        except (ResearchTimeout, ResearchSecurityError) as exc:
            self.fail(str(exc))
            return self.record
        except Exception as exc:  # fail-closed on anything unexpected
            logger.exception("research session %s failed", self.record.session_id)
            self.fail(f"{type(exc).__name__}: {clamp_text(exc, 500)}")
            return self.record
        return self.record

    def _prepare_data(self, ctx: RunContext) -> None:
        """Execution-grounded cleaning, recorded as methodology, not as prose."""
        if self.record.config.autonomous:
            return  # cleaning writes cleaned.csv: outside the degraded grant set
        from dream.research.prep import prepare_dataset

        primary = next((s for s in self.record.sources if s.get("dataset_id")), None)
        if primary is None:
            return
        ctx.raise_if_cancelled()
        try:
            trace = prepare_dataset(
                self.runtime, primary["dataset_id"], emit=lambda e, **p: self.emit(e, **p)
            )
        except Exception as exc:
            self.emit("prep.failed", reason=clamp_text(exc, 300))
            return
        if trace.get("rounds"):
            self.record.plan.methodology += (
                f"\n\nData preparation applied {len(trace['rounds'])} execution-grounded "
                f"round(s): "
                + "; ".join(
                    f"round {r['round']} ({', '.join(op['op'] for op in r['operations'])}) "
                    f"{r['rows_before']}→{r['rows_after']} rows"
                    for r in trace["rounds"]
                )
                + "."
            )
        for limitation in trace.get("limitations", []):
            self.emit("prep.limitation", detail=clamp_text(limitation, 300))

    def _run_sections(self, ctx: RunContext) -> None:
        from dream.research.iterate import (
            attach_charts,
            collect_analyses,
            enrich_from_profile,
            run_section,
        )

        usable = [s for s in self.record.sources if s.get("dataset_id")]
        if not usable:
            raise ResearchError("no usable data sources; nothing to research")

        for index, section in enumerate(self.record.plan.sections):
            ctx.raise_if_cancelled()
            if section.status == "DONE":
                continue  # resume: never redo a finished section
            source = usable[min(index, len(usable) - 1)]
            dataset_id = source["dataset_id"]
            self.emit("section.start", section=section.title, dataset_id=dataset_id)
            try:
                enrich_from_profile(ctx, section, dataset_id)
                collect_analyses(ctx, section, dataset_id)
                run_section(ctx, section, source)
                attach_charts(ctx, section, dataset_id)
            except ResearchCancelled:
                raise
            except ResearchTimeout as exc:
                section.status = "SKIPPED"
                section.rationale = clamp_text(exc, 300)
                self.emit("section.timeout", section=section.title)
            except Exception as exc:  # one bad section must not sink the report
                logger.warning("section %r failed: %s", section.title, exc)
                section.status = "FAILED"
                section.rationale = f"{type(exc).__name__}: {clamp_text(exc, 300)}"
                self.emit("section.failed", section=section.title, reason=section.rationale)
            self.emit(
                "section.end",
                section=section.title,
                status=section.status,
                findings=len(section.findings),
            )
            self.store.save(self.record)

    def _write_and_proofread(self, ctx: RunContext) -> None:
        from dream.research.proofread import audit, enforce
        from dream.research.writer import write_section

        for section in self.record.plan.sections:
            ctx.raise_if_cancelled()
            write_section(
                self.backend,
                section,
                language=self.record.config.language,
                output_length=self.record.config.output_length,
                timeout=self.record.config.step_timeout_seconds,
            )
            self.emit("section.written", section=section.title, chars=len(section.prose))

        self.transition("PROOFREAD")
        # Enforce grounding per section *before* compiling, so a hallucinated
        # figure never reaches the Markdown at all.
        redactions = 0
        for section in self.record.plan.sections:
            cleaned, count = enforce(section.prose, ctx.grounded_values)
            section.prose = cleaned
            redactions += count
        pre = audit(
            "\n".join(s.prose for s in self.record.plan.sections), ctx.grounded_values
        )
        self.record.report.proofread = {
            "redactions": redactions,
            "pre_compile": pre,
        }
        self._grounded = ctx.grounded_values
        self.emit("proofread.done", redactions=redactions, ok=pre["ok"])
        self.store.save(self.record)

    def _compile(self, ctx: RunContext, executor: Any) -> None:
        from dream.research.proofread import proofread
        from dream.research.report import REFERENCES, compile_report

        self.transition("COMPILING")
        result = compile_report(
            self.record,
            executor,
            tracker=self.tracker,
            artifacts=self.artifacts,
            exporter=self.exporter,
            ledger=ctx.grounded_values,
        )
        reference_count = len(REFERENCES) + len(
            [s for s in self.record.sources if s.get("dataset_id")]
        )
        final = proofread(
            self.backend,
            result["markdown"],
            ctx.grounded_values,
            language=self.record.config.language,
            reference_count=reference_count,
            timeout=self.record.config.step_timeout_seconds,
        )
        self.record.report.markdown_path = result["markdown_path"]
        self.record.report.pdf_path = result["pdf_path"]
        self.record.report.bundle_path = result["bundle_path"]
        self.record.report.record_ids = result["record_ids"]
        self.record.report.pages = result["pages"]
        self.record.report.proofread = {
            **self.record.report.proofread,
            "final": final,
            "grounded_values": len(ctx.grounded_values),
        }
        self.emit(
            "report.compiled",
            markdown=result["markdown_path"],
            pdf=result["pdf_path"],
            pages=result["pages"],
            ok=final["ok"],
        )
        self.transition("COMPLETE")

    # -- publish -------------------------------------------------------------- #

    def publish(self) -> dict[str, Any]:
        """The explicit deploy action: mark a reviewed report as published."""
        if self.record.status != "COMPLETE":
            raise ResearchError("only a COMPLETE session can be published")
        self.record.published = True
        self.emit("published")
        self.store.save(self.record)
        return self.record.report.to_dict()

    def to_dict(self) -> dict[str, Any]:
        return self.record.to_dict()


# --------------------------------------------------------------------------- #
# Engine facade
# --------------------------------------------------------------------------- #


class ResearchEngine:
    """Create, look up, and run research sessions.

    The bridge holds one of these. It is deliberately thin: session identity
    and persistence live in :class:`SessionStore`, behaviour in
    :class:`ResearchSession`.
    """

    def __init__(
        self,
        *,
        store: SessionStore | None = None,
        runtime: Any = None,
        backend: Any = None,
        approver: Callable[[str, dict[str, Any]], bool] | None = None,
        tracker: Any = None,
        artifacts: Any = None,
        exporter: Any = None,
    ) -> None:
        self.store = store or SessionStore()
        self.runtime = runtime
        self.backend = backend
        self.approver = approver
        self.tracker = tracker
        self.artifacts = artifacts
        self.exporter = exporter
        self._live: dict[str, ResearchSession] = {}
        self._lock = threading.RLock()

    # -- lifecycle ----------------------------------------------------------- #

    def create(
        self,
        topic: str,
        workspace: str,
        *,
        config: dict[str, Any] | ResearchConfig | None = None,
    ) -> ResearchSession:
        from dream.research.discovery import safe_workspace
        from dream.security.injection import guard_untrusted

        if not isinstance(topic, str) or not topic.strip():
            raise ResearchError("topic must be a non-empty string")
        if len(topic) > 2000:
            raise ResearchError("topic must be at most 2000 characters")
        # The topic is user text but it reaches a model: it goes through the
        # same injection gate as any other untrusted content.
        safe_topic = guard_untrusted(topic.strip(), source="research.topic")
        root = safe_workspace(workspace)
        resolved = (
            config if isinstance(config, ResearchConfig) else ResearchConfig.from_dict(config)
        )
        record = SessionRecord(
            session_id=new_id(),
            topic=safe_topic,
            workspace=str(root),
            config=resolved,
        )
        session = self._wrap(record)
        self.store.save(record)
        session.emit("created", topic=clamp_text(safe_topic, 300), workspace=str(root))
        self.store.save(record)
        return session

    def _wrap(self, record: SessionRecord) -> ResearchSession:
        session = ResearchSession(
            record,
            store=self.store,
            runtime=self.runtime,
            backend=self.backend,
            approver=self.approver,
            tracker=self.tracker,
            artifacts=self.artifacts,
            exporter=self.exporter,
        )
        with self._lock:
            self._live[record.session_id] = session
        return session

    def get(self, session_id: str) -> ResearchSession:
        with self._lock:
            live = self._live.get(session_id)
        if live is not None:
            return live
        return self._wrap(self.store.load(session_id))

    def list(self) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for record in self.store.list():
            summaries.append(
                {
                    "session_id": record.session_id,
                    "topic": record.topic,
                    "status": record.status,
                    "sections": len(record.plan.sections),
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                    "published": record.published,
                    "report": record.report.markdown_path,
                }
            )
        return summaries

    def delete(self, session_id: str) -> bool:
        with self._lock:
            self._live.pop(session_id, None)
        return self.store.delete(session_id)

    # -- one-shot --------------------------------------------------------------- #

    def run(
        self,
        topic: str,
        workspace: str,
        *,
        config: dict[str, Any] | ResearchConfig | None = None,
        auto_approve: bool = True,
    ) -> ResearchSession:
        """Plan → (approve) → execute → report, in one call.

        ``auto_approve=False`` stops at the checkpoint and returns the session
        in ``APPROVAL_PENDING`` — the interactive path. Autonomous sessions
        (``config['autonomous']``) skip the checkpoint by design but run with
        the degraded, read-only grant set.
        """
        session = self.create(topic, workspace, config=config)
        session.plan()
        if not auto_approve and not session.record.config.autonomous:
            return session
        if not session.record.config.autonomous:
            session.approve()
        session.start()
        return session

    def stream(self, session_id: str) -> Iterator[dict[str, Any]]:
        """Replay a session's recorded progress events (UI live trace)."""
        session = self.get(session_id)
        yield from session.record.events
