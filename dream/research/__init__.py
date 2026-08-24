"""Dream's autonomous data-science research engine.

A self-directed analyst: it plans an open-ended study, discovers and profiles
the data in a workspace, iterates *plan → code → execute → observe →
self-correct* with real runtime feedback, and compiles a grounded, reproducible
report (Markdown + PDF) with provenance behind every number.

Quick start::

    from dream.research import ResearchEngine

    engine = ResearchEngine()                 # offline-capable
    session = engine.run("Why did revenue dip in Q3?", "data/space")
    print(session.record.report.markdown_path)

The engine is deliberately layered so each piece is testable on its own:

============================  ======================================
:mod:`~dream.research.session`   state machine, persistence, pipeline
:mod:`~dream.research.planner`   topic + sources → study plan
:mod:`~dream.research.iterate`   the per-section research loop
:mod:`~dream.research.discovery` multi-source discovery + relevance
:mod:`~dream.research.prep`      execution-grounded data preparation
:mod:`~dream.research.analyze`   analyses, anomalies, tables, charts
:mod:`~dream.research.executor`  AST-gated, sandboxed CodeAct
:mod:`~dream.research.writer`    findings → analyst prose
:mod:`~dream.research.proofread` the grounding guard
:mod:`~dream.research.report`    Markdown + PDF + provenance
============================  ======================================

Nothing here imports pandas or matplotlib at module scope; the heavy stack is
reached only through :mod:`dream.skills.data_science`, inside the sandbox.
"""

from __future__ import annotations

from dream.research.errors import (
    ResearchCancelled,
    ResearchError,
    ResearchSecurityError,
    ResearchTimeout,
)
from dream.research.schemas import (
    Finding,
    Iteration,
    Observation,
    Plan,
    ReportRef,
    ResearchConfig,
    Section,
    SessionRecord,
)
from dream.research.session import (
    ResearchEngine,
    ResearchSession,
    RunContext,
    SessionStore,
)

__all__ = [
    "Finding",
    "Iteration",
    "Observation",
    "Plan",
    "ReportRef",
    "ResearchCancelled",
    "ResearchConfig",
    "ResearchEngine",
    "ResearchError",
    "ResearchSecurityError",
    "ResearchSession",
    "ResearchTimeout",
    "ReportRef",
    "RunContext",
    "Section",
    "SessionRecord",
    "SessionStore",
]
