"""Delphi consensus moderator and argumentation synthesizer."""

from __future__ import annotations

import time

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
            return DebateStatus.OPEN, 0.5, "هنوز ادعای قابل بررسی ثبت نشده است."

        total_claims = len(session.claims)
        verified_count = sum(
            1
            for c in session.claims.values()
            if c.verification_status == VerificationStatus.VERIFIED
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
            "🏛 گزارش اجماع دلفی (Delphi Consensus Report):\n"
            f"- موضوع: {session.topic}\n"
            f"- تعداد نوبت‌های مناظره: {len(session.turns)}\n"
            f"- تعداد کل گزاره‌ها (Claims): {total_claims}\n"
            f"- گزاره‌های تاییدشده: {verified_count}\n"
            f"- مغالطات شناسایی‌شده: {fallacy_count}\n"
            f"- ضریب اطمینان نهایی: {consensus_score:.2f}\n"
            f"- وضعیت: {status.value}"
        )

        session.status = status
        session.confidence_score = consensus_score
        session.consensus_summary = summary
        session.updated_at = time.time()
        return status, consensus_score, summary
