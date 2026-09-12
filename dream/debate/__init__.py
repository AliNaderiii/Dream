"""Multi-Agent Debate, Delphi Consensus & Verifiable Fact-Checking Subsystem."""

from __future__ import annotations

from dream.debate.engine import DebateEngine
from dream.debate.factchecker import FactChecker
from dream.debate.moderator import DebateModerator
from dream.debate.slash import handle_debate_slash_command
from dream.debate.tools import (
    debate_add_turn,
    debate_create_session,
    debate_list_sessions,
    debate_reach_consensus,
    debate_reset_all,
    debate_run_autonomous,
    debate_verify_statement,
    get_debate_tools,
    get_global_debate_engine,
    reset_global_debate_engine,
)
from dream.debate.types import (
    DebateRole,
    DebateSession,
    DebateStatus,
    DebateTurn,
    FactClaim,
    VerificationStatus,
)

# Auto-register debate toolset in registry
try:
    from dream.tools.toolsets import Toolset, register_toolset

    register_toolset(
        Toolset(
            name="debate",
            description=(
                "Multi-agent debate rounds, Delphi consensus evaluation, "
                "and fact verification."
            ),
            tools=[
                "debate_create_session",
                "debate_add_turn",
                "debate_run_autonomous",
                "debate_verify_statement",
                "debate_reach_consensus",
                "debate_list_sessions",
                "debate_reset_all",
            ],
            metadata={"category": "debate", "builtin": True},
        )
    )
except Exception:
    pass

__all__ = [
    "DebateEngine",
    "DebateModerator",
    "DebateRole",
    "DebateSession",
    "DebateStatus",
    "DebateTurn",
    "FactChecker",
    "FactClaim",
    "VerificationStatus",
    "debate_add_turn",
    "debate_create_session",
    "debate_list_sessions",
    "debate_reach_consensus",
    "debate_reset_all",
    "debate_run_autonomous",
    "debate_verify_statement",
    "get_debate_tools",
    "get_global_debate_engine",
    "handle_debate_slash_command",
    "reset_global_debate_engine",
]
