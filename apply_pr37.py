#!/usr/bin/env python3
"""Phase 34: Autonomous Multi-Agent Debate, Delphi Consensus & Verifiable Fact-Checking Subsystem.

Applies all modules for Phase 34:
- dream/debate/types.py
- dream/debate/factchecker.py
- dream/debate/moderator.py
- dream/debate/engine.py
- dream/debate/tools.py
- dream/debate/slash.py
- dream/debate/__init__.py
- dream/tools/toolsets.py (registered debate toolset)
- tests/test_debate_and_factchecking.py
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

FILES: dict[str, str] = {
    "dream/debate/types.py": r'''"""Domain models and data structures for Autonomous Multi-Agent Debate & Fact-Checking."""

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
''',
    "dream/debate/factchecker.py": r'''"""Automated claim extraction, logical fallacy detection, and evidence verification."""

from __future__ import annotations

import re
import time
from typing import Any
import uuid

from dream.debate.types import FactClaim, VerificationStatus


class FactChecker:
    """Extracts statements, checks for logical fallacies, and verifies grounded truth."""

    FALLACY_PATTERNS = [
        (
            r"(یا\s+باید\s+.*\s+یا\s+نابودی|either\s+.*\s+or\s+total\s+ruin)",
            "\u0645\u063a\u0627\u0644\u0637\u0647 \u062f\u0648\u0631\u0627\u0647\u06cc \u06a9\u0627\u0632\u0628 (False Dilemma)",
        ),
        (
            r"(همه\s+می\u200cدانند|everyone\s+knows|بدون\s+شک\s+همه)",
            "\u0645\u063a\u0627\u0644\u0637\u0647 \u062a\u0639\u0645\u06cc\u0645 \u0634\u062a\u0627\u0628\u200c\u0632\u062f\u0647 (Hasty Generalization)",
        ),
        (
            r"(تو\s+نمی\u200cفهمی|شما\s+صلاحیت\s+ندارید|you\s+are\s+ignorant)",
            "\u0645\u063a\u0627\u0644\u0637\u0647 \u062d\u0645\u0644\u0647 \u0628\u0647 \u0634\u062e\u0635 (Ad Hominem)",
        ),
        (
            r"(چون\s+من\s+می\u200cگویم\s+پس\s+درست\s+است|because\s+i\s+said\s+so)",
            "\u0645\u063a\u0627\u0644\u0637\u0647 \u0627\u0633\u062a\u062f\u0644\u0627\u0644 \u062f\u0627\u06cc\u0631\u0647\u200c\u0627\u06cc (Circular Reasoning)",
        ),
    ]

    def detect_fallacies(self, text: str) -> list[str]:
        """Detect known rhetorical fallacies in argumentation text."""
        detected: list[str] = []
        for pat, name in self.FALLACY_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                detected.append(name)
        return detected

    def extract_claims(self, text: str) -> list[FactClaim]:
        """Decompose an argument into atomic factual statements."""
        raw_sentences = [
            s.strip()
            for s in re.split(r"[\.\n!\?\u061f\u06d4]+", text)
            if len(s.strip()) > 8
        ]

        claims: list[FactClaim] = []
        for sent in raw_sentences:
            cid = f"clm-{uuid.uuid4().hex[:6]}"
            fallacies = self.detect_fallacies(sent)
            claims.append(
                FactClaim(
                    claim_id=cid,
                    statement=sent,
                    verification_status=VerificationStatus.UNVERIFIED,
                    confidence_score=0.5,
                    fallacies_detected=fallacies,
                )
            )
        return claims

    def verify_claim_against_evidence(
        self,
        claim: FactClaim,
        evidence: str = "",
    ) -> FactClaim:
        """Verify claim against provided ground-truth evidence text."""
        if not evidence.strip():
            claim.verification_status = VerificationStatus.UNVERIFIED
            claim.confidence_score = 0.5
            return claim

        claim_words = set(re.findall(r"\w+", claim.statement.lower()))
        evidence_words = set(re.findall(r"\w+", evidence.lower()))

        if not claim_words:
            claim.verification_status = VerificationStatus.UNVERIFIED
            return claim

        overlap = len(claim_words.intersection(evidence_words))
        ratio = overlap / len(claim_words)

        # Check contradiction negation keywords
        contradiction_markers = ["غلط", "نادرست", "رد شده", "false", "incorrect", "refuted", "disproven"]
        has_contradiction = any(m in evidence.lower() for m in contradiction_markers) and ratio > 0.3

        if has_contradiction:
            claim.verification_status = VerificationStatus.CONTRADICTED
            claim.confidence_score = round(max(0.1, 1.0 - ratio), 2)
            claim.evidence_sources.append(evidence[:120])
        elif ratio >= 0.4:
            claim.verification_status = VerificationStatus.VERIFIED
            claim.confidence_score = round(min(0.95, 0.5 + (ratio * 0.5)), 2)
            claim.evidence_sources.append(evidence[:120])
        elif ratio >= 0.2:
            claim.verification_status = VerificationStatus.PARTIAL
            claim.confidence_score = round(ratio, 2)
            claim.evidence_sources.append(evidence[:120])
        else:
            claim.verification_status = VerificationStatus.UNVERIFIED
            claim.confidence_score = 0.4

        claim.verified_at = time.time()
        return claim
''',
    "dream/debate/moderator.py": r'''"""Delphi consensus moderator and argumentation synthesizer."""

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
''',
    "dream/debate/engine.py": r'''"""Debate Engine Coordinator for autonomous deliberation and multi-agent consensus."""

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
''',
    "dream/debate/tools.py": r'''"""LLM tool bindings for Autonomous Debate & Fact-Checking Subsystem."""

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
''',
    "dream/debate/slash.py": r'''"""CLI and slash command handlers for Multi-Agent Debate & Fact-Checking."""

from __future__ import annotations

from typing import Any

from dream.debate.tools import (
    debate_create_session,
    debate_list_sessions,
    debate_reach_consensus,
    debate_reset_all,
    debate_run_autonomous,
    debate_verify_statement,
)


def handle_debate_slash_command(command_str: str) -> str:
    """Handle /debate and /verify slash commands for CLI and REPL.

    Usage:
        /debate <topic>
        /debate list
        /debate status <debate_id>
        /debate reset
        /verify <statement>
    """
    cmd = command_str.strip()

    if cmd.startswith("/verify"):
        statement = cmd[len("/verify") :].strip()
        if not statement:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u06af\u0632\u0627\u0631\u0647 \u06cc\u0627 \u0627\u062f\u0639\u0627 \u0631\u0627 \u0628\u0631\u0627\u06cc \u0631\u0627\u0633\u062a\u06cc\u200c\u0622\u0632\u0645\u0627\u06cc\u06cc \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = debate_verify_statement(statement)
        status = res.get("verification_status", "unverified")
        conf = res.get("confidence", 0.0)
        fallacies = res.get("fallacies", [])

        out = [
            f"\U0001f50e \u0646\u062a\u06cc\u062c\u0647 \u0627\u0631\u0632\u06cc\u0627\u0628\u06cc \u06af\u0632\u0627\u0631\u0647:",
            f"- \u0648\u0636\u0639\u06cc\u062a: `{status}`",
            f"- \u0636\u0631\u06cc\u0628 \u0627\u0637\u0645\u06cc\u0646\u0627\u0646: {conf:.2f}",
        ]
        if fallacies:
            out.append(f"- \u26a0\ufe0f \u0645\u063a\u0627\u0644\u0637\u0627\u062a \u0634\u0646\u0627\u0633\u0627\u06cc\u06cc\u200c\u0634\u062f\u0647: {', '.join(fallacies)}")
        else:
            out.append("- \u2705 \u0647\u06cc\u0686 \u0645\u063a\u0627\u0644\u0637\u0647 \u0645\u0646\u0637\u0642\u06cc \u0634\u0646\u0627\u0633\u0627\u06cc\u06cc \u0646\u0634\u062f.")
        return "\n".join(out)

    if not cmd.startswith("/debate"):
        return "\u274c \u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a."

    parts = cmd.split(maxsplit=2)
    if len(parts) == 1:
        return (
            "\U0001f3db \u062f\u0633\u062a\u0648\u0631\u0627\u062a \u0645\u0646\u0627\u0638\u0631\u0647 \u0686\u0646\u062f-\u0639\u0627\u0645\u0644 (Debate):\n"
            "  /debate <topic>                           \u0627\u062c\u0631\u0627\u06cc \u0645\u0646\u0627\u0638\u0631\u0647 \u062e\u0648\u062f\u06a9\u0627\u0631 \u067e\u06cc\u0631\u0627\u0645\u0648\u0646 \u0645\u0648\u0636\u0648\u0639\n"
            "  /debate list                              \u0641\u0647\u0631\u0633\u062a \u0645\u0646\u0627\u0638\u0631\u0627\u062a \u062b\u0628\u062a\u200c\u0634\u062f\u0647\n"
            "  /debate status <id>                       \u0627\u0631\u0632\u06cc\u0627\u0628\u06cc \u0627\u062c\u0645\u0627\u0639 \u0646\u0634\u0633\u062a\n"
            "  /debate reset                             \u067e\u0627\u06a9\u0633\u0627\u0632\u06cc \u062d\u0627\u0641\u0638\u0647 \u0645\u0646\u0627\u0638\u0631\u0627\u062a\n"
            "  /verify <claim>                           \u0631\u0627\u0633\u062a\u06cc\u200c\u0622\u0632\u0645\u0627\u06cc\u06cc \u0648 \u06a9\u0634\u0641 \u0645\u063a\u0627\u0644\u0637\u0627\u062a"
        )

    subcmd = parts[1].lower()
    arg_rest = parts[2] if len(parts) > 2 else ""

    if subcmd == "list":
        res = debate_list_sessions()
        debates = res.get("debates", [])
        if not debates:
            return "\U0001f4dc \u0647\u06cc\u0686 \u0645\u0646\u0627\u0638\u0631\u0647\u200c\u0627\u06cc \u062b\u0628\u062a \u0646\u0634\u062f\u0647 \u0627\u0633\u062a."
        lines = ["\U0001f3db \u0641\u0647\u0631\u0633\u062a \u0646\u0634\u0633\u062a\u200c\u0647\u0627\u06cc \u0645\u0646\u0627\u0638\u0631\u0647:"]
        for d in debates:
            lines.append(f"- `{d['debate_id']}`: **{d['topic']}** ({d['status']}, \u0627\u0637\u0645\u06cc\u0646\u0627\u0646: {d['confidence_score']})")
        return "\n".join(lines)

    if subcmd == "reset":
        debate_reset_all()
        return "\u2705 \u062d\u0627\u0641\u0638\u0647 \u0645\u0646\u0627\u0638\u0631\u0627\u062a \u067e\u0627\u06a9\u0633\u0627\u0632\u06cc \u0634\u062f."

    if subcmd == "status":
        did = arg_rest.strip()
        if not did:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0634\u0646\u0627\u0633\u0647 \u0645\u0646\u0627\u0638\u0631\u0647 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = debate_reach_consensus(did)
        if not res.get("success"):
            return f"\u274c {res.get('error')}"
        return res.get("summary", "")

    # Treat whole arg as topic for autonomous debate
    topic = cmd[len("/debate") :].strip()
    res = debate_run_autonomous(
        topic=topic,
        proponent_arg=f"\u062f\u0644\u0627\u06cc\u0644 \u0645\u0648\u0627\u0641\u0642 \u067e\u06cc\u0631\u0627\u0645\u0648\u0646 {topic}",
        opponent_arg=f"\u062f\u0644\u0627\u06cc\u0644 \u0645\u0646\u062a\u0642\u062f \u0648 \u0686\u0627\u0644\u0634\u200c\u0647\u0627\u06cc {topic}",
    )
    if res.get("success"):
        return res.get("consensus_summary", "")
    return f"\u274c \u062e\u0637\u0627 \u062f\u0631 \u0627\u062c\u0631\u0627\u06cc \u0645\u0646\u0627\u0638\u0631\u0647: {res.get('error')}"
''',
    "dream/debate/__init__.py": r'''"""Autonomous Multi-Agent Debate, Delphi Consensus & Verifiable Fact-Checking Subsystem."""

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
            description="Multi-agent debate rounds, Delphi consensus evaluation, and fact verification.",
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
''',
    "dream/tools/toolsets.py": r'''"""Toolset categorization, grouping, and dynamic tool management."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from dream.tools.base import REGISTRY, Tool


