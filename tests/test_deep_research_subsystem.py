"""Unit and integration tests for Autonomous Deep Research and Synthesis Subsystem."""

from __future__ import annotations

from pathlib import Path
import tempfile
import pytest

from dream.research import (
    DeepResearchEngine,
    MultiSourceCollector,
    ResearchPlanner,
    ResearchStatus,
    ResearchSynthesizer,
    SourceCredibility,
    handle_research_slash_command,
    research_add_source,
    research_export_report,
    research_get_status,
    research_list_sessions,
    research_plan_investigation,
    research_run_autonomous,
    research_synthesize_report,
    reset_global_research_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_research_engine() -> None:
    reset_global_research_engine()
    yield
    reset_global_research_engine()


def test_toolset_includes_research() -> None:
    """Verify research toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("research")
    assert ts is not None
    assert "research_plan_investigation" in ts.tools
    assert "research_synthesize_report" in ts.tools
    assert "research_run_autonomous" in ts.tools
    assert "research" in BUILTIN_TOOLSETS


def test_research_planner_decomposition() -> None:
    """Verify research topic decomposition and query generation."""
    planner = ResearchPlanner()
    plan = planner.create_plan(
        topic="Post-Quantum Cryptography Algorithms",
        target_depth=3,
        max_sources=12,
        focus_areas=["Kyber", "Dilithium"],
    )
    assert plan.topic == "Post-Quantum Cryptography Algorithms"
    assert len(plan.hypotheses) >= 3
    assert len(plan.sub_questions) >= 3
    assert plan.status == ResearchStatus.PLANNING

    queries = planner.generate_search_queries(plan.topic, plan.sub_questions)
    assert len(queries) >= 3
    langs = {q["language"] for q in queries}
    assert "fa" in langs
    assert "en" in langs


def test_multisource_collector_credibility_and_dedup() -> None:
    """Verify source credibility scoring and deduplication."""
    collector = MultiSourceCollector()

    # Academic domain
    cred_acad, score_acad = collector.assess_credibility("https://arxiv.org/abs/2401.12345")
    assert cred_acad == SourceCredibility.PRIMARY_ACADEMIC
    assert score_acad >= 0.95

    # Official doc domain
    cred_off, score_off = collector.assess_credibility("https://github.com/NousResearch/hermes-agent")
    assert cred_off == SourceCredibility.OFFICIAL_DOCUMENTATION
    assert score_off >= 0.90

    # Forum domain
    cred_forum, score_forum = collector.assess_credibility("https://reddit.com/r/MachineLearning")
    assert cred_forum == SourceCredibility.COMMUNITY_FORUM
    assert score_forum <= 0.70

    # Source creation and deduplication
    s1 = collector.create_source(
        url="https://arxiv.org/abs/2401.12345",
        title="Paper A",
        snippet="Factual finding on cryptographic security bounds.",
    )
    s2 = collector.create_source(
        url="https://arxiv.org/abs/2401.12345/",
        title="Paper A duplicate",
        snippet="Duplicate text.",
    )
    s3 = collector.create_source(
        url="https://nature.com/articles/pqc",
        title="Nature Review",
        snippet="Comprehensive analysis of quantum-resistant algorithms.",
    )

    deduped = collector.deduplicate_sources([s1, s2, s3])
    assert len(deduped) == 2
    assert deduped[0].credibility_score >= deduped[1].credibility_score


def test_synthesizer_and_report_generation() -> None:
    """Verify multi-source synthesis, inline citations, and markdown rendering."""
    planner = ResearchPlanner()
    collector = MultiSourceCollector()
    synthesizer = ResearchSynthesizer()

    plan = planner.create_plan(topic="Autonomous Agent Architectures")
    src1 = collector.create_source(
        url="https://arxiv.org/abs/2608.12345",
        title="Deep Agentic Reasoning",
        snippet="Autonomous agents achieve 95% task completion with tool use.",
    )
    src2 = collector.create_source(
        url="https://github.com/NousResearch/hermes-agent",
        title="Hermes Documentation",
        snippet="Stable seams enable robust tool invocation across multi-turn sessions.",
    )

    findings = synthesizer.synthesize_findings(plan, [src1, src2])
    assert len(findings) == len(plan.sub_questions)

    report = synthesizer.generate_report(plan, [src1, src2], findings)
    assert report.topic == "Autonomous Agent Architectures"
    assert len(report.bibliography) == 2
    assert len(report.executive_summary_fa) > 0
    assert len(report.detailed_sections) > 0
    assert "# \U0001f50e" in report.markdown_content
    assert "[1]" in report.markdown_content


def test_deep_research_engine_workflow() -> None:
    """Verify autonomous end-to-end research flow and session management."""
    engine = DeepResearchEngine()

    plan, report = engine.run_autonomous_research(
        topic="Neural Network Interpretability",
        target_depth=2,
        max_sources=6,
    )
    assert plan.status == ResearchStatus.COMPLETED
    assert report.total_sources_analyzed >= 3
    assert len(report.bibliography) >= 3

    # Check session query
    session = engine.get_session(plan.session_id)
    assert session is not None
    assert session["plan"]["topic"] == "Neural Network Interpretability"

    # Export report with path safety
    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "report.md"
        saved = engine.export_report(plan.session_id, str(out_file))
        assert Path(saved).exists()
        assert "Executive Summary" in Path(saved).read_text(encoding="utf-8")

    # Sensitive path security refusal
    with pytest.raises(PermissionError):
        engine.export_report(plan.session_id, "/etc/shadow")


def test_research_tools_and_slash_commands() -> None:
    """Verify LLM tool wrappers and /research CLI slash command handlers."""
    # Tool: run autonomous
    auto_res = research_run_autonomous(topic="Quantum Machine Learning")
    assert auto_res["success"] is True
    sid = auto_res["session_id"]

    # Tool: status
    status_res = research_get_status(sid)
    assert status_res["success"] is True
    assert status_res["plan"]["status"] == "completed"

    # Tool: list
    list_res = research_list_sessions()
    assert list_res["success"] is True
    assert len(list_res["sessions"]) >= 1

    # Slash: list
    list_msg = handle_research_slash_command("/research list")
    assert "Quantum Machine Learning" in list_msg

    # Slash: status
    status_msg = handle_research_slash_command(f"/research status {sid}")
    assert "Quantum Machine Learning" in status_msg

    # Slash: start
    start_msg = handle_research_slash_command("/research start Synthetic Biology")
    assert "\u062a\u06a9\u0645\u06cc\u0644 \u0634\u062f" in start_msg
