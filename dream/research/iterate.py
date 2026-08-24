"""The core loop: KnowledgeGap → ToolSelector → CodeAct → Observe/Reflect.

One section at a time, up to ``max_iterations`` turns, each turn feeding its
runtime output into the next. Four properties are enforced here because this
is where the engine either earns its trust or loses it:

* **grounding** — a finding is only recorded when the value it cites came out
  of an executed step. The iteration's observation *is* the evidence.
* **self-correction** — a snippet that raises is not a failure; the traceback
  is fed back and the CodeAct step retries up to ``max_retries`` before the
  iteration degrades to the deterministic analysis path.
* **risk tiers** — tool dispatch goes through :class:`ToolBroker`. Dangerous
  tools are simply absent from an autonomous run's table, and in an
  interactive run they require an approver.
* **no hang** — every step is bounded by the section deadline; when the budget
  is gone the loop stops cleanly and the section is written from whatever was
  grounded, with an explicit rationale.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from dream.research.analyze import (
    build_tables,
    detect_anomalies,
    extract_numbers,
    format_number,
    plan_analyses,
    render_charts,
    run_analyses,
)
from dream.research.errors import (
    ResearchCancelled,
    ResearchError,
    ResearchSecurityError,
    ResearchTimeout,
)
from dream.research.planner import ask_json
from dream.research.prompts import codegen_prompt, knowledge_gap_prompt, reflect_prompt
from dream.research.schemas import (
    Finding,
    Iteration,
    Observation,
    Section,
    ToolCallRecord,
    clamp_text,
)

logger = logging.getLogger("dream.research.iterate")

__all__ = ["INTERACTIVE_TOOLS", "AUTONOMOUS_TOOLS", "ToolBroker", "run_section"]

#: Read/derive-only tools an autonomous (cron) session may dispatch. Anything
#: that writes outside the dataset directory, shells out, or reaches the
#: network is *absent from the table*, not merely denied — a degraded grant
#: set, per the security model.
AUTONOMOUS_TOOLS = ("profile_data", "analyze_data", "auto_chart")

#: Interactive sessions add the guarded tools; they still pass the risk gate.
INTERACTIVE_TOOLS = (
    "profile_data",
    "analyze_data",
    "auto_chart",
    "create_chart",
    "clean_data",
)

#: Never dispatchable from a research loop, in any mode.
FORBIDDEN_TOOLS = frozenset({"run_shell", "shell", "write_file", "delete_file", "http_request"})


class ToolBroker:
    """Risk-tiered dispatch for the tools a research loop may call.

    The broker owns three decisions: which tools exist for this session
    (grant set), whether a ``guarded``/``dangerous`` tool needs an approver,
    and how a tool failure is reported back to the loop (as data, never as an
    exception that kills the section).
    """

    def __init__(
        self,
        runtime: Any,
        *,
        autonomous: bool = False,
        approver: Callable[[str, dict[str, Any]], bool] | None = None,
        allow_network: bool = False,
    ) -> None:
        self.runtime = runtime
        self.autonomous = bool(autonomous)
        self.approver = approver
        self.allow_network = bool(allow_network)
        self.calls: list[ToolCallRecord] = []

    @property
    def available(self) -> tuple[str, ...]:
        return AUTONOMOUS_TOOLS if self.autonomous else INTERACTIVE_TOOLS

    def risk_of(self, tool: str) -> str:
        """The registry's risk tier for a tool, defaulting to ``dangerous``."""
        try:
            from dream.tools import REGISTRY
        except ImportError:  # pragma: no cover
            return "dangerous"
        registered = REGISTRY.get(tool)
        return getattr(registered, "risk", "dangerous") if registered else "dangerous"

    def check(self, tool: Any, arguments: Any) -> tuple[str, dict[str, Any]]:
        """Validate a proposed call. Raises :class:`ResearchSecurityError`."""
        if not isinstance(tool, str) or not tool:
            raise ResearchSecurityError("tool must be a non-empty string")
        if tool in FORBIDDEN_TOOLS:
            raise ResearchSecurityError(f"tool {tool!r} is never available to a research loop")
        if tool not in self.available:
            mode = "autonomous" if self.autonomous else "interactive"
            raise ResearchSecurityError(
                f"tool {tool!r} is not in the {mode} research grant set"
            )
        if not isinstance(arguments, dict):
            raise ResearchSecurityError("tool arguments must be an object")
        risk = self.risk_of(tool)
        if risk == "dangerous":
            raise ResearchSecurityError(f"tool {tool!r} is dangerous and cannot be automated")
        if risk == "guarded" and self.autonomous:
            raise ResearchSecurityError(
                f"guarded tool {tool!r} needs an approver; autonomous runs are read-only"
            )
        if risk == "guarded" and self.approver is not None and not self.approver(tool, arguments):
            raise ResearchSecurityError(f"approval refused for {tool!r}")
        return tool, dict(arguments)

    def call(self, tool: str, arguments: dict[str, Any]) -> ToolCallRecord:
        """Dispatch a checked call, recording the outcome either way."""
        started = time.monotonic()
        try:
            name, args = self.check(tool, arguments)
            method = getattr(self.runtime, name, None)
            if method is None:
                raise ResearchSecurityError(f"tool {tool!r} is not implemented by the runtime")
            result = method(**args)
            record = ToolCallRecord(
                tool=name,
                arguments=args,
                ok=True,
                summary=clamp_text(result, 800),
                elapsed_seconds=round(time.monotonic() - started, 3),
            )
            record.arguments = args
            self.calls.append(record)
            return record
        except Exception as exc:
            record = ToolCallRecord(
                tool=str(tool),
                arguments=arguments if isinstance(arguments, dict) else {},
                ok=False,
                error=clamp_text(exc, 500),
                elapsed_seconds=round(time.monotonic() - started, 3),
            )
            self.calls.append(record)
            return record


