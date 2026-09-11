"""Multi-Agent Deliberation and Consensus protocol engine."""

from __future__ import annotations

import time
import uuid
from typing import Any

from dream.swarm.types import ConsensusDecision, SwarmNode


class ConsensusEngine:
    """Deliberation engine for reaching multi-model agreement and resolving disputes."""

    def __init__(self) -> None:
        self._history: list[ConsensusDecision] = []

    def evaluate_proposal(
        self,
        proposal_text: str,
        votes: dict[str, dict[str, Any]],
        strategy: str = "majority",
        threshold: float = 0.5,
        proposal_id: str | None = None,
    ) -> ConsensusDecision:
        """Evaluate votes on a proposal and determine outcome."""
        pid = proposal_id or f"prop_{uuid.uuid4().hex[:6]}"
        if not votes:
            decision = ConsensusDecision(
                proposal_id=pid,
                proposal_text=proposal_text,
                votes={},
                verdict="rejected",
                confidence=0.0,
                reasoning="No votes submitted",
                passed=False,
                timestamp=time.time(),
            )
            self._history.append(decision)
            return decision

        total_voters = len(votes)
        choice_counts: dict[str, int] = {}
        choice_weights: dict[str, float] = {}
        reasoning_list: list[str] = []

        for voter_id, vote_info in votes.items():
            choice = str(vote_info.get("choice", "abstain")).lower()
            confidence = float(vote_info.get("confidence", 1.0))
            reason = vote_info.get("reason", "")

            choice_counts[choice] = choice_counts.get(choice, 0) + 1
            choice_weights[choice] = choice_weights.get(choice, 0.0) + confidence
            if reason:
                reasoning_list.append(f"[{voter_id}] {choice.upper()}: {reason}")

        if strategy == "weighted":
            total_weight = sum(choice_weights.values()) or 1.0
            best_choice = max(choice_weights.items(), key=lambda x: x[1])[0]
            winning_score = choice_weights[best_choice] / total_weight
        elif strategy == "unanimous":
            best_choice = max(choice_counts.items(), key=lambda x: x[1])[0]
            if choice_counts[best_choice] == total_voters:
                winning_score = 1.0
            else:
                winning_score = choice_counts[best_choice] / total_voters
        else:  # majority
            best_choice = max(choice_counts.items(), key=lambda x: x[1])[0]
            winning_score = choice_counts[best_choice] / total_voters

        passed = (
            best_choice in ("accept", "approve", "yes", "pass")
            and winning_score >= threshold
        )

        decision = ConsensusDecision(
            proposal_id=pid,
            proposal_text=proposal_text,
            votes=votes,
            verdict=best_choice,
            confidence=round(winning_score, 3),
            reasoning="; ".join(reasoning_list),
            passed=passed,
            timestamp=time.time(),
        )
        self._history.append(decision)
        return decision

    def simulate_mock_deliberation(
        self,
        proposal_text: str,
        voter_nodes: list[SwarmNode],
        default_choice: str = "approve",
    ) -> ConsensusDecision:
        """Helper to run multi-agent deliberation simulation across active swarm nodes."""
        mock_votes: dict[str, dict[str, Any]] = {}
        for node in voter_nodes:
            role_val = node.role.value if hasattr(node.role, "value") else str(node.role)
            mock_votes[node.node_id] = {
                "choice": default_choice,
                "confidence": 0.9 if role_val in ("architect", "critic") else 0.8,
                "reason": f"Evaluated and validated by {node.name} ({role_val})",
            }
        return self.evaluate_proposal(proposal_text, mock_votes, strategy="majority")

    def get_history(self, limit: int = 50) -> list[ConsensusDecision]:
        """Return consensus decision history."""
        return list(reversed(self._history[-limit:]))
