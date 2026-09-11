"""Autonomous Deep Research, Multi-Source Fact Gathering, and Intelligence Synthesis Subsystem."""

from __future__ import annotations

from dream.research.collector import MultiSourceCollector
from dream.research.engine import DeepResearchEngine
from dream.research.planner import ResearchPlanner
from dream.research.slash import handle_research_slash_command
from dream.research.synthesizer import ResearchSynthesizer
from dream.research.tools import (
    get_global_research_engine,
    get_research_tools,
    research_add_source,
    research_export_report,
    research_get_status,
    research_list_sessions,
    research_plan_investigation,
    research_run_autonomous,
    research_synthesize_report,
    reset_global_research_engine,
)
from dream.research.types import (
    ResearchFinding,
    ResearchPlan,
    ResearchReport,
    ResearchSource,
    ResearchStatus,
    SourceCitation,
    SourceCredibility,
)

# Register toolset if toolset registry is present
try:
    from dream.tools.toolsets import Toolset, register_toolset

    register_toolset(
        Toolset(
            name="research",
            description="Autonomous deep research, evidence collection, and multi-source synthesis.",
            tools=[
                "research_plan_investigation",
                "research_add_source",
                "research_synthesize_report",
                "research_run_autonomous",
                "research_export_report",
                "research_get_status",
                "research_list_sessions",
            ],
            metadata={"category": "research", "builtin": True},
        )
    )
except Exception:
    pass

__all__ = [
    "DeepResearchEngine",
    "MultiSourceCollector",
    "ResearchFinding",
    "ResearchPlan",
    "ResearchPlanner",
    "ResearchReport",
    "ResearchSource",
    "ResearchStatus",
    "ResearchSynthesizer",
    "SourceCitation",
    "SourceCredibility",
    "get_global_research_engine",
    "get_research_tools",
    "handle_research_slash_command",
    "research_add_source",
    "research_export_report",
    "research_get_status",
    "research_list_sessions",
    "research_plan_investigation",
    "research_run_autonomous",
    "research_synthesize_report",
    "reset_global_research_engine",
]
