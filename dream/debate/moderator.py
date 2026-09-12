"""Delphi consensus moderator and argumentation synthesizer."""

from __future__ import annotations

import time
from typing import Any

from dream.debate.factchecker import FactChecker
from dream.debate.types import (
    DebateRole,
    DebateSession,
    DebateStatus,
    DebateTurn,
    VerificationStatus,
)


class DebateModerator:
    """Moderates debates, computes Delphi agreement scores, and synthesizes resolutions."""

    def __init__(self, fact_checker: FactChecker | None = None) -> None:
        self.fact_checker = fact_checker or FactChecker()

    def process_turn(
        self,
        session: DebateSession,
        role: DebateRole,
        speaker_name: str,
        argument_text: str,
        counter_points: list[str] | None = None,
        evidence: str = "",
    ) -> DebateTurn:
        """Process an argumentation turn, extract claims, and verify facts."""
        claims = self.fact_checker.extract_claims(argument_text)
        for clm in claims:
            if evidence:
                self.fact_checker.verify_claim_against_evidence(clm, evidence=evidence)
            session.claims[clm.claim_id] = clm

        turn_num = len(session.turns) + 1
        turn = DebateTurn(
            turn_number=turn_num,
            role=role,
            speaker_name=speaker_name,
            arguments=argument_text,
            claims=claims,
            counter_points=counter_points or [],
        )
        session.turns.append(turn)
        session.updated_at = time.time()
        return turn

    def evaluate_consensus(self, session: DebateSession) -> tuple[DebateStatus, float, str]:
        """Compute consensus score across all debate turns and claims."""
        if not session.claims:
            return DebateStatus.OPEN, 0.5, "\u0647\u0646\u0648\u0632 \u0627\u062f\u0639\u0627\u06cc \u0642\u0627\u0628\u0644 \u0628\u0631\u0631\u0633\u06cc \u062b\u0628\u062a \u0646\u0634\u062f\u0647 \u0627\u0633\u062a."

        total_claims = len(session.claims)
        verified_count = sum(
            1 for c in session.claims.values() if c.verification_status == VerificationStatus.VERIFIED
        )
        fallacy_count = sum(len(c.fallacies_detected) for c in session.claims.values())

        # Base confidence calculation
        base_score = verified_count / total_claims if total_claims > 0 else 0.5
        fallacy_penalty = min(0.3, fallacy_count * 0.05)
        consensus_score = round(max(0.0, min(1.0, base_score - fallacy_penalty)), 2)

        # Delphi consensus state
        if len(session.turns) >= 2 and consensus_score >= 0.65:
            status = DebateStatus.CONVERGED
        elif len(session.turns) >= 4 and consensus_score < 0.4:
            status = DebateStatus.DEADLOCKED
        else:
            status = DebateStatus.IN_PROGRESS

        # Generate summary synthesis
        summary = (
            f"\U0001f3db \u06af\u0632\u0627\u0631\u0634 \u0627\u062c\u0645\u0627\u0639 \u062f\u0644\u0641\u06cc (Delphi Consensus Report):\n"
            f"- \u0645\u0648\u0636\u0648\u0639: {session.topic}\n"
            f"- \u062a\u0639\u062f\u0627\u062f \u0646\u0648\u0628\u062a\u200c\u0647\u0627\u06cc \u0645\u0646\u0627\u0638\u0631\u0647: {len(session.turns)}\n"
            f"- \u062a\u0639\u062f\u0627\u062f \u06a9\u0644 \u06af\u0632\u0627\u0631\u0647\u200c\u0647\u0627 (Claims): {total_claims}\n"
            f"- \u06af\u0632\u0627\u0631\u0647\u200c\u0647\u0627\u06cc \u062a\u0627\u06cc\u06cc\u062f\u0634\u062f\u0647: {verified_count}\n"
            f"- \u0645\u063a\u0627\u0644\u0637\u0627\u062a \u0634\u0646\u0627\u0633\u0627\u06cc\u06cc\u200c\u0634\u062f\u0647: {fallacy_count}\n"
            f"- \u0636\u0631\u06cc\u0628 \u0627\u0637\u0645\u06cc\u0646\u0627\u0646 \u0646\u0647\u0627\u06cc\u06cc: {consensus_score:.2f}\n"
            f"- \u0648\u0636\u0639\u06cc\u062a: {status.value}"
        )

        session.status = status
        session.confidence_score = consensus_score
        session.consensus_summary = summary
        session.updated_at = time.time()
        return status, consensus_score, summary