@dataclass(frozen=True)
class Toolset:
    """Group of related tools identified by name."""

    name: str
    description: str
    tools: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


# Default built-in toolsets matching Dream's core capabilities
BUILTIN_TOOLSETS: dict[str, Toolset] = {
    "core": Toolset(
        name="core",
        description="Fundamental utilities (datetime, math calculation)",
        tools=("get_datetime", "calculate"),
    ),
    "workspace": Toolset(
        name="workspace",
        description="Workspace note inspection and editing",
        tools=("read_note", "list_notes", "write_note"),
    ),
    "web": Toolset(
        name="web",
        description="Public internet search and page fetching",
        tools=("search_web", "read_page"),
    ),
    "skills": Toolset(
        name="skills",
        description="Reusable skill management, hub discovery, and autonomous evolution",
        tools=(
            "save_skill",
            "use_skill",
            "list_skills",
            "skill_view",
            "edit_skill",
            "delete_skill",
            "save_skill_bundle",
            "apply_skill_proposal",
            "discard_skill_proposal",
            "hub_search_skills",
            "hub_install_skill",
            "skill_evolve_optimize",
            "skill_export_bundle",
            "skill_import_bundle",
        ),
    ),
    "reminders": Toolset(
        name="reminders",
        description="Scheduled reminders and tasks",
        tools=("create_reminder", "cancel_reminder"),
    ),
    "system": Toolset(
        name="system",
        description="System commands and external communication",
        tools=("run_shell", "send_email"),
    ),
    "mcp": Toolset(
        name="mcp",
        description="Model Context Protocol servers, discovery, and tool execution",
        tools=(
            "mcp_list_servers",
            "mcp_list_tools",
            "mcp_call_tool",
            "mcp_read_resource",
            "mcp_reload",
        ),
    ),
    "subagents": Toolset(
        name="subagents",
        description="Multi-agent orchestration, delegation, and worker lifecycle",
        tools=(
            "subagent_spawn",
            "subagent_wait",
            "subagent_delegate_task",
            "subagent_list",
            "subagent_terminate",
        ),
    ),
    "scheduler": Toolset(
        name="scheduler",
        description="Autonomous cron scheduling, reminders, and multi-channel delivery",
        tools=(
            "schedule_task",
            "list_schedules",
            "cancel_schedule",
            "trigger_schedule",
        ),
    ),
    "retrieval": Toolset(
        name="retrieval",
        description="Hybrid semantic retrieval and knowledge graph memory association",
        tools=(
            "search_hybrid_memory",
            "query_knowledge_graph",
        ),
    ),
    "distill": Toolset(
        name="distill",
        description="Autonomous trajectory recording, distillation, and evaluation benchmarks",
        tools=(
            "distill_record_trajectory",
            "distill_export_dataset",
            "eval_run_benchmark",
        ),
    ),
    "profiles": Toolset(
        name="profiles",
        description="Multi-profile persona scoping and isolated workspace management",
        tools=(
            "profile_list",
            "profile_get_current",
            "profile_switch",
            "profile_create",
        ),
    ),
    "context": Toolset(
        name="context",
        description="Prioritized context files (SOUL, AGENTS, USER, MEMORY) and budgeting",
        tools=(
            "context_get_tier",
            "context_update_tier",
            "context_get_budget_report",
            "context_assemble_prompt",
            "context_reload_all",
        ),
    ),
    "terminal": Toolset(
        name="terminal",
        description="Multi-backend isolated execution (Local, Docker, SSH, Cloud Sandboxes)",
        tools=(
            "terminal_execute",
            "terminal_list_backends",
            "terminal_switch_backend",
        ),
    ),
    "browser": Toolset(
        name="browser",
        description="Multi-driver browser control, DOM extraction, and visual interaction",
        tools=(
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_screenshot",
            "browser_extract_content",
            "browser_close",
            "browser_get_status",
        ),
    ),
    "dialectic": Toolset(
        name="dialectic",
        description="Self-reflective dialectic user modeling and knowledge synthesis",
        tools=(
            "dialectic_observe",
            "dialectic_reflect",
            "dialectic_get_belief_graph",
            "dialectic_reconcile",
            "dialectic_query_traits",
        ),
    ),
    "acp": Toolset(
        name="acp",
        description="Agent Client Protocol (ACP) IDE integration and diff tools",
        tools=(
            "acp_apply_diff",
            "acp_read_diagnostics",
            "acp_get_session_status",
            "acp_list_agents",
            "acp_call_agent",
        ),
    ),
    "plugins": Toolset(
        name="plugins",
        description="Dynamic plugin installation, lifecycle management, and extension hooks",
        tools=(
            "plugin_list",
            "plugin_install",
            "plugin_enable",
            "plugin_disable",
            "plugin_get_info",
        ),
    ),
    "swarm": Toolset(
        name="swarm",
        description="Distributed swarm orchestration, DAG task execution, and consensus",
        tools=(
            "swarm_spawn_node",
            "swarm_plan_workflow",
            "swarm_execute_step",
            "swarm_run_all",
            "swarm_reach_consensus",
            "swarm_get_status",
            "swarm_broadcast_message",
        ),
    ),
    "speech": Toolset(
        name="speech",
        description="Voice synthesis (TTS), recognition (STT), and HybridEmo emotion modeling",
        tools=(
            "speech_text_to_speech",
            "speech_speech_to_text",
            "speech_analyze_voice_emotion",
            "speech_list_voices",
        ),
    ),
    "ocr": Toolset(
        name="ocr",
        description="Persian document OCR, receipt parsing, and invoice field extraction",
        tools=(
            "ocr_extract_document",
            "ocr_extract_invoice",
        ),
    ),
    "knowledge": Toolset(
        name="knowledge",
        description=(
            "Multimodal temporal knowledge graph, timeline reasoning, "
            "and cross-modal entity linking"
        ),
        tools=(
            "knowledge_add_entity",
            "knowledge_add_relation",
            "knowledge_query_temporal",
            "knowledge_get_entity_timeline",
            "knowledge_link_multimodal_artifact",
            "knowledge_get_stats",
        ),
    ),
    "alignment": Toolset(
        name="alignment",
        description=(
            "Continuous self-improving alignment, multi-dimensional scoring, "
            "self-critique, and DPO dataset generation"
        ),
        tools=(
            "alignment_record_feedback",
            "alignment_critique_and_refine",
            "alignment_evaluate_response",
            "alignment_export_dataset",
            "alignment_get_stats",
        ),
    ),
    "research": Toolset(
        name="research",
        description=(
            "Autonomous multi-step deep research, evidence collection, "
            "and multi-source intelligence synthesis"
        ),
        tools=(
            "research_plan_investigation",
            "research_add_source",
            "research_synthesize_report",
            "research_run_autonomous",
            "research_export_report",
            "research_get_status",
            "research_list_sessions",
        ),
    ),
    "cache": Toolset(
        name="cache",
        description=(
            "Semantic caching, speculative pre-fetching, and token economics optimization"
        ),
        tools=(
            "cache_lookup_query",
            "cache_store_entry",
            "cache_predict_tool",
            "cache_get_economics",
            "cache_clear",
            "cache_warmup",
        ),
    ),
    "sandbox": Toolset(
        name="sandbox",
        description=(
            "Isolated Python code execution, dataset analysis, and REPL interpreter"
        ),
        tools=(
            "sandbox_execute_python",
            "sandbox_analyze_dataset",
            "sandbox_reset_session",
            "sandbox_list_artifacts",
            "sandbox_get_status",
        ),
    ),
    "canvas": Toolset(
        name="canvas",
        description=(
            "Interactive visual artifacts, diagrams, standalone previews, and versioning"
        ),
        tools=(
            "canvas_create_artifact",
            "canvas_update_artifact",
            "canvas_get_artifact",
            "canvas_list_artifacts",
            "canvas_diff_versions",
            "canvas_render_preview",
            "canvas_export_bundle",
            "canvas_reset_session",
            "canvas_get_status",
        ),
    ),
    "debate": Toolset(
        name="debate",
        description=(
            "Multi-agent debate rounds, Delphi consensus evaluation, and fact verification"
        ),
        tools=(
            "debate_create_session",
            "debate_add_turn",
            "debate_run_autonomous",
            "debate_verify_statement",
            "debate_reach_consensus",
            "debate_list_sessions",
            "debate_reset_all",
        ),
    ),
}

