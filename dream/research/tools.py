"""LLM Tool bindings for Autonomous Deep Research and Multi-Source Synthesis."""

from __future__ import annotations

from typing import Any

from dream.research.engine import DeepResearchEngine
from dream.security.pathsafety import is_sensitive_path

_GLOBAL_RESEARCH_ENGINE: DeepResearchEngine | None = None


def get_global_research_engine() -> DeepResearchEngine:
    """Get or initialize singleton DeepResearchEngine."""
    global _GLOBAL_RESEARCH_ENGINE
    if _GLOBAL_RESEARCH_ENGINE is None:
        _GLOBAL_RESEARCH_ENGINE = DeepResearchEngine()
    return _GLOBAL_RESEARCH_ENGINE


def reset_global_research_engine() -> None:
    """Reset DeepResearchEngine singleton instance."""
    global _GLOBAL_RESEARCH_ENGINE
    _GLOBAL_RESEARCH_ENGINE = None


def research_plan_investigation(
    topic: str,
    depth: int = 2,
    max_sources: int = 15,
    focus_areas: list[str] | None = None,
) -> dict[str, Any]:
    """Decompose topic into hypotheses, sub-questions, and multi-lingual search queries."""
    engine = get_global_research_engine()
    plan = engine.plan_investigation(
        topic=topic,
        target_depth=depth,
        max_sources=max_sources,
        focus_areas=focus_areas,
    )
    return {"success": True, "plan": plan.to_dict()}


def research_add_source(
    session_id: str,
    url: str,
    title: str,
    snippet: str,
    extracted_claims: list[str] | None = None,
) -> dict[str, Any]:
    """Ingest external evidence into a research investigation session."""
    engine = get_global_research_engine()
    try:
        src = engine.add_evidence_source(
            session_id=session_id,
            url=url,
            title=title,
            snippet=snippet,
            extracted_claims=extracted_claims,
        )
        return {"success": True, "source": src.to_dict()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def research_synthesize_report(session_id: str) -> dict[str, Any]:
    """Cross-verify findings and synthesize full markdown report for a research session."""
    engine = get_global_research_engine()
    try:
        report = engine.synthesize_report(session_id)
        return {"success": True, "report": report.to_dict()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def research_run_autonomous(
    topic: str,
    depth: int = 2,
    max_sources: int = 10,
    focus_areas: list[str] | None = None,
) -> dict[str, Any]:
    """Run full autonomous deep research lifecycle on a topic and return structured report."""
    engine = get_global_research_engine()
    plan, report = engine.run_autonomous_research(
        topic=topic,
        target_depth=depth,
        max_sources=max_sources,
        focus_areas=focus_areas,
    )
    return {
        "success": True,
        "session_id": plan.session_id,
        "plan": plan.to_dict(),
        "report": report.to_dict(),
    }


def research_export_report(
    session_id: str,
    file_path: str,
) -> dict[str, Any]:
    """Export finalized research report to disk with L4 path security check."""
    if is_sensitive_path(file_path):
        return {
            "success": False,
            "error": f"Permission denied: '{file_path}' is a sensitive system path.",
        }

    engine = get_global_research_engine()
    try:
        saved_path = engine.export_report(session_id, file_path)
        return {"success": True, "file_path": saved_path}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def research_get_status(session_id: str) -> dict[str, Any]:
    """Get active status, collected sources count, and report progress of research session."""
    engine = get_global_research_engine()
    session = engine.get_session(session_id)
    if session:
        return {"success": True, **session}
    return {"success": False, "error": f"Session '{session_id}' not found."}


def research_list_sessions() -> dict[str, Any]:
    """List all registered deep research investigation sessions."""
    engine = get_global_research_engine()
    sessions = engine.list_sessions()
    return {"success": True, "sessions": sessions}


def get_research_tools() -> list[Any]:
    """Return Deep Research tool functions for agent registration."""
    return [
        research_plan_investigation,
        research_add_source,
        research_synthesize_report,
        research_run_autonomous,
        research_export_report,
        research_get_status,
        research_list_sessions,
    ]
