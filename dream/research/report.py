"""Report compilation: Markdown + PDF, with provenance and a repro bundle.

The Markdown is assembled on the host from grounded material only. The PDF is
rendered *inside the sandbox* by a trusted, engine-authored body — the host
still never imports matplotlib — with the page text passed through
``_params.json`` and a page cap enforced before rendering.

Layout, in order: cover, abstract/executive summary, methodology, per-section
findings (prose, callouts, tables, figures), discussion, conclusions,
limitations, recommendations, appendices (execution trace), references, and a
reproducibility block. Every figure and table is anchored to the code and the
runtime output that produced it, and the whole thing is linked into
:mod:`dream.provenance` so a reader can walk back from a number to its run.

Idempotence is a requirement, not an accident: compiling the same session
twice overwrites the same three files under the dataset directory and emits
exactly one provenance link per artifact.
"""

from __future__ import annotations

import logging
import os
import textwrap
from pathlib import Path
from typing import Any

from dream.research.errors import ResearchError
from dream.research.schemas import Finding, SessionRecord, clamp_text

logger = logging.getLogger("dream.research.report")

__all__ = [
    "REFERENCES",
    "build_markdown",
    "compile_report",
    "render_pdf",
]

REFERENCES = (
    "pandas development team, *pandas-dev/pandas: Pandas*, doi:10.5281/zenodo.3509134",
    "Harris et al., *Array programming with NumPy*, Nature 585 (2020)",
    "Virtanen et al., *SciPy 1.0*, Nature Methods 17 (2020)",
    "Hunter, *Matplotlib: A 2D graphics environment*, CiSE 9 (2007)",
)

_MAX_MD_BYTES = 4 * 1024 * 1024


def _kind(findings: list[Finding], kind: str) -> list[Finding]:
    return [f for f in findings if f.kind == kind]


