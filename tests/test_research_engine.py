"""End-to-end and unit coverage for the research engine (P1).

Every test here runs fully offline: the deterministic ``EchoBackend`` (or no
backend at all), the guarded local subprocess executor, and a temporary
dataset registry. Tests that need pandas skip cleanly when the scientific
stack is absent, so the suite stays green on a bare interpreter.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dream.agent import EchoBackend
from dream.research import (
    ResearchConfig,
    ResearchEngine,
    ResearchError,
    SessionStore,
)
from dream.research.analyze import (
    build_tables,
    detect_anomalies,
    extract_numbers,
    format_number,
    plan_analyses,
)
from dream.research.discovery import relevance_score, safe_workspace
from dream.research.planner import fallback_plan
from dream.research.prep import SchemaTracker, propose_operations
from dream.research.schemas import (
    Finding,
    Section,
    SessionRecord,
    clamp_text,
    parse_json_object,
)

pandas = pytest.importorskip("pandas", reason="the research engine needs pandas in the sandbox")

SALES_CSV = """month,region,revenue,units,discount
2024-01,north,1200,30,0.05
2024-02,north,1350,33,0.05
2024-03,north,900,22,0.15
2024-04,north,1500,36,0.02
2024-01,south,800,20,0.10
2024-02,south,760,19,0.10
2024-03,south,300,8,0.30
2024-04,south,9000,210,0.00
"""


@pytest.fixture()
def space(tmp_path: Path) -> Path:
    workspace = tmp_path / "space"
    workspace.mkdir()
    (workspace / "sales.csv").write_text(SALES_CSV, encoding="utf-8")
    return workspace


@pytest.fixture()
def engine(tmp_path: Path, monkeypatch) -> ResearchEngine:
    monkeypatch.setenv("DREAM_DATA_LOCAL_EXEC", "1")
    monkeypatch.setenv("DREAM_DATASETS_DIR", str(tmp_path / "datasets"))
    from dream.skills.data_science import DataScienceRuntime

    return ResearchEngine(
        store=SessionStore(tmp_path / "research"),
        runtime=DataScienceRuntime(),
        backend=EchoBackend(),
    )


# --------------------------------------------------------------------------- #
# Schemas + parsing
# --------------------------------------------------------------------------- #


def test_tolerant_json_parser_handles_fences_prose_and_trailing_commas():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Sure! Here you go: {"a": [1, 2,], "b": "x"} Hope that helps.') == {
        "a": [1, 2],
        "b": "x",
    }
    assert parse_json_object("not json at all") == {}
    assert parse_json_object(None) == {}
    assert parse_json_object('{"nested": {"brace": "} inside a string"}}')["nested"]


def test_config_clamps_out_of_range_values():
    config = ResearchConfig(max_iterations=9999, max_time_seconds=1e12, max_retries=-3)
    assert config.max_iterations == 10
    assert config.max_time_seconds == 24 * 3600.0
    assert config.max_retries == 0
    with pytest.raises(ResearchError):
        ResearchConfig(language="klingon")


def test_clamp_text_bounds_and_flattens():
    assert clamp_text(None) == ""
    assert clamp_text(["a", "b"]) == "a b"
    assert len(clamp_text("x" * 10_000, 100)) <= 102


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


def test_relevance_scores_column_matches_above_unrelated_sources():
    hit = relevance_score("revenue by region", "sales", ["revenue", "region", "units"])
    miss = relevance_score("revenue by region", "weather", ["temperature", "humidity"])
    assert hit > miss
    assert 0.0 <= hit <= 1.0


def test_relevance_is_persian_normalised():
    assert relevance_score("فروش ماهانه", "گزارش", ["فروش", "ماه"]) > 0


def test_safe_workspace_refuses_non_directories(tmp_path: Path):
    with pytest.raises(ResearchError):
        safe_workspace(str(tmp_path / "nope"))
    with pytest.raises(ResearchError):
        safe_workspace("")


def test_discovery_registers_sources_by_id_only(engine: ResearchEngine, space: Path):
    session = engine.create("revenue by region", str(space))
    sources = session.discover()
    assert sources and all(len(s["dataset_id"]) == 32 for s in sources if s.get("dataset_id"))
    assert sources[0]["columns"][:2] == ["month", "region"]
    # Idempotent: a second call must not re-ingest.
    assert session.discover() == sources


def test_discovery_skips_symlinks_pointing_outside_the_space(
    engine: ResearchEngine, space: Path, tmp_path: Path
):
    outside = tmp_path / "secret.csv"
    outside.write_text("a,b\n1,2\n", encoding="utf-8")
    try:
        (space / "link.csv").symlink_to(outside)
    except OSError:  # pragma: no cover - platform without symlink permission
        pytest.skip("symlinks unavailable")
    session = engine.create("revenue", str(space))
    names = {s.get("filename") for s in session.discover()}
    assert "secret.csv" not in names


# --------------------------------------------------------------------------- #
# Planning + approval
# --------------------------------------------------------------------------- #


def test_fallback_plan_is_a_real_runnable_plan():
    plan = fallback_plan(
        "why did revenue drop",
        [{"dataset_id": "a" * 32, "name": "sales", "columns": ["revenue"]}],
    )
    assert plan.sections and plan.questions and plan.methodology
    assert plan.datasets == ["a" * 32]
    assert plan.source == "fallback"


def test_plan_moves_to_approval_pending_and_estimates_cost(
    engine: ResearchEngine, space: Path
):
    session = engine.create("revenue drop by region", str(space))
    plan = session.plan()
    assert session.status == "APPROVAL_PENDING"
    assert plan.sections
    assert session.record.cost_estimate["estimated_model_calls"] > 0


def test_start_is_refused_before_approval(engine: ResearchEngine, space: Path):
    session = engine.create("revenue", str(space))
    session.plan()
    with pytest.raises(ResearchError, match="approved"):
        session.start()


def test_modify_replaces_the_outline_and_bumps_the_revision(
    engine: ResearchEngine, space: Path
):
    session = engine.create("revenue", str(space))
    session.plan()
    before = session.record.plan.revision
    plan = session.modify(
        {"sections": [{"title": "Only section", "thesis": "one thesis"}],
         "objective": "edited objective"}
    )
    assert [s.title for s in plan.sections] == ["Only section"]
    assert plan.objective == "edited objective"
    assert plan.revision == before + 1
    assert plan.approved is False and plan.source == "user"


def test_modify_rejects_a_bad_outline(engine: ResearchEngine, space: Path):
    session = engine.create("revenue", str(space))
    session.plan()
    with pytest.raises(ResearchError):
        session.modify({"sections": []})
    with pytest.raises(ResearchError):
        session.modify({"sections": [{"thesis": "no title"}]})
    with pytest.raises(ResearchError):
        session.modify({})


def test_illegal_transitions_are_refused(engine: ResearchEngine, space: Path):
    session = engine.create("revenue", str(space))
    with pytest.raises(ResearchError, match="illegal transition"):
        session.transition("COMPLETE")
    with pytest.raises(ResearchError, match="unknown status"):
        session.transition("BANANA")


# --------------------------------------------------------------------------- #
# Prep / analysis helpers
# --------------------------------------------------------------------------- #


def test_schema_tracker_follows_renames_and_drops():
    tracker = SchemaTracker(["a", "b", "c"])
    tracker.apply({"op": "rename_column", "column": "a", "new_name": "z"})
    tracker.apply({"op": "drop_column", "column": "b"})
    assert tracker.columns == ["z", "c"]
    assert not tracker.knows("a")


def test_prep_proposals_are_triggered_by_real_statistics():
    profile = {
        "row_count": 100,
        "duplicate_rows": 4,
        "columns": {
            "x": {"role": "numeric", "missing": 10},
            "y": {"role": "categorical", "missing": 5},
            "z": {"role": "numeric", "missing": 90},  # too damaged to impute
            "w": {"role": "numeric", "missing": 0},
        },
    }
    ops = propose_operations(profile, SchemaTracker(["x", "y", "z", "w"]))
    tags = [(o["op"], o.get("column")) for o in ops]
    assert ("remove_duplicates", None) in tags
    assert ("fill_na", "x") in tags
    assert ("fill_na", "z") not in tags
    assert ("fill_na", "w") not in tags


def test_anomaly_detection_flags_spikes_and_missingness():
    profile = {
        "row_count": 50,
        "duplicate_rows": 0,
        "columns": {
            "rev": {"role": "numeric", "mean": 10.0, "std": 1.0, "min": 9.0,
                    "max": 90.0, "missing": 0},
            "gap": {"role": "numeric", "mean": 1.0, "std": 1.0, "min": 0.0,
                    "max": 2.0, "missing": 25},
        },
    }
    kinds = {f.metric for f in detect_anomalies(profile)}
    assert "rev.high" in kinds
    assert "gap.missing" in kinds


def test_plan_analyses_uses_profiled_roles():
    profile = {
        "columns": {
            "a": {"role": "numeric"},
            "b": {"role": "numeric"},
            "c": {"role": "categorical"},
        }
    }
    kinds = [a["kind"] for a in plan_analyses(profile)]
    assert "correlation" in kinds and "groupby" in kinds and "regression" in kinds
    assert plan_analyses({}) == []


def test_extract_numbers_walks_nested_output_and_strings():
    found = extract_numbers({"a": 1, "b": [2.5, {"c": "value 3.75 here"}], "d": True})
    assert {"1", "2.5", "3.75"} <= found
    assert "True" not in found


def test_build_tables_only_reports_numeric_columns():
    tables = build_tables(
        {"columns": {"n": {"role": "numeric", "count": 5, "mean": 2.0, "std": 1.0,
                           "min": 1, "max": 3},
                     "t": {"role": "text"}}}
    )
    assert tables[0]["rows"][0][0] == "n"
    assert len(tables[0]["rows"]) == 1
    assert build_tables({"columns": {}}) == []


def test_format_number_is_canonical():
    assert format_number(3.0) == "3"
    assert format_number("3.14159") == "3.142"


# --------------------------------------------------------------------------- #
# Full pipeline
# --------------------------------------------------------------------------- #


def test_offline_end_to_end_produces_a_grounded_report(engine: ResearchEngine, space: Path):
    session = engine.run(
        "Why did revenue drop in March by region?",
        str(space),
        config={"max_iterations": 2, "max_sections": 3},
    )
    record = session.record
    assert record.status == "COMPLETE", record.error
    markdown = Path(record.report.markdown_path).read_text(encoding="utf-8")

    # Structure: an analyst report, not a data dump.
    for heading in ("Abstract", "Methodology", "Discussion", "Conclusions",
                    "Limitations", "References", "Reproducibility",
                    "Execution trace"):
        assert heading in markdown, heading

    # Grounding: the audit passes and the report's numbers came from execution.
    audit = record.report.proofread["final"]
    assert audit["ok"], audit
    assert record.report.proofread["grounded_values"] > 0

    # The report cites the registry id, never a raw filesystem path.
    assert record.sources[0]["dataset_id"] in markdown
    assert str(space) not in markdown

    # PDF compiled within the page cap.
    assert record.report.pages and record.report.pages <= record.config.max_pages
    assert Path(record.report.pdf_path).exists()


def test_report_numbers_match_executed_output(engine: ResearchEngine, space: Path):
    session = engine.run("row counts", str(space), config={"max_iterations": 1})
    assert session.record.status == "COMPLETE"
    # The seeded CSV has 8 rows; the profile executed in the sandbox must agree
    # and that number must be in the grounding ledger the report was audited on.
    emitted = [
        it.observation.result
        for section in session.record.plan.sections
        for it in section.iterations
        if it.observation.result
    ]
    assert any(result.get("rows") == 8 for result in emitted)


def test_rerunning_a_completed_session_is_idempotent(engine: ResearchEngine, space: Path):
    session = engine.run("revenue", str(space), config={"max_iterations": 1})
    first = Path(session.record.report.markdown_path).read_text(encoding="utf-8")
    charts_before = list(
        Path(session.record.report.markdown_path).parent.glob("charts/*.png")
    )
    with pytest.raises(ResearchError):
        session.start()  # COMPLETE is terminal; no duplicate artifacts
    second = Path(session.record.report.markdown_path).read_text(encoding="utf-8")
    assert first == second
    assert charts_before == list(
        Path(session.record.report.markdown_path).parent.glob("charts/*.png")
    )


def test_persian_run_produces_rtl_safe_output(engine: ResearchEngine, space: Path):
    session = engine.run(
        "چرا درآمد کاهش یافت؟",
        str(space),
        config={"language": "fa", "max_iterations": 1, "max_sections": 2},
    )
    assert session.record.status == "COMPLETE", session.record.error
    markdown = Path(session.record.report.markdown_path).read_text(encoding="utf-8")
    assert "چکیده" in markdown
    assert 'dir="rtl"' in markdown


def test_session_is_persisted_and_resumable(engine: ResearchEngine, space: Path, tmp_path):
    session = engine.run("revenue", str(space), config={"max_iterations": 1})
    session_id = session.record.session_id
    store = SessionStore(tmp_path / "research")
    reloaded = store.load(session_id)
    assert reloaded.status == "COMPLETE"
    assert reloaded.plan.sections[0].findings
    assert reloaded.report.markdown_path == session.record.report.markdown_path
    raw = json.loads((tmp_path / "research" / f"{session_id}.json").read_text("utf-8"))
    assert raw["session_id"] == session_id


def test_engine_list_and_delete(engine: ResearchEngine, space: Path):
    session = engine.create("revenue", str(space))
    listed = engine.list()
    assert any(s["session_id"] == session.record.session_id for s in listed)
    assert engine.delete(session.record.session_id) is True
    assert engine.delete(session.record.session_id) is False


def test_publish_requires_a_complete_session(engine: ResearchEngine, space: Path):
    session = engine.create("revenue", str(space))
    with pytest.raises(ResearchError, match="COMPLETE"):
        session.publish()
    session.plan()
    session.approve()
    session.start()
    report = session.publish()
    assert session.record.published is True
    assert report["markdown_path"]


def test_progress_events_describe_the_trace(engine: ResearchEngine, space: Path):
    seen: list[str] = []
    session = engine.create("revenue", str(space), config={"max_iterations": 1})
    session.subscribe(lambda event: seen.append(event["event"]))
    session.plan()
    session.approve()
    session.start()
    for expected in ("discovery.start", "plan.ready", "section.start",
                     "iteration.start", "proofread.done", "report.compiled"):
        assert expected in seen, expected


def test_cancel_mid_run_stops_cleanly_and_is_terminal(engine: ResearchEngine, space: Path):
    session = engine.create("revenue", str(space), config={"max_iterations": 3})
    session.plan()
    session.approve()
    # Cancel as soon as the first section starts: the next step boundary must
    # unwind the run rather than push on to a report.
    session.subscribe(
        lambda event: session.cancel() if event["event"] == "section.start" else None
    )
    session.start()
    assert session.record.status == "CANCELLED"
    assert not session.record.report.markdown_path
    with pytest.raises(ResearchError, match="CANCELLED"):
        session.start()


def test_a_failing_section_does_not_sink_the_report(engine: ResearchEngine, space: Path,
                                                    monkeypatch):
    session = engine.create("revenue", str(space), config={"max_iterations": 1})
    session.plan()
    session.approve()

    from dream.research import iterate as iterate_module

    real = iterate_module.run_section
    calls = {"n": 0}

    def exploding(ctx, section, source):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("synthetic section failure")
        return real(ctx, section, source)

    monkeypatch.setattr(iterate_module, "run_section", exploding)
    session.start()
    assert session.record.status == "COMPLETE", session.record.error
    statuses = {s.status for s in session.record.plan.sections}
    assert "FAILED" in statuses
    markdown = Path(session.record.report.markdown_path).read_text(encoding="utf-8")
    assert "synthetic section failure" in markdown  # surfaced as a limitation


def test_findings_and_sections_round_trip_through_json():
    section = Section(section_id="a" * 32, title="T", thesis="th")
    section.findings.append(Finding(claim="c", evidence="e", kind="anomaly"))
    record = SessionRecord(session_id="b" * 32, topic="t")
    record.plan.sections.append(section)
    revived = SessionRecord.from_dict(json.loads(json.dumps(record.to_dict())))
    assert revived.plan.sections[0].findings[0].kind == "anomaly"
    assert revived.plan.sections[0].section_id == "a" * 32


# --------------------------------------------------------------------------- #
# Self-correction and no-hang
# --------------------------------------------------------------------------- #


def test_the_loop_self_corrects_after_a_broken_snippet(engine: ResearchEngine, space: Path):
    """A model that emits broken code once must recover, not fail the section."""

    class FlakyBackend:
        """Emits an exploding snippet first, then a valid one."""

        def __init__(self) -> None:
            self.code_calls = 0

        def chat(self, messages, tools=None):
            prompt = messages[-1]["content"]
            if "CodeAct step" in prompt:
                self.code_calls += 1
                if self.code_calls == 1:
                    return {
                        "content": '{"code": "emit({\'v\': df[\'ghost_column\'].sum()})",'
                        ' "expects": "boom"}',
                        "tool_calls": [],
                    }
                return {
                    "content": '{"code": "emit({\'rows\': int(df.shape[0])})",'
                    ' "expects": "row count"}',
                    "tool_calls": [],
                }
            return {"content": "", "tool_calls": []}

    backend = FlakyBackend()
    engine.backend = backend
    session = engine.run(
        "row counts", str(space), config={"max_iterations": 1, "max_sections": 1,
                                          "max_retries": 2}
    )
    assert session.record.status == "COMPLETE", session.record.error
    iterations = session.record.plan.sections[0].iterations
    assert any(it.retries >= 1 for it in iterations), "no self-correction was recorded"
    assert any(it.observation.result.get("rows") == 8 for it in iterations)
    assert backend.code_calls >= 2


def test_a_refused_snippet_is_fed_back_and_recovered(engine: ResearchEngine, space: Path):
    """The AST gate's refusal is a self-correction signal, not a dead end."""

    class UnsafeThenSafeBackend:
        def __init__(self) -> None:
            self.code_calls = 0

        def chat(self, messages, tools=None):
            if "CodeAct step" in messages[-1]["content"]:
                self.code_calls += 1
                if self.code_calls == 1:
                    return {
                        "content": '{"code": "import os\\nemit({\'p\': os.getcwd()})"}',
                        "tool_calls": [],
                    }
                return {"content": '{"code": "emit({\'rows\': int(df.shape[0])})"}',
                        "tool_calls": []}
            return {"content": "", "tool_calls": []}

    engine.backend = UnsafeThenSafeBackend()
    session = engine.run(
        "rows", str(space), config={"max_iterations": 1, "max_sections": 1, "max_retries": 2}
    )
    assert session.record.status == "COMPLETE", session.record.error
    events = [e["event"] for e in session.record.events]
    assert "iteration.refused" in events
    assert any(
        it.observation.result.get("rows") == 8
        for it in session.record.plan.sections[0].iterations
    )


def test_a_hanging_backend_cannot_stall_the_session(engine: ResearchEngine, space: Path):
    """A provider that never answers degrades to the offline path on a deadline."""
    import time as _time

    class HangingBackend:
        def chat(self, messages, tools=None):
            _time.sleep(30)
            return {"content": "too late", "tool_calls": []}

    engine.backend = HangingBackend()
    started = _time.monotonic()
    session = engine.run(
        "rows",
        str(space),
        config={"max_iterations": 1, "max_sections": 1, "step_timeout_seconds": 1},
    )
    elapsed = _time.monotonic() - started
    assert session.record.status in ("COMPLETE", "FAILED")
    assert elapsed < 60, f"the session took {elapsed:.0f}s; the watchdog did not fire"


def test_the_global_time_budget_is_enforced(engine: ResearchEngine, space: Path):
    session = engine.create(
        "rows",
        str(space),
        config={"max_time_seconds": 5, "max_iterations": 10, "max_sections": 6},
    )
    session.plan()
    session.approve()
    import time as _time

    started = _time.monotonic()
    session.start()
    assert _time.monotonic() - started < 180
    assert session.record.status in ("COMPLETE", "FAILED")