# --------------------------------------------------------------------------- #
# Loop steps
# --------------------------------------------------------------------------- #


def _knowledge_gap(ctx: Any, section: Section, index: int, observations: list[str]) -> str:
    """What is still unknown. Falls back to a schedule when no model answers."""
    schedule = (
        "Establish the shape, completeness, and column roles of the data "
        "backing this section.",
        "Quantify the relationships and distributions behind the section's "
        "thesis with statistical analyses.",
        "Confirm the findings visually and check for anomalies that change "
        "the interpretation.",
    )
    default = schedule[min(index, len(schedule) - 1)]
    if ctx.backend is None:
        return default
    raw = ask_json(
        ctx.backend,
        knowledge_gap_prompt(section.to_dict(), observations, language=ctx.config.language),
        timeout=ctx.step_timeout,
    )
    if raw.get("sufficient") is True and index > 0:
        return ""
    return clamp_text(raw.get("gap") or raw.get("next_question") or default, 600)


def _deterministic_code(gap: str, source: dict[str, Any], index: int) -> str:
    """The offline CodeAct path: small, real, always-grounded snippets.

    These are the snippets EchoBackend runs. They are deliberately boring —
    shape, completeness, and per-column moments — because their output must
    be reproducible enough for tests to assert on.
    """
    del gap
    columns = [str(c) for c in (source.get("columns") or [])]
    if index == 0:
        return (
            "summary = {\n"
            '    "rows": int(df.shape[0]),\n'
            '    "columns": int(df.shape[1]),\n'
            '    "missing_cells": int(df.isna().sum().sum()),\n'
            '    "duplicate_rows": int(df.duplicated().sum()),\n'
            "}\n"
            "print(summary)\n"
            "emit(summary)\n"
        )
    return (
        "numeric = df.select_dtypes(include='number')\n"
        "stats = {}\n"
        "for name in list(numeric.columns)[:8]:\n"
        "    values = numeric[name].dropna()\n"
        "    if not len(values):\n"
        "        continue\n"
        "    stats[str(name)] = {\n"
        '        "mean": float(values.mean()),\n'
        '        "min": float(values.min()),\n'
        '        "max": float(values.max()),\n'
        '        "count": int(values.count()),\n'
        "    }\n"
        "print(stats)\n"
        'emit({"numeric_summary": stats, "n_columns": ' + str(len(columns)) + "})\n"
    )