_TOOLSETS: dict[str, Toolset] = dict(BUILTIN_TOOLSETS)


def register_toolset(
    name: str,
    tools: Collection[str],
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> Toolset:
    """Register a new named toolset or update an existing one."""
    toolset = Toolset(
        name=name,
        description=description,
        tools=tuple(sorted(set(tools))),
        metadata=metadata or {},
    )
    _TOOLSETS[name] = toolset
    return toolset


def unregister_toolset(name: str) -> bool:
    """Remove a registered toolset (returns True if removed)."""
    if name in _TOOLSETS:
        del _TOOLSETS[name]
        return True
    return False


def get_toolset(name: str) -> Toolset | None:
    """Return a Toolset by name, or None if not registered."""
    return _TOOLSETS.get(name)


def list_toolsets() -> list[Toolset]:
    """Return a list of all registered Toolsets."""
    return list(_TOOLSETS.values())


def filter_tools(
    toolsets: Collection[str] | None = None,
    include_tools: Collection[str] | None = None,
    exclude_tools: Collection[str] | None = None,
    registry: Mapping[str, Tool] | None = None,
) -> dict[str, Tool]:
    """Filter registered tools by toolset names and explicit inclusions/exclusions."""
    source = REGISTRY if registry is None else registry

    if toolsets is None and include_tools is None and exclude_tools is None:
        return dict(source)

    allowed_names: set[str] = set()

    if toolsets is not None:
        for ts_name in toolsets:
            ts = _TOOLSETS.get(ts_name)
            if ts:
                allowed_names.update(ts.tools)

    if include_tools is not None:
        allowed_names.update(include_tools)

    if toolsets is None and include_tools is None:
        allowed_names.update(source.keys())

    if exclude_tools is not None:
        allowed_names.difference_update(exclude_tools)

    return {name: tool for name, tool in source.items() if name in allowed_names}
''',
    "tests/test_debate_and_factchecking.py": r'''"""Unit and integration tests for Autonomous Multi-Agent Debate & Fact-Checking Subsystem."""

from __future__ import annotations

import pytest

from dream.debate import (
    DebateEngine,
    DebateModerator,
    DebateRole,
    DebateStatus,
    FactChecker,
    VerificationStatus,
    debate_add_turn,
    debate_create_session,
    debate_list_sessions,
    debate_reach_consensus,
    debate_reset_all,
    debate_run_autonomous,
    debate_verify_statement,
    handle_debate_slash_command,
    reset_global_debate_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_debate_engine() -> None:
    reset_global_debate_engine()
    yield
    reset_global_debate_engine()


def test_toolset_includes_debate() -> None:
    """Verify debate toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("debate")
    assert ts is not None
    assert "debate_create_session" in ts.tools
    assert "debate_verify_statement" in ts.tools
    assert "debate_run_autonomous" in ts.tools
    assert "debate" in BUILTIN_TOOLSETS


def test_factchecker_fallacy_detection_and_claims() -> None:
    """Verify statement extraction and logical fallacy identification."""
    checker = FactChecker()

    statement_fallacy = "همه می‌دانند که یا باید این سیستم اجرا شود یا نابودی کامل حتمی است!"
    fallacies = checker.detect_fallacies(statement_fallacy)
    assert len(fallacies) >= 2

    claims = checker.extract_claims("زبان پایتون سرعت اجرای بالایی در محاسبات عددی دارد. این موضوع در مقالات معتبر اثبات شده است.")
    assert len(claims) >= 1
    assert claims[0].verification_status == VerificationStatus.UNVERIFIED


def test_factchecker_evidence_verification() -> None:
    """Verify evidence matching and contradiction detection."""
    checker = FactChecker()
    claim = checker.extract_claims("زمین به دور خورشید گردش می‌کند.")[0]

    # Positive evidence verification
    verified_claim = checker.verify_claim_against_evidence(
        claim,
        evidence="بر اساس قوانین کپلر، زمین در یک مدار بیضوی به دور خورشید گردش می‌کند.",
    )
    assert verified_claim.verification_status in (VerificationStatus.VERIFIED, VerificationStatus.PARTIAL)
    assert verified_claim.confidence_score >= 0.5

    # Contradiction verification
    contradicted_claim = checker.verify_claim_against_evidence(
        claim,
        evidence="این ادعا کاملاً غلط و نادرست است و زمین به دور خورشید گردش نمی‌کند.",
    )
    assert contradicted_claim.verification_status == VerificationStatus.CONTRADICTED


def test_delphi_moderator_and_consensus_computation() -> None:
    """Verify multi-round moderation and Delphi consensus scoring."""
    engine = DebateEngine()
    session = engine.create_debate(topic="مهاجرت به معماری میکروسرویس")

    # Turn 1
    engine.add_argument(
        debate_id=session.debate_id,
        role=DebateRole.PROPONENT,
        speaker_name="Architect Pro",
        argument="معماری میکروسرویس قابلیت مقیاس‌پذیری مستقل تیم‌ها را افزایش می‌دهد.",
        evidence="میکروسرویس قابلیت مقیاس‌پذیری و استقلال تیم‌ها را فراهم می‌آورد.",
    )

    # Turn 2
    engine.add_argument(
        debate_id=session.debate_id,
        role=DebateRole.OPPONENT,
        speaker_name="Architect Skeptic",
        argument="پیچیدگی شبکه و هزینه نگهداری در معماری توزیع‌شده افزایش می‌یابد.",
        evidence="پیچیدگی شبکه و هزینه نگهداری سرویس‌های توزیع‌شده بالا است.",
    )

    status, score, summary = engine.moderator.evaluate_consensus(session)
    assert score > 0.4
    assert "Delphi Consensus Report" in summary
    assert len(session.turns) == 2


def test_debate_engine_autonomous_rounds() -> None:
    """Verify autonomous debate rounds and session lifecycle."""
    engine = DebateEngine()
    session, summary = engine.run_autonomous_debate(
        topic="استفاده از هوش مصنوعی در کدنویسی",
        proponent_arg="ابزارهای هوش مصنوعی بهره‌وری توسعه‌دهندگان را به میزان چشمگیری افزایش می‌دهند.",
        opponent_arg="کدهای تولیدشده توسط هوش مصنوعی ممکن است دارای باگ‌های امنیتی باشند.",
        evidence="هوش مصنوعی بهره‌وری توسعه‌دهندگان را افزایش می‌دهد اما ممکن است باگ امنیتی داشته باشد.",
    )

    assert session.status in (DebateStatus.CONVERGED, DebateStatus.IN_PROGRESS)
    assert session.confidence_score > 0.0
    assert len(session.turns) == 2
    assert "Delphi Consensus Report" in summary


def test_debate_tools_and_slash_commands() -> None:
    """Verify LLM agent tools and /debate & /verify slash commands."""
    # Tool: verify statement
    res_v = debate_verify_statement(
        statement="سرعت نور در خلا حدود ۳۰۰ هزار کیلومتر بر ثانیه است.",
        evidence="سرعت نور در خلا دقیقاً ۲۹۹,۷۹۲ کیلومتر بر ثانیه اندازه‌گیری شده است.",
    )
    assert res_v["success"] is True
    assert res_v["confidence"] >= 0.4

    # Tool: autonomous debate
    res_deb = debate_run_autonomous(
        topic="تحلیل کارایی زبان Rust در مقایسه با C++",
        proponent_arg="زبان Rust با سیستم Borrow Checker امنیت حافظه را تضمین می‌کند.",
        opponent_arg="زمان کامپایل در Rust در پروژه‌های بزرگ نسبت به C++ طولانی‌تر است.",
    )
    assert res_deb["success"] is True
    assert "session" in res_deb

    # Tool: list
    res_list = debate_list_sessions()
    assert res_list["success"] is True
    assert len(res_list["debates"]) >= 1

    # Slash: /verify
    slash_v = handle_debate_slash_command("/verify زمین مسطح است چون همه می‌دانند!")
    assert "نتیجه ارزیابی" in slash_v
    assert "مغالطه" in slash_v

    # Slash: /debate list
    slash_list = handle_debate_slash_command("/debate list")
    assert "فهرست نشست‌های مناظره" in slash_list

    # Slash: /debate reset
    slash_reset = handle_debate_slash_command("/debate reset")
    assert "پاکسازی شد" in slash_reset
''',
}


def main() -> None:
    root = Path(__file__).resolve().parent
    if not (root / "dream").exists():
        if (root / "dream-repo" / "dream").exists():
            root = root / "dream-repo"
        elif (Path.cwd() / "dream").exists():
            root = Path.cwd()
        else:
            print(f"Error: could not locate Dream repo root from {root}")
            sys.exit(1)

    print(f"Applying Phase 34 (Autonomous Multi-Agent Debate & Fact-Checking) to: {root}")

    for rel_path, content in FILES.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"  [written] {rel_path}")

    print("\nRunning pytest validation...")
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_debate_and_factchecking.py", "-v"],
        cwd=root,
    )
    if res.returncode != 0:
        print("\n[FAIL] Pytest failed for Phase 34")
        sys.exit(res.returncode)

    print("\nRunning security audit...")
    audit_res = subprocess.run(
        [sys.executable, "tools/security_audit.py"],
        cwd=root,
    )
    if audit_res.returncode != 0:
        print("\n[FAIL] Security audit failed for Phase 34")
        sys.exit(audit_res.returncode)

    print("\n[SUCCESS] Phase 34 (Autonomous Multi-Agent Debate & Fact-Checking) applied and verified cleanly!")


if __name__ == "__main__":
    main()
