"""Domain models and data structures for Autonomous Multi-Agent Debate & Fact-Checking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any


class DebateRole(str, Enum):
    """Roles within the debate panel."""

    PROPONENT = "proponent"
    OPPONENT = "opponent"
    FACT_CHECKER = "fact_checker"
    SYNTHESIZER = "synthesizer"


class VerificationStatus(str, Enum):
    """Verification outcome for an atomic factual claim."""

    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    UNVERIFIED = "unverified"
    PARTIAL = "partial"


class DebateStatus(str, Enum):
    """Status lifecycle of a debate session."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CONVERGED = "converged"
    DEADLOCKED = "deadlocked"
    RESOLVED = "resolved"


@dataclass(slots=True)
class FactClaim:
    """An atomic factual claim extracted from arguments."""

    claim_id: str
    statement: str
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    confidence_score: float = 0.5
    evidence_sources: list[str] = field(default_factory=list)
    fallacies_detected: list[str] = field(default_factory=list)
    verified_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize claim to dictionary."""
        return {
            "claim_id": self.claim_id,
            "statement": self.statement,
            "verification_status": self.verification_status.value,
            "confidence_score": round(self.confidence_score, 2),
            "evidence_sources": self.evidence_sources,
            "fallacies_detected": self.fallacies_detected,
            "verified_at": round(self.verified_at, 2),
        }


@dataclass(slots=True)
class DebateTurn:
    """A single speech or argumentation turn in the debate."""

    turn_number: int
    role: DebateRole
    speaker_name: str
    arguments: str
    claims: list[FactClaim] = field(default_factory=list)
    counter_points: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize debate turn to dictionary."""
        return {
            "turn_number": self.turn_number,
            "role": self.role.value,
            "speaker_name": self.speaker_name,
            "arguments": self.arguments,
            "claims": [c.to_dict() for c in self.claims],
            "counter_points": self.counter_points,
            "timestamp": round(self.timestamp, 2),
        }


@dataclass(slots=True)
class DebateSession:
    """Container tracking the multi-agent debate lifecycle and Delphi consensus."""

    debate_id: str
    topic: str
    status: DebateStatus = DebateStatus.OPEN
    turns: list[DebateTurn] = field(default_factory=list)
    claims: dict[str, FactClaim] = field(default_factory=dict)
    consensus_summary: str = ""
    confidence_score: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize debate session to dictionary."""
        return {
            "debate_id": self.debate_id,
            "topic": self.topic,
            "status": self.status.value,
            "total_turns": len(self.turns),
            "total_claims": len(self.claims),
            "consensus_summary": self.consensus_summary,
            "confidence_score": round(self.confidence_score, 2),
            "created_at": round(self.created_at, 2),
            "updated_at": round(self.updated_at, 2),
        }