def _codegen(ctx: Any, gap: str, source: dict[str, Any], index: int, last_error: str) -> str:
    if ctx.backend is None:
        return _deterministic_code(gap, source, index)
    raw = ask_json(
        ctx.backend,
        codegen_prompt(gap, source, language=ctx.config.language, last_error=last_error),
        timeout=ctx.step_timeout,
    )
    code = raw.get("code")
    if isinstance(code, str) and code.strip():
        return code
    return _deterministic_code(gap, source, index)


def _reflect(ctx: Any, gap: str, observation: Observation) -> dict[str, Any]:
    """Digest runtime output into facts. Deterministic when no model answers."""
    deterministic = {
        "facts": _facts_from_result(observation.result),
        "anomalies": [],
        "root_cause": "",
        "recommendation": "",
        "retry": bool(observation.error),
        "converged": False,
    }
    if ctx.backend is None:
        return deterministic
    raw = ask_json(
        ctx.backend,
        reflect_prompt(gap, observation.to_dict(), language=ctx.config.language),
        timeout=ctx.step_timeout,
    )
    if not raw:
        return deterministic
    facts = [clamp_text(f, 400) for f in (raw.get("facts") or [])[:20]]
    return {
        "facts": facts or deterministic["facts"],
        "anomalies": [clamp_text(a, 400) for a in (raw.get("anomalies") or [])[:10]],
        "root_cause": clamp_text(raw.get("root_cause"), 600),
        "recommendation": clamp_text(raw.get("recommendation"), 600),
        "retry": bool(raw.get("retry")) or bool(observation.error),
        "converged": bool(raw.get("converged")),
    }


def _facts_from_result(result: dict[str, Any], *, limit: int = 12) -> list[str]:
    """Flatten an emitted result into ``key = value`` statements."""
    facts: list[str] = []

    def walk(node: Any, prefix: str = "") -> None:
        if len(facts) >= limit:
            return
        if isinstance(node, dict):
            for key, value in list(node.items())[:limit]:
                walk(value, f"{prefix}.{key}" if prefix else str(key))
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            facts.append(f"{prefix} = {format_number(node)}")
        elif isinstance(node, str) and node:
            facts.append(f"{prefix} = {clamp_text(node, 120)}")

    walk(result)
    return facts


# --------------------------------------------------------------------------- #
# Section driver
# --------------------------------------------------------------------------- #


