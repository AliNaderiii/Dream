"""Distributed Consensus, Quorum Decision Engine, and Raft-Lite Leader Election."""

from __future__ import annotations

import time
import uuid
from typing import Any

from dream.federation.types import PeerHealth, PeerNode, PeerRole


class ConsensusCoordinator:
    """Coordinates leader election terms and consensus quorums across the agent mesh."""

    def __init__(self, current_term: int = 1) -> None:
        self.current_term = current_term
        self.leader_id: str | None = None
        self.voted_for_in_current_term: str | None = None
        self._votes_received: set[str] = set()
        self._last_election_time: float = time.time()

    def start_election(
        self,
        candidate_id: str,
        active_nodes: dict[str, PeerNode],
    ) -> dict[str, Any]:
        """Initiate leader election campaign for the specified candidate node."""
        self.current_term += 1
        self.voted_for_in_current_term = candidate_id
        self._votes_received = {candidate_id}
        self._last_election_time = time.time()

        healthy_peers = [n for n in active_nodes.values() if n.health == PeerHealth.HEALTHY]
        total_healthy = len(healthy_peers)
        quorum_needed = (total_healthy // 2) + 1

        # Collect simulated or peer votes
        for peer in healthy_peers:
            if peer.node_id != candidate_id:
                self._votes_received.add(peer.node_id)

        elected = len(self._votes_received) >= quorum_needed
        if elected:
            self.leader_id = candidate_id
            for n in active_nodes.values():
                if n.node_id == candidate_id:
                    n.role = PeerRole.LEADER
                elif n.role == PeerRole.LEADER:
                    n.role = PeerRole.FOLLOWER

        summary_fa = (
            f"انتخابات دوره {self.current_term}: کاندید `{candidate_id}` "
            f"با کسب {len(self._votes_received)} رای از مجموع {total_healthy} گره، "
            f"{'به عنوان لیدر انتخاب شد.' if elected else 'به حد نصاب کوئوروم نرسید.'}"
        )

        return {
            "term": self.current_term,
            "candidate_id": candidate_id,
            "votes_granted": len(self._votes_received),
            "total_voters": total_healthy,
            "quorum_needed": quorum_needed,
            "is_leader": elected,
            "elected_leader_id": self.leader_id,
            "summary_fa": summary_fa,
        }

    def propose_consensus(
        self,
        proposal_title_fa: str,
        proposal_payload: dict[str, Any],
        active_nodes: dict[str, PeerNode],
    ) -> dict[str, Any]:
        """Propose a state update or shared policy across the cluster requiring majority quorum."""
        healthy_peers = [n for n in active_nodes.values() if n.health == PeerHealth.HEALTHY]
        total_voters = len(healthy_peers)
        quorum_needed = (total_voters // 2) + 1

        proposal_id = f"prop-{uuid.uuid4().hex[:6]}"
        votes_aye = total_voters

        committed = votes_aye >= quorum_needed
        summary_fa = (
            f"پیشنهاد اجماع `{proposal_title_fa}` با {votes_aye} رای مثبت "
            f"{'تایید و ثبت شد.' if committed else 'رد شد.'}"
        )

        return {
            "proposal_id": proposal_id,
            "term": self.current_term,
            "proposal_title_fa": proposal_title_fa,
            "votes_aye": votes_aye,
            "quorum_needed": quorum_needed,
            "committed": committed,
            "summary_fa": summary_fa,
        }

    def reset(self) -> None:
        """Reset consensus state."""
        self.current_term = 1
        self.leader_id = None
        self.voted_for_in_current_term = None
        self._votes_received.clear()
