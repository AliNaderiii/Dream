"""Debate Engine Coordinator for autonomous deliberation and multi-agent consensus."""

from __future__ import annotations

import time
from typing import Any
import uuid

from dream.debate.factchecker import FactChecker
from dream.debate.moderator import DebateModerator
from dream.debate.types import (
    DebateRole,
    DebateSession,
    DebateStatus,
    DebateTurn,
    FactClaim,
)


class DebateEngine:
    """Coordinates multi-perspective deliberations, argument verification, and consensus synthesis."""

    def __init__(
        self,
        moderator: DebateModerator | None = None,
        fact_checker: FactChecker | None = None,
    ) -> None:
        self.fact_checker = fact_checker or FactChecker()
        self.moderator = moderator or DebateModerator(fact_checker=self.fact_checker)
        self._sessions: dict[str, DebateSession] = {}
        self._active_debate_id: str | None = None

    def create_debate(self, topic: str) -> DebateSession:
        """Initialize a new multi-agent debate session."""
        did = f"deb-{uuid.uuid4().hex[:6]}"
        now = time.time()
        session = DebateSession(
            debate_id=did,
            topic=topic,
            status=DebateStatus.OPEN,
            created_at=now,
            updated_at=now,
        )
        self._sessions[did] = session
        self._active_debate_id = did
        return session

    def add_argument(
        self,
        debate_id: str,
        role: str | DebateRole,
        speaker_name: str,
        argument: str,
        evidence: str = "",
    ) -> DebateTurn:
        """Add an argument turn to an ongoing debate session."""
        session = self._sessions.get(debate_id)
        if not session:
            raise KeyError(f"Debate session '{debate_id}' not found.")

        if isinstance(role, str):
            try:
                r_enum = DebateRole(role.lower())
            except ValueError:
                r_enum = DebateRole.PROPONENT
        else:
            r_enum = role

        turn = self.moderator.process_turn(
            session=session,
            role=r_enum,
            speaker_name=speaker_name,
            argument_text=argument,
            evidence=evidence,
        )
        return turn

    def run_autonomous_debate(
        self,
        topic: str,
        proponent_arg: str,
        opponent_arg: str,
        evidence: str = "",
    ) -> tuple[DebateSession, str]:
        """Execute a complete autonomous debate round between proponent and opponent."""
        session = self.create_debate(topic)

        # Turn 1: Proponent
        self.add_argument(
            debate_id=session.debate_id,
            role=DebateRole.PROPONENT,
            speaker_name="Proponent Agent",
            argument=proponent_arg,
            evidence=evidence,
        )

        # Turn 2: Opponent
        self.add_argument(
            debate_id=session.debate_id,
            role=DebateRole.OPPONENT,
            speaker_name="Skeptic Agent",
            argument=opponent_arg,
            evidence=evidence,
        )

        # Evaluate consensus
        _, _, summary = self.moderator.evaluate_consensus(session)
        return session, summary

    def verify_statement(
        self,
        statement: str,
        evidence: str = "",
    ) -> FactClaim:
        """Verify an isolated factual statement and detect logical fallacies."""
        claims = self.fact_checker.extract_claims(statement)
        if not claims:
            # Fallback single claim
            cid = f"clm-{uuid.uuid4().hex[:6]}"
            claim = FactClaim(
                claim_id=cid,
                statement=statement,
                fallacies_detected=self.fact_checker.detect_fallacies(statement),
            )
        else:
            claim = claims[0]

        return self.fact_checker.verify_claim_against_evidence(claim, evidence=evidence)

    def reach_consensus(self, debate_id: str) -> dict[str, Any]:
        """Trigger Delphi consensus calculation for a session."""
        session = self._sessions.get(debate_id)
        if not session:
            raise KeyError(f"Debate session '{debate_id}' not found.")

        status, score, summary = self.moderator.evaluate_consensus(session)
        return {
            "debate_id": debate_id,
            "status": status.value,
            "confidence_score": score,
            "summary": summary,
        }

    def get_debate(self, debate_id: str) -> DebateSession | None:
        """Retrieve debate session by ID."""
        return self._sessions.get(debate_id)

    def list_debates(self) -> list[DebateSession]:
        """List all debate sessions."""
        return list(self._sessions.values())

    def reset(self) -> None:
        """Clear all debate sessions."""
        self._sessions.clear()
        self._active_debate_id = None