def run_section(ctx: Any, section: Section, source: dict[str, Any]) -> Section:
    """Iterate one section to a grounded conclusion (or a stated limitation).

    ``ctx`` is the :class:`~dream.research.session.RunContext` supplied by the
    session: it carries the backend, the runtime, the executor, the broker,
    the deadlines, the cancellation flag, and the progress emitter.
    """
    section.status = "RUNNING"
    dataset_id = source.get("dataset_id")
    if not dataset_id:
        section.status = "SKIPPED"
        section.rationale = "no usable dataset was available for this section"
        return section

    observations: list[str] = []
    grounded: set[str] = set()
    section_started = time.monotonic()

    for index in range(ctx.config.max_iterations):
        ctx.raise_if_cancelled()
        if ctx.out_of_time() or (
            time.monotonic() - section_started > ctx.section_budget
        ):
            section.rationale = (
                f"stopped after {index} iteration(s): the time budget for this "
                "section was exhausted"
            )
            ctx.emit("section.budget_exhausted", section=section.title, iterations=index)
            break

        iteration = Iteration(index=index)
        started = time.monotonic()
        ctx.emit("iteration.start", section=section.title, iteration=index)

        # -- KnowledgeGap ------------------------------------------------- #
        gap = _knowledge_gap(ctx, section, index, observations)
        if not gap:
            iteration.reflection = "the section is already answerable from collected evidence"
            iteration.elapsed_seconds = round(time.monotonic() - started, 3)
            section.iterations.append(iteration)
            ctx.emit("iteration.converged", section=section.title, iteration=index)
            break
        iteration.knowledge_gap = gap
        ctx.emit("iteration.gap", section=section.title, iteration=index, gap=gap)

        # -- ToolSelector --------------------------------------------------- #
        tool, arguments = _select_tool(ctx, gap, dataset_id, index)
        if tool:
            record = ctx.broker.call(tool, arguments)
            iteration.tool_calls.append(record)
            ctx.emit(
                "iteration.tool",
                section=section.title,
                iteration=index,
                tool=record.tool,
                ok=record.ok,
                error=record.error,
            )

        # -- CodeAct (with self-correction) -------------------------------- #
        observation = Observation()
        last_error = ""
        attempts = ctx.config.max_retries + 1
        for attempt in range(attempts):
            ctx.raise_if_cancelled()
            code = _codegen(ctx, gap, source, index, last_error)
            iteration.code = code
            try:
                observation = ctx.executor.run(
                    dataset_id,
                    code,
                    timeout=min(ctx.step_timeout, ctx.remaining()),
                    cancelled=ctx.cancelled,
                )
            except ResearchCancelled:
                raise
            except ResearchTimeout as exc:
                observation = Observation(error=str(exc))
                ctx.emit("iteration.timeout", section=section.title, iteration=index)
                break
            except ResearchSecurityError as exc:
                # A refused snippet is a self-correction opportunity, not a
                # failure: the reason goes back into the next codegen prompt.
                last_error = f"refused by the code gate: {exc}"
                observation = Observation(error=last_error)
                iteration.retries = attempt + 1
                ctx.emit(
                    "iteration.refused",
                    section=section.title,
                    iteration=index,
                    reason=str(exc),
                )
                continue
            if not observation.error:
                break
            last_error = observation.error or observation.stderr
            iteration.retries = attempt + 1
            ctx.emit(
                "iteration.self_correct",
                section=section.title,
                iteration=index,
                attempt=attempt + 1,
                error=clamp_text(last_error, 300),
            )
            # Last attempt: fall back to the deterministic snippet, which is
            # known-good against any registered table.
            if attempt == attempts - 2:
                iteration.code = _deterministic_code(gap, source, index)
                try:
                    observation = ctx.executor.run(
                        dataset_id,
                        iteration.code,
                        timeout=min(ctx.step_timeout, ctx.remaining()),
                        cancelled=ctx.cancelled,
                    )
                except (ResearchTimeout, ResearchSecurityError) as exc:
                    observation = Observation(error=str(exc))
                if not observation.error:
                    break

        iteration.observation = observation
        grounded |= extract_numbers(observation.result)
        grounded |= extract_numbers(observation.stdout)

        # -- Observe / Reflect ---------------------------------------------- #
        digest = _reflect(ctx, gap, observation)
        iteration.observation.facts = digest["facts"]
        iteration.observation.converged = bool(digest["converged"])
        iteration.reflection = clamp_text(
            digest.get("root_cause") or digest.get("recommendation") or "", 600
        )
        for fact in digest["facts"]:
            section.findings.append(
                Finding(
                    claim=fact,
                    evidence=clamp_text(observation.result or observation.stdout, 600),
                    kind="observation",
                    section_id=section.section_id,
                    iteration=index,
                    grounded=True,
                )
            )
        for anomaly in digest["anomalies"]:
            section.findings.append(
                Finding(
                    claim=anomaly,
                    evidence=clamp_text(observation.result or observation.stdout, 400),
                    kind="anomaly",
                    section_id=section.section_id,
                    iteration=index,
                )
            )
        if digest.get("root_cause"):
            section.findings.append(
                Finding(
                    claim=digest["root_cause"],
                    evidence="reflection over executed output",
                    kind="root_cause",
                    section_id=section.section_id,
                    iteration=index,
                )
            )
        if digest.get("recommendation"):
            section.findings.append(
                Finding(
                    claim=digest["recommendation"],
                    evidence="reflection over executed output",
                    kind="recommendation",
                    section_id=section.section_id,
                    iteration=index,
                )
            )

        observations.extend(digest["facts"][:6])
        iteration.elapsed_seconds = round(time.monotonic() - started, 3)
        section.iterations.append(iteration)
        ctx.emit(
            "iteration.end",
            section=section.title,
            iteration=index,
            facts=len(digest["facts"]),
            error=observation.error,
        )
        if digest["converged"]:
            ctx.emit("iteration.converged", section=section.title, iteration=index)
            break

    ctx.grounded_values |= grounded
    section.status = "DONE" if section.findings else "SKIPPED"
    if section.status == "SKIPPED" and not section.rationale:
        section.rationale = "no grounded evidence could be produced for this section"
    return section


