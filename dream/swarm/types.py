"""Data types, roles, and consensus models for Multi-Agent Swarm subsystem."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentRole(str, Enum):
    """Specialized roles for swarm agents."""

    LEADER = "leader"
    ARCHITECT = "architect"
    CODER = "coder"
    CRITIC = "critic"
    RESEARCHER = "researcher"
    ARBITER = "arbiter"
    SPECIALIST = "specialist"


class TaskStatus(str, Enum):
    """Lifecycle statuses for swarm tasks."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class SwarmNode:
    """An autonomous agent node in the swarm cluster."""

    node_id: str
    name: str
    role: AgentRole
    model: str = "gpt-4o"
    capabilities: list[str] = field(default_factory=list)
    status: str = "idle"  # idle, busy, offline
    created_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize node to dictionary."""
        return {
            "node_id": self.node_id,
            "name": self.name,
            "role": self.role.value if isinstance(self.role, AgentRole) else self.role,
            "model": self.model,
            "capabilities": self.capabilities,
            "status": self.status,
            "created_at": self.created_at,
            "last_heartbeat": self.last_heartbeat,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SwarmNode:
        """Instantiate node from dictionary."""
        role_val = data.get("role", "specialist")
        try:
            role = AgentRole(role_val)
        except Exception:
            role = AgentRole.SPECIALIST
        return cls(
            node_id=data["node_id"],
            name=data.get("name", data["node_id"]),
            role=role,
            model=data.get("model", "gpt-4o"),
            capabilities=data.get("capabilities", []),
            status=data.get("status", "idle"),
            created_at=data.get("created_at", time.time()),
            last_heartbeat=data.get("last_heartbeat", time.time()),
            metadata=data.get("metadata", {}),
        )


@dataclass(slots=True)
class SwarmTask:
    """A decomposable sub-task in the swarm execution DAG."""

    task_id: str
    title: str
    description: str = ""
    assigned_to: str = ""  # node_id or role
    dependencies: list[str] = field(default_factory=list)  # task_ids
    status: TaskStatus = TaskStatus.PENDING
    result: str = ""
    error: str = ""
    priority: int = 1  # 1 = highest
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize task to dictionary."""
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "assigned_to": self.assigned_to,
            "dependencies": self.dependencies,
            "status": self.status.value if isinstance(self.status, TaskStatus) else self.status,
            "result": self.result,
            "error": self.error,
            "priority": self.priority,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SwarmTask:
        """Instantiate task from dictionary."""
        status_val = data.get("status", "pending")
        try:
            status = TaskStatus(status_val)
        except Exception:
            status = TaskStatus.PENDING
        return cls(
            task_id=data["task_id"],
            title=data.get("title", ""),
            description=data.get("description", ""),
            assigned_to=data.get("assigned_to", ""),
            dependencies=data.get("dependencies", []),
            status=status,
            result=data.get("result", ""),
            error=data.get("error", ""),
            priority=data.get("priority", 1),
            created_at=data.get("created_at", time.time()),
            completed_at=data.get("completed_at"),
            metadata=data.get("metadata", {}),
        )


@dataclass(slots=True)
class SwarmMessage:
    """An inter-agent message routed across the swarm message bus."""

    msg_id: str
    sender_id: str
    recipient_id: str  # specific node_id or "*" for broadcast
    topic: str
    payload: Any
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize message to dictionary."""
        return {
            "msg_id": self.msg_id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "topic": self.topic,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class ConsensusDecision:
    """Outcome of a multi-agent deliberation or voting process."""

    proposal_id: str
    proposal_text: str
    votes: dict[str, Any] = field(default_factory=dict)  # node_id -> {"choice": ..., "reason": ...}
    verdict: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    passed: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize consensus decision to dictionary."""
        return {
            "proposal_id": self.proposal_id,
            "proposal_text": self.proposal_text,
            "votes": self.votes,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "passed": self.passed,
            "timestamp": self.timestamp,
        }
