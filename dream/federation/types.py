"""Data models and type definitions for Multi-Agent Neural Mesh & Federation Subsystem."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PeerRole(str, Enum):
    """Cluster role of a federated Dream peer node."""

    LEADER = "leader"
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    OBSERVER = "observer"


class PeerHealth(str, Enum):
    """Liveness and health status of a federated peer node."""

    HEALTHY = "healthy"
    SUSPECT = "suspect"
    DEAD = "dead"
    OFFLINE = "offline"


class GossipMessageType(str, Enum):
    """Categorization of epidemic gossip mesh protocol messages."""

    HEARTBEAT = "heartbeat"
    STATE_SYNC = "state_sync"
    TASK_DELEGATION = "task_delegation"
    TASK_RESULT = "task_result"
    ELECTION_VOTE_REQUEST = "election_vote_request"
    ELECTION_VOTE_RESPONSE = "election_vote_response"
    CONSENSUS_PROPOSAL = "consensus_proposal"
    CONSENSUS_COMMIT = "consensus_commit"


@dataclass
class PeerNode:
    """Represents an active Dream agent node in the distributed federation mesh."""

    node_id: str
    display_name_fa: str
    endpoint: str
    role: PeerRole = PeerRole.FOLLOWER
    health: PeerHealth = PeerHealth.HEALTHY
    capabilities: list[str] = field(default_factory=list)
    last_heartbeat: float = field(default_factory=time.time)
    workload_score: float = 0.0  # 0.0 (idle) to 1.0 (overloaded)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize peer node to dictionary."""
        return {
            "node_id": self.node_id,
            "display_name_fa": self.display_name_fa,
            "endpoint": self.endpoint,
            "role": self.role.value,
            "health": self.health.value,
            "capabilities": self.capabilities,
            "last_heartbeat": round(self.last_heartbeat, 2),
            "workload_score": round(self.workload_score, 2),
            "metadata": self.metadata,
        }


@dataclass
class GossipMessage:
    """Structured message broadcasted through the peer-to-peer epidemic gossip mesh."""

    message_id: str
    msg_type: GossipMessageType
    sender_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    ttl_hops: int = 4
    vector_clock: int = 1
    target_node_id: str | None = None  # None for mesh broadcast

    def to_dict(self) -> dict[str, Any]:
        """Serialize gossip message to dictionary."""
        return {
            "message_id": self.message_id,
            "msg_type": self.msg_type.value,
            "sender_id": self.sender_id,
            "payload": self.payload,
            "timestamp": round(self.timestamp, 2),
            "ttl_hops": self.ttl_hops,
            "vector_clock": self.vector_clock,
            "target_node_id": self.target_node_id,
        }


@dataclass
class DistributedTask:
    """Task delegated across federated nodes based on specialization."""

    task_id: str
    task_name: str
    required_capability: str
    payload: dict[str, Any]
    origin_node_id: str
    assigned_node_id: str | None = None
    status: str = "pending"  # "pending", "running", "completed", "failed"
    result: Any = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize distributed task to dictionary."""
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "required_capability": self.required_capability,
            "origin_node_id": self.origin_node_id,
            "assigned_node_id": self.assigned_node_id,
            "status": self.status,
            "result": self.result,
            "created_at": round(self.created_at, 2),
            "completed_at": round(self.completed_at, 2) if self.completed_at else None,
        }


@dataclass
class FederationTopology:
    """Complete visual and routing topology snapshot of the agent mesh."""

    cluster_id: str
    current_term: int
    leader_id: str | None
    total_peers: int
    healthy_peers: int
    peers: dict[str, PeerNode] = field(default_factory=dict)
    active_tasks_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize topology to dictionary."""
        return {
            "cluster_id": self.cluster_id,
            "current_term": self.current_term,
            "leader_id": self.leader_id,
            "total_peers": self.total_peers,
            "healthy_peers": self.healthy_peers,
            "peers": {k: v.to_dict() for k, v in self.peers.items()},
            "active_tasks_count": self.active_tasks_count,
            "metadata": self.metadata,
        }