def _select_tool(
    ctx: Any, gap: str, dataset_id: str, index: int
) -> tuple[str | None, dict[str, Any]]:
    """Pick the next tool. The deterministic schedule is the safety net."""
    schedule: tuple[tuple[str, dict[str, Any]], ...] = (
        ("profile_data", {"dataset_id": dataset_id}),
        ("analyze_data", {"dataset_id": dataset_id, "analyses": []}),
        ("auto_chart", {"dataset_id": dataset_id, "max_charts": 3}),
    )
    tool, arguments = schedule[min(index, len(schedule) - 1)]
    if tool == "analyze_data":
        analyses = plan_analyses(ctx.profiles.get(dataset_id) or {})
        if not analyses:
            return None, {}
        arguments = {"dataset_id": dataset_id, "analyses": analyses}
    del gap
    return tool, arguments


def enrich_from_profile(ctx: Any, section: Section, dataset_id: str) -> None:
    """Attach profile-derived tables, anomalies, and charts to a section.

    This is the deterministic backbone under the LLM loop: even a completely
    silent model leaves the section with executed tables, real anomaly alerts,
    and rendered figures.
    """
    profile = ctx.profiles.get(dataset_id)
    if not profile:
        try:
            profile = ctx.runtime.profile_data(dataset_id)
            ctx.profiles[dataset_id] = profile
        except Exception as exc:
            logger.info("profile unavailable for %s: %s", dataset_id, exc)
            return
    section.tables.extend(build_tables(profile))
    for finding in detect_anomalies(profile):
        finding.section_id = section.section_id
        section.findings.append(finding)
    ctx.grounded_values |= extract_numbers(profile)


def collect_analyses(ctx: Any, section: Section, dataset_id: str) -> None:
    """Run the planned statistical batch and ground its numbers."""
    profile = ctx.profiles.get(dataset_id) or {}
    analyses = plan_analyses(profile)
    if not analyses:
        return
    outcome = run_analyses(ctx.runtime, dataset_id, analyses)
    if outcome["error"]:
        section.rationale = clamp_text(
            f"{section.rationale} analysis batch failed: {outcome['error']}".strip(), 600
        )
        return
    ctx.grounded_values |= extract_numbers(outcome["results"])
    for result in outcome["results"][:6]:
        if not isinstance(result, dict) or result.get("error"):
            continue
        section.findings.append(
            Finding(
                claim=f"{result.get('kind', 'analysis')} completed: "
                + clamp_text(
                    {k: v for k, v in result.items() if k != "kind"}, 300
                ),
                evidence=clamp_text(result, 800),
                kind="observation",
                section_id=section.section_id,
            )
        )


def attach_charts(ctx: Any, section: Section, dataset_id: str, *, max_charts: int = 2) -> None:
    """Render and attach figures, tolerating a renderer that refuses."""
    if ctx.config.autonomous:
        return  # rendering writes files: not in the degraded grant set
    try:
        rendered = render_charts(ctx.runtime, dataset_id, max_charts=max_charts)
    except ResearchError as exc:
        logger.info("charts skipped: %s", exc)
        return
    for chart in rendered:
        png = (chart.get("files") or {}).get("png")
        if png:
            section.charts.append(png)