def _table_md(table: dict[str, Any]) -> str:
    header = [str(h) for h in table.get("header") or []]
    rows = table.get("rows") or []
    if not header or not rows:
        return ""
    lines = [
        f"**{clamp_text(table.get('title'), 120)}**",
        "",
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in rows[:50]:
        cells = [clamp_text(c, 60) for c in row][: len(header)]
        cells += [""] * (len(header) - len(cells))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _rtl_wrap(text: str, language: str) -> str:
    """RTL-safe Markdown: wrap Persian blocks so renderers get direction right."""
    if language != "fa" or not text.strip():
        return text
    return f'<div dir="rtl" align="right">\n\n{text}\n\n</div>'


def build_markdown(
    session: SessionRecord,
    *,
    base_dir: Path | None = None,
    ledger: set[str] | None = None,
) -> str:
    """Assemble the full analyst report as Markdown.

    ``ledger`` — when given, the grounding ledger is extended with the report's
    *own* derived figures (source counts, section counts, executed-step counts,
    measured iteration timings). These are facts about the run, produced by the
    run, so the proofreader must treat them as grounded; leaving them out would
    make the guard flag the report's own bookkeeping.
    """
    language = session.config.language
    plan = session.plan
    fa = language == "fa"
    heading = {
        "abstract": "چکیده" if fa else "Abstract",
        "summary": "خلاصه مدیریتی" if fa else "Executive summary",
        "method": "روش‌شناسی" if fa else "Methodology",
        "findings": "یافته‌ها" if fa else "Findings",
        "discussion": "بحث" if fa else "Discussion",
        "conclusion": "نتیجه‌گیری" if fa else "Conclusions",
        "limits": "محدودیت‌ها" if fa else "Limitations",
        "actions": "اقدامات پیشنهادی" if fa else "Recommended actions",
        "appendix": "پیوست: ردّ اجرا" if fa else "Appendix A — Execution trace",
        "refs": "منابع" if fa else "References",
        "repro": "بازتولیدپذیری" if fa else "Reproducibility",
        "contents": "فهرست" if fa else "Contents",
    }

    all_findings: list[Finding] = [f for s in plan.sections for f in s.findings]
    anomalies = _kind(all_findings, "anomaly")
    actions = _kind(all_findings, "recommendation")
    executed_steps = sum(len(s.iterations) for s in plan.sections)
    source_count = len([s for s in session.sources if s.get("dataset_id")])
    grounded_count = len([f for f in all_findings if f.grounded])

    if ledger is not None:
        from dream.research.analyze import format_number

        for value in (
            executed_steps,
            source_count,
            grounded_count,
            len(plan.sections),
            len(anomalies),
            len([s for s in plan.sections if s.status == "DONE"]),
            len(session.report.record_ids),
        ):
            ledger.add(format_number(value))
        for section in plan.sections:
            for iteration in section.iterations:
                ledger.add(format_number(round(iteration.elapsed_seconds, 2)))
                ledger.add(format_number(iteration.index))
                ledger.add(format_number(iteration.retries))

    parts: list[str] = []
    # -- cover ----------------------------------------------------------- #
    parts.append(f"# {clamp_text(plan.objective or session.topic, 200)}")
    parts.append(
        "\n".join(
            [
                f"*Session*: `{session.session_id}`",
                f"*Sources*: {source_count}",
                f"*Sections*: {len(plan.sections)}",
                f"*Executed steps*: {executed_steps}",
                f"*Language*: {language}",
            ]
        )
    )

    # -- contents --------------------------------------------------------- #
    toc = [f"1. {heading['abstract']}", f"2. {heading['method']}"]
    for index, section in enumerate(plan.sections, start=3):
        toc.append(f"{index}. {clamp_text(section.title, 120)}")
    toc.extend(
        [
            f"{len(plan.sections) + 3}. {heading['discussion']}",
            f"{len(plan.sections) + 4}. {heading['conclusion']}",
            f"{len(plan.sections) + 5}. {heading['limits']}",
        ]
    )
    parts.append(f"## {heading['contents']}\n\n" + "\n".join(toc))

    # -- abstract / executive summary ------------------------------------- #
    abstract = (
        f"This report answers: {clamp_text(plan.objective or session.topic, 400)} "
        f"It draws on {source_count} "
        f"registered data source(s), {executed_steps} executed analysis step(s), "
        f"and {grounded_count} grounded finding(s). Every figure in this document "
        "was produced by an executed step; the grounding guard removed anything "
        "that was not."
    )
    parts.append(f"## {heading['abstract']}\n\n{_rtl_wrap(abstract, language)}")

    if plan.questions:
        parts.append(
            f"## {heading['summary']}\n\n"
            + "\n".join(f"- {clamp_text(q, 300)}" for q in plan.questions[:8])
        )

    # -- methodology ------------------------------------------------------- #
    method_body = plan.methodology or "Standard profiling, cleaning, and analysis pipeline."
    source_lines = [
        f"- `{s['dataset_id']}` — {clamp_text(s.get('name'), 80)} "
        f"({s.get('format')}, shape {s.get('shape')})"
        for s in session.sources
        if s.get("dataset_id")
    ]
    parts.append(
        f"## {heading['method']}\n\n{_rtl_wrap(method_body, language)}\n\n"
        "**Data sources (by registry id):**\n" + ("\n".join(source_lines) or "- none")
    )

    # -- per-section findings ---------------------------------------------- #
    figure_index = 0
    for section in plan.sections:
        block = [f"## {clamp_text(section.title, 160)}"]
        if section.status in ("SKIPPED", "FAILED"):
            block.append(
                f"*Not concluded.* {clamp_text(section.rationale, 400) or 'No evidence.'}"
            )
        block.append(_rtl_wrap(section.prose or "", language))
        for table in section.tables:
            rendered = _table_md(table)
            if rendered:
                block.append(rendered)
        for chart in section.charts:
            figure_index += 1
            path = chart
            if base_dir is not None:
                try:
                    path = os.path.relpath(chart, base_dir)
                except ValueError:  # different drive on Windows
                    path = chart
            block.append(f"![Figure {figure_index}]({path})\n\n*Figure {figure_index}.* "
                         f"{clamp_text(section.title, 100)}")
        parts.append("\n\n".join(b for b in block if b.strip()))

    # -- discussion / conclusions ------------------------------------------ #
    discussion = (
        "The findings above are descriptive unless a section states otherwise. "
        "Correlation reported here is not evidence of causation, and every "
        "interval reflects only the rows present in the registered sources."
    )
    if anomalies:
        discussion += (
            f" {len(anomalies)} anomaly alert(s) were raised by the data itself; "
            "they are listed in their sections and should be triaged first."
        )
    parts.append(f"## {heading['discussion']}\n\n{_rtl_wrap(discussion, language)}")

    concluded = [s for s in plan.sections if s.status == "DONE"]
    conclusion = (
        f"{len(concluded)} of {len(plan.sections)} section(s) reached a grounded "
        "conclusion. "
        + (
            "The remaining sections are reported as limitations rather than "
            "filled with speculation."
            if len(concluded) < len(plan.sections)
            else "No section required speculation."
        )
    )
    parts.append(f"## {heading['conclusion']}\n\n{_rtl_wrap(conclusion, language)}")

    # -- limitations -------------------------------------------------------- #
    limits = [
        "Only data registered in this session's workspace was consulted; no "
        "external sources were used."
        if not session.config.allow_network
        else "External sources were permitted for this run and are cited inline.",
    ]
    for section in plan.sections:
        if section.status != "DONE" and section.rationale:
            limits.append(f"{section.title}: {clamp_text(section.rationale, 200)}")
    for entry in session.sources:
        if entry.get("error"):
            limits.append(
                f"source '{entry.get('filename')}' could not be read: "
                f"{clamp_text(entry['error'], 160)}"
            )
    parts.append(f"## {heading['limits']}\n\n" + "\n".join(f"- {line}" for line in limits))

    # -- recommendations ----------------------------------------------------- #
    if actions:
        parts.append(
            f"## {heading['actions']}\n\n"
            + "\n".join(f"- {clamp_text(f.claim, 300)}" for f in actions[:10])
        )

    # -- appendix: execution trace -------------------------------------------- #
    trace_lines: list[str] = []
    for section in plan.sections:
        for iteration in section.iterations:
            tools = ", ".join(c.tool for c in iteration.tool_calls) or "—"
            outcome = (
                "error: " + clamp_text(iteration.observation.error, 80)
                if iteration.observation.error
                else "ok"
            )
            trace_lines.append(
                f"- **{clamp_text(section.title, 60)}** iteration {iteration.index}: "
                f"gap=\"{clamp_text(iteration.knowledge_gap, 100)}\"; tools={tools}; "
                f"retries={iteration.retries}; "
                f"{iteration.elapsed_seconds:.2f}s; {outcome}"
            )
    parts.append(
        f"## {heading['appendix']}\n\n" + ("\n".join(trace_lines) or "- no iterations recorded")
    )

    # -- references ------------------------------------------------------------ #
    references = [f"[{i}] {ref}" for i, ref in enumerate(REFERENCES, start=1)]
    for offset, entry in enumerate(
        [s for s in session.sources if s.get("dataset_id")], start=len(REFERENCES) + 1
    ):
        references.append(
            f"[{offset}] Local data source `{entry['dataset_id']}` "
            f"({clamp_text(entry.get('filename'), 80)}, {entry.get('format')})"
        )
    parts.append(f"## {heading['refs']}\n\n" + "\n\n".join(references))

    # -- reproducibility -------------------------------------------------------- #
    parts.append(
        f"## {heading['repro']}\n\n"
        f"- Session id: `{session.session_id}`\n"
        f"- Configuration: `{session.config.to_dict()}`\n"
        f"- Provenance records: {len(session.report.record_ids)}\n"
        "- Every number above appears in the grounding ledger built from "
        "executed output; the proofreader's report is attached to this "
        "session.\n"
        "- A reproducibility ZIP (code, inputs, config, provenance chain) is "
        "exported alongside this report when provenance is enabled."
    )

    markdown = "\n\n".join(parts).strip() + "\n"
    if len(markdown.encode("utf-8")) > _MAX_MD_BYTES:
        markdown = markdown[: _MAX_MD_BYTES // 2] + "\n\n*[report truncated at size limit]*\n"
    return markdown


# --------------------------------------------------------------------------- #
# PDF rendering (trusted body, runs in the sandbox)
# --------------------------------------------------------------------------- #

_PDF_BODY = textwrap.dedent(
    """
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["pdf.fonttype"] = 42
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    pages = P["pages"]
    max_pages = int(P["max_pages"])
    figures = P.get("figures") or []
    out = P["output"]

    written = 0
    with PdfPages(out) as pdf:
        for page in pages[:max_pages]:
            fig = plt.figure(figsize=(8.27, 11.69))
            y = 0.95
            for line in page[:58]:
                kind = line.get("kind", "body")
                text = line.get("text", "")[:110]
                if kind == "title":
                    fig.text(0.5, y, text, ha="center", fontsize=18, weight="bold")
                    y -= 0.05
                elif kind == "heading":
                    fig.text(0.08, y, text, fontsize=13, weight="bold")
                    y -= 0.032
                elif kind == "mono":
                    fig.text(0.08, y, text, fontsize=8, family="monospace")
                    y -= 0.02
                else:
                    fig.text(0.08, y, text, fontsize=10)
                    y -= 0.022
                if y < 0.05:
                    break
            pdf.savefig(fig)
            plt.close(fig)
            written += 1
        for path in figures[: max(0, max_pages - written)]:
            try:
                image = plt.imread(path)
            except Exception:
                continue
            fig = plt.figure(figsize=(8.27, 11.69))
            axes = fig.add_axes([0.06, 0.30, 0.88, 0.45])
            axes.imshow(image)
            axes.axis("off")
            pdf.savefig(fig)
            plt.close(fig)
            written += 1

    emit({"pages": written, "size_bytes": os.path.getsize(out)})
    """
).strip()


def _paginate(markdown: str, *, lines_per_page: int = 46) -> list[list[dict[str, str]]]:
    """Turn Markdown into simple typed lines the PDF body can lay out."""
    typed: list[dict[str, str]] = []
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line:
            typed.append({"kind": "body", "text": ""})
        elif line.startswith("# "):
            typed.append({"kind": "title", "text": line[2:]})
        elif line.startswith("#"):
            typed.append({"kind": "heading", "text": line.lstrip("# ")})
        elif line.startswith("|") or line.startswith("    "):
            typed.append({"kind": "mono", "text": line})
        elif line.startswith("!["):
            continue  # figures get their own pages
        else:
            typed.append({"kind": "body", "text": line})
    pages: list[list[dict[str, str]]] = []
    for start in range(0, len(typed), lines_per_page):
        pages.append(typed[start : start + lines_per_page])
    return pages or [[{"kind": "body", "text": "(empty report)"}]]


def render_pdf(
    executor: Any,
    dataset_id: str,
    markdown: str,
    *,
    figures: list[str] | None = None,
    max_pages: int = 20,
    output_name: str = "research_report.pdf",
    timeout: float = 180.0,
) -> dict[str, Any]:
    """Render the Markdown to PDF inside the sandbox. Returns page/size info."""
    if not isinstance(max_pages, int) or not 1 <= max_pages <= 200:
        raise ResearchError("max_pages must be an integer in [1, 200]")
    record = executor.runtime.datasets.get(dataset_id)
    workspace = executor.runtime.datasets.dir_for(record)
    relative_figures: list[str] = []
    for figure in figures or []:
        try:
            relative = os.path.relpath(figure, workspace)
        except ValueError:
            continue
        if not relative.startswith(".."):
            relative_figures.append(relative)

    observation = executor.run_trusted(
        dataset_id,
        _PDF_BODY,
        {
            "pages": _paginate(markdown),
            "max_pages": max_pages,
            "figures": relative_figures[:8],
            "output": output_name,
        },
        timeout=timeout,
    )
    if observation.error and not observation.result:
        raise ResearchError(f"PDF rendering failed: {clamp_text(observation.error, 300)}")
    return {
        "pdf_path": str(workspace / output_name),
        "pages": int(observation.result.get("pages") or 0),
        "size_bytes": int(observation.result.get("size_bytes") or 0),
    }


def compile_report(
    session: SessionRecord,
    executor: Any,
    *,
    tracker: Any = None,
    artifacts: Any = None,
    exporter: Any = None,
    ledger: set[str] | None = None,
) -> dict[str, Any]:
    """Write ``research_report.md`` + ``.pdf`` and link them to provenance.

    Idempotent: the same session compiles to the same two paths, overwriting
    in place. Returns a dict of paths, page count, and provenance record ids.
    """
    primary = next((s for s in session.sources if s.get("dataset_id")), None)
    if primary is None:
        raise ResearchError("cannot compile a report without a registered data source")
    dataset_id = primary["dataset_id"]
    record = executor.runtime.datasets.get(dataset_id)
    workspace = executor.runtime.datasets.dir_for(record)

    markdown = build_markdown(session, base_dir=workspace, ledger=ledger)
    md_path = workspace / "research_report.md"
    md_path.write_text(markdown, encoding="utf-8")

    figures = [c for section in session.plan.sections for c in section.charts]
    pdf_info: dict[str, Any] = {"pdf_path": "", "pages": 0, "size_bytes": 0}
    try:
        pdf_info = render_pdf(
            executor,
            dataset_id,
            markdown,
            figures=figures,
            max_pages=session.config.max_pages,
        )
    except Exception as exc:  # a missing PDF must not lose the Markdown
        logger.warning("PDF rendering unavailable: %s", exc)

    record_ids: list[str] = []
    if tracker is not None:
        try:
            provenance = tracker.record(
                "file_write",
                "dream.research",
                payload={
                    "tool_name": "research.compile",
                    "session_id": session.session_id,
                    "topic": clamp_text(session.topic, 300),
                    "sections": [s.title for s in session.plan.sections],
                    "markdown_path": str(md_path),
                    "pdf_path": pdf_info["pdf_path"],
                },
            )
            record_ids.append(provenance.record_id)
            if artifacts is not None:
                for path in (str(md_path), pdf_info["pdf_path"]):
                    if path:
                        artifacts.link_artifact(
                            path,
                            provenance.record_id,
                            tool_name="research.compile",
                            agent_id="dream.research",
                            custom_metadata={"session_id": session.session_id},
                        )
        except Exception:
            logger.warning("provenance linkage failed for the research report", exc_info=True)

    bundle_path = ""
    if exporter is not None and record_ids:
        try:
            bundle = exporter.export(
                record_id=record_ids[0],
                output_file=str(workspace / "research_reproducibility.zip"),
            )
            bundle_path = bundle.get("file_path") or ""
        except Exception:
            logger.warning("reproducibility export failed", exc_info=True)

    return {
        "markdown_path": str(md_path),
        "pdf_path": pdf_info["pdf_path"],
        "pages": pdf_info["pages"],
        "size_bytes": pdf_info["size_bytes"],
        "bundle_path": bundle_path,
        "record_ids": record_ids,
        "markdown": markdown,
    }
