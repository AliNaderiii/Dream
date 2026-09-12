"""LLM tool bindings for Autonomous Debate & Fact-Checking Subsystem."""

from __future__ import annotations

from typing import Any

from dream.debate.engine import DebateEngine

_GLOBAL_DEBATE_ENGINE: DebateEngine | None = None


def get_global_debate_engine() -> DebateEngine:
    """Get or initialize singleton DebateEngine."""
    global _GLOBAL_DEBATE_ENGINE
    if _GLOBAL_DEBATE_ENGINE is None:
        _GLOBAL_DEBATE_ENGINE = DebateEngine()
    return _GLOBAL_DEBATE_ENGINE


def reset_global_debate_engine() -> None:
    """Reset singleton DebateEngine."""
    global _GLOBAL_DEBATE_ENGINE
    _GLOBAL_DEBATE_ENGINE = None


def debate_create_session(topic: str) -> dict[str, Any]:
    """Create a new multi-agent debate session around a topic."""
    engine = get_global_debate_engine()
    session = engine.create_debate(topic)
    return {
        "success": True,
        "session": session.to_dict(),
        "message": f"\u0646\u0634\u0633\u062a \u0645\u0646\u0627\u0638\u0631\u0647 '{topic}' \u0627\u06cc\u062c\u0627\u062f \u0634\u062f.",
    }


def debate_add_turn(
    debate_id: str,
    role: str,
    speaker_name: str,
    argument: str,
    evidence: str = "",
) -> dict[str, Any]:
    """Submit an argumentation turn from a specific debate role (proponent/opponent)."""
    engine = get_global_debate_engine()
    try:
        turn = engine.add_argument(
            debate_id=debate_id,
            role=role,
            speaker_name=speaker_name,
            argument=argument,
            evidence=evidence,
        )
        return {"success": True, "turn": turn.to_dict()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def debate_run_autonomous(
    topic: str,
    proponent_arg: str,
    opponent_arg: str,
    evidence: str = "",
) -> dict[str, Any]:
    """Run an automated multi-perspective debate round and synthesize Delphi consensus."""
    engine = get_global_debate_engine()
    try:
        session, summary = engine.run_autonomous_debate(
            topic=topic,
            proponent_arg=proponent_arg,
            opponent_arg=opponent_arg,
            evidence=evidence,
        )
        return {
            "success": True,
            "session": session.to_dict(),
            "consensus_summary": summary,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def debate_verify_statement(
    statement: str,
    evidence: str = "",
) -> dict[str, Any]:
    """Verify a factual claim, evaluate evidence overlap, and detect logical fallacies."""
    engine = get_global_debate_engine()
    claim = engine.verify_statement(statement=statement, evidence=evidence)
    return {
        "success": True,
        "claim": claim.to_dict(),
        "fallacies": claim.fallacies_detected,
        "verification_status": claim.verification_status.value,
        "confidence": claim.confidence_score,
    }


def debate_reach_consensus(debate_id: str) -> dict[str, Any]:
    """Synthesize final consensus and confidence score for a debate session."""
    engine = get_global_debate_engine()
    try:
        res = engine.reach_consensus(debate_id)
        return {"success": True, **res}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def debate_list_sessions() -> dict[str, Any]:
    """List all registered debate sessions."""
    engine = get_global_debate_engine()
    sessions = engine.list_debates()
    return {"success": True, "debates": [s.to_dict() for s in sessions]}


def debate_reset_all() -> dict[str, Any]:
    """Reset debate engine and clear session history."""
    engine = get_global_debate_engine()
    engine.reset()
    return {"success": True, "message": "\u062a\u0645\u0627\u0645 \u0646\u0634\u0633\u062a\u200c\u0647\u0627\u06cc \u0645\u0646\u0627\u0638\u0631\u0647 \u067e\u0627\u06a9\u0633\u0627\u0632\u06cc \u0634\u062f\u0646\u062f."}


def get_debate_tools() -> list[Any]:
    """Return debate tool functions for agent registration."""
    return [
        debate_create_session,
        debate_add_turn,
        debate_run_autonomous,
        debate_verify_statement,
        debate_reach_consensus,
        debate_list_sessions,
        debate_reset_all,
    ]
