#!/usr/bin/env python3
"""apply_pr22.py - Standalone installer for Phase 19 / PR #22:
Multi-Agent Swarm, Distributed DAG Execution & Multi-Model Consensus Protocol.

This installer creates or updates the following files in the target repository:
  - dream/swarm/__init__.py
  - dream/swarm/types.py
  - dream/swarm/bus.py
  - dream/swarm/topology.py
  - dream/swarm/dag.py
  - dream/swarm/consensus.py
  - dream/swarm/coordinator.py
  - dream/swarm/tools.py
  - dream/swarm/slash.py
  - dream/tools/toolsets.py
  - tests/test_swarm_and_consensus.py
"""

from __future__ import annotations

import sys
from pathlib import Path

SWARM_TYPES_PY = r'''"""Data types, roles, and consensus models for Multi-Agent Swarm subsystem."""

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
'''

SWARM_BUS_PY = r'''"""Inter-agent Message Bus and event routing for Swarm nodes."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from dream.swarm.types import SwarmMessage


class MessageBus:
    """Pub/sub and direct messaging hub for swarm agents."""

    def __init__(self, max_history: int = 1000) -> None:
        self.max_history = max_history
        self._subscribers: dict[str, list[Callable[[SwarmMessage], None]]] = {}
        self._history: list[SwarmMessage] = []

    def subscribe(self, topic: str, handler: Callable[[SwarmMessage], None]) -> None:
        """Subscribe handler to a specific topic or wildcard '*'."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        if handler not in self._subscribers[topic]:
            self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Callable[[SwarmMessage], None]) -> bool:
        """Unsubscribe handler from topic."""
        if topic in self._subscribers and handler in self._subscribers[topic]:
            self._subscribers[topic].remove(handler)
            return True
        return False

    def publish(
        self,
        sender_id: str,
        topic: str,
        payload: Any,
        recipient_id: str = "*",
    ) -> SwarmMessage:
        """Publish a message to the bus and notify matching subscribers."""
        msg = SwarmMessage(
            msg_id=f"msg_{uuid.uuid4().hex[:8]}",
            sender_id=sender_id,
            recipient_id=recipient_id,
            topic=topic,
            payload=payload,
            timestamp=time.time(),
        )

        self._history.append(msg)
        if len(self._history) > self.max_history:
            self._history.pop(0)

        # Notify exact topic subscribers
        handlers = list(self._subscribers.get(topic, []))
        # Notify wildcard topic subscribers
        if topic != "*":
            handlers.extend(self._subscribers.get("*", []))

        for h in handlers:
            try:
                h(msg)
            except Exception:
                pass

        return msg

    def send_direct(
        self,
        sender_id: str,
        recipient_id: str,
        topic: str,
        payload: Any,
    ) -> SwarmMessage:
        """Send direct point-to-point message between two specific swarm agents."""
        return self.publish(
            sender_id=sender_id,
            topic=topic,
            payload=payload,
            recipient_id=recipient_id,
        )

    def get_history(
        self,
        topic: str | None = None,
        sender_id: str | None = None,
        recipient_id: str | None = None,
        limit: int = 50,
    ) -> list[SwarmMessage]:
        """Query and filter message history."""
        results = []
        for msg in reversed(self._history):
            if topic and msg.topic != topic:
                continue
            if sender_id and msg.sender_id != sender_id:
                continue
            if recipient_id and msg.recipient_id not in (recipient_id, "*"):
                continue
            results.append(msg)
            if len(results) >= limit:
                break
        return list(reversed(results))

    def clear(self) -> None:
        """Clear all subscribers and history."""
        self._subscribers.clear()
        self._history.clear()
'''

SWARM_TOPOLOGY_PY = r'''"""Swarm Topology management, node registration, and health tracking."""

from __future__ import annotations

import time
import uuid
from typing import Any

from dream.swarm.types import AgentRole, SwarmNode


class SwarmTopology:
    """Manages active nodes, role distributions, and health monitoring in the swarm."""

    def __init__(self) -> None:
        self._nodes: dict[str, SwarmNode] = {}
        self._leader_id: str | None = None

    def register_node(
        self,
        name: str,
        role: AgentRole | str,
        model: str = "gpt-4o",
        capabilities: list[str] | None = None,
        node_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SwarmNode:
        """Register a new agent node in the swarm topology."""
        nid = node_id or f"node_{uuid.uuid4().hex[:6]}"
        if isinstance(role, str):
            try:
                role_enum = AgentRole(role.lower())
            except Exception:
                role_enum = AgentRole.SPECIALIST
        else:
            role_enum = role

        node = SwarmNode(
            node_id=nid,
            name=name,
            role=role_enum,
            model=model,
            capabilities=capabilities or [],
            status="idle",
            created_at=time.time(),
            last_heartbeat=time.time(),
            metadata=metadata or {},
        )
        self._nodes[nid] = node

        # If role is LEADER and no leader currently set, set as leader
        if role_enum == AgentRole.LEADER or self._leader_id is None:
            self._leader_id = nid

        return node

    def unregister_node(self, node_id: str) -> bool:
        """Remove a node from the topology."""
        if node_id in self._nodes:
            del self._nodes[node_id]
            if self._leader_id == node_id:
                self._leader_id = None
                self._elect_leader()
            return True
        return False

    def get_node(self, node_id: str) -> SwarmNode | None:
        """Retrieve node by ID."""
        return self._nodes.get(node_id)

    def list_nodes(self, active_only: bool = False) -> list[SwarmNode]:
        """List all registered nodes."""
        nodes = list(self._nodes.values())
        if active_only:
            nodes = [n for n in nodes if n.status != "offline"]
        return nodes

    def get_nodes_by_role(self, role: AgentRole | str) -> list[SwarmNode]:
        """Find all nodes matching a specific role."""
        target_role = role.value if isinstance(role, AgentRole) else str(role).lower()
        return [n for n in self._nodes.values() if n.role.value == target_role]

    def get_leader(self) -> SwarmNode | None:
        """Return the current leader node."""
        if self._leader_id and self._leader_id in self._nodes:
            return self._nodes[self._leader_id]
        return self._elect_leader()

    def _elect_leader(self) -> SwarmNode | None:
        """Elect a leader from available nodes."""
        # First priority: node with LEADER role
        leaders = self.get_nodes_by_role(AgentRole.LEADER)
        if leaders:
            self._leader_id = leaders[0].node_id
            return leaders[0]

        # Second priority: ARCHITECT role
        architects = self.get_nodes_by_role(AgentRole.ARCHITECT)
        if architects:
            self._leader_id = architects[0].node_id
            return architects[0]

        # Fallback: first available node
        if self._nodes:
            first_node = next(iter(self._nodes.values()))
            self._leader_id = first_node.node_id
            return first_node

        self._leader_id = None
        return None

    def heartbeat(self, node_id: str) -> bool:
        """Update last heartbeat timestamp for a node."""
        if node_id in self._nodes:
            self._nodes[node_id].last_heartbeat = time.time()
            if self._nodes[node_id].status == "offline":
                self._nodes[node_id].status = "idle"
            return True
        return False

    def check_health(self, timeout_seconds: float = 60.0) -> list[str]:
        """Mark timed out nodes as offline and return list of unhealthy node IDs."""
        now = time.time()
        unhealthy = []
        for nid, node in self._nodes.items():
            if now - node.last_heartbeat > timeout_seconds:
                node.status = "offline"
                unhealthy.append(nid)
                if self._leader_id == nid:
                    self._elect_leader()
        return unhealthy

    def bootstrap_default_swarm(self) -> list[SwarmNode]:
        """Initialize a balanced standard swarm cluster."""
        self._nodes.clear()
        nodes = [
            self.register_node(
                "Swarm Leader",
                AgentRole.LEADER,
                model="gpt-4o",
                capabilities=["planning", "delegation", "synthesis"],
            ),
            self.register_node(
                "System Architect",
                AgentRole.ARCHITECT,
                model="gpt-4o",
                capabilities=["design", "api_spec", "architecture"],
            ),
            self.register_node(
                "Primary Coder",
                AgentRole.CODER,
                model="gpt-4o",
                capabilities=["python", "refactoring", "debugging"],
            ),
            self.register_node(
                "Code Reviewer & Critic",
                AgentRole.CRITIC,
                model="gpt-4o",
                capabilities=["code_review", "security_audit", "verification"],
            ),
            self.register_node(
                "Consensus Arbiter",
                AgentRole.ARBITER,
                model="gpt-4o",
                capabilities=["arbitration", "voting", "tie_breaker"],
            ),
        ]
        return nodes
'''

SWARM_DAG_PY = r'''"""Task Directed Acyclic Graph (DAG) for parallel and dependency-aware swarm execution."""

from __future__ import annotations

import time
import uuid
from typing import Any

from dream.swarm.types import SwarmTask, TaskStatus


class TaskDAG:
    """Manages decomposed tasks, dependency graphs, and parallel execution sequencing."""

    def __init__(self) -> None:
        self._tasks: dict[str, SwarmTask] = {}

    def add_task(
        self,
        title: str,
        description: str = "",
        assigned_to: str = "",
        dependencies: list[str] | None = None,
        priority: int = 1,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SwarmTask:
        """Add a new task node to the DAG."""
        tid = task_id or f"task_{uuid.uuid4().hex[:6]}"
        task = SwarmTask(
            task_id=tid,
            title=title,
            description=description,
            assigned_to=assigned_to,
            dependencies=dependencies or [],
            status=TaskStatus.PENDING,
            priority=priority,
            created_at=time.time(),
            metadata=metadata or {},
        )
        self._tasks[tid] = task
        return task

    def get_task(self, task_id: str) -> SwarmTask | None:
        """Retrieve task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[SwarmTask]:
        """List all tasks sorted by priority."""
        return sorted(self._tasks.values(), key=lambda t: t.priority)

    def get_ready_tasks(self) -> list[SwarmTask]:
        """Return all pending tasks whose dependencies have all completed successfully."""
        ready = []
        for task in self._tasks.values():
            if task.status != TaskStatus.PENDING:
                continue

            # Check if all dependencies are satisfied
            deps_satisfied = True
            for dep_id in task.dependencies:
                dep_task = self._tasks.get(dep_id)
                if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                    deps_satisfied = False
                    break

            if deps_satisfied:
                ready.append(task)

        # Sort ready tasks by priority
        return sorted(ready, key=lambda t: t.priority)

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus | str,
        result: str = "",
        error: str = "",
    ) -> bool:
        """Update task status and store execution output."""
        if task_id not in self._tasks:
            return False

        task = self._tasks[task_id]
        if isinstance(status, str):
            try:
                task.status = TaskStatus(status.lower())
            except Exception:
                task.status = TaskStatus.FAILED
        else:
            task.status = status

        if result:
            task.result = result
        if error:
            task.error = error

        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            task.completed_at = time.time()

        return True

    def detect_cycles(self) -> bool:
        """Detect if the task graph has any circular dependencies using DFS."""
        visited: dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited

        for tid in self._tasks:
            visited[tid] = 0

        def has_cycle(curr_id: str) -> bool:
            visited[curr_id] = 1  # visiting
            curr_task = self._tasks.get(curr_id)
            if curr_task:
                for dep_id in curr_task.dependencies:
                    if dep_id in self._tasks:
                        if visited.get(dep_id) == 1:
                            return True
                        if visited.get(dep_id) == 0 and has_cycle(dep_id):
                            return True
            visited[curr_id] = 2  # visited
            return False

        for tid in self._tasks:
            if visited[tid] == 0:
                if has_cycle(tid):
                    return True
        return False

    def is_complete(self) -> bool:
        """Return True if all tasks have terminated (completed or failed)."""
        if not self._tasks:
            return True
        return all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
            for t in self._tasks.values()
        )

    def get_progress(self) -> dict[str, Any]:
        """Compute execution progress statistics."""
        total = len(self._tasks)
        if total == 0:
            return {"total": 0, "completed": 0, "failed": 0, "pending": 0, "pct": 100.0}

        completed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED)
        in_progress = sum(1 for t in self._tasks.values() if t.status == TaskStatus.IN_PROGRESS)
        pending = sum(1 for t in self._tasks.values() if t.status == TaskStatus.PENDING)

        pct = round((completed / total) * 100.0, 1)
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "in_progress": in_progress,
            "pending": pending,
            "pct": pct,
        }

    def clear(self) -> None:
        """Reset DAG tasks."""
        self._tasks.clear()
'''

SWARM_CONSENSUS_PY = r'''"""Multi-Agent Deliberation and Consensus protocol engine."""

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
'''

SWARM_COORDINATOR_PY = r'''"""Master Swarm Coordinator orchestrating topology, DAG execution, bus messaging, and consensus."""

from __future__ import annotations

from typing import Any

from dream.swarm.bus import MessageBus
from dream.swarm.consensus import ConsensusEngine
from dream.swarm.dag import TaskDAG
from dream.swarm.topology import SwarmTopology
from dream.swarm.types import AgentRole, ConsensusDecision, SwarmTask, TaskStatus


class SwarmCoordinator:
    """Central orchestrator managing multi-agent swarm cluster operations."""

    def __init__(self) -> None:
        self.topology = SwarmTopology()
        self.dag = TaskDAG()
        self.bus = MessageBus()
        self.consensus = ConsensusEngine()
        self._ensure_bootstrap()

    def _ensure_bootstrap(self) -> None:
        """Ensure initial default swarm topology exists."""
        if not self.topology.list_nodes():
            self.topology.bootstrap_default_swarm()

    def reset_swarm(self) -> None:
        """Reset swarm cluster state, tasks, and message bus."""
        self.topology = SwarmTopology()
        self.dag.clear()
        self.bus.clear()
        self.topology.bootstrap_default_swarm()

    def plan_workflow(self, goal: str) -> list[SwarmTask]:
        """Decompose a high-level goal into an orchestrated Swarm Task DAG."""
        self.dag.clear()

        # Step 1: Architecture & Planning
        t1 = self.dag.add_task(
            title=f"Architecture design for: {goal[:40]}",
            description=f"Define technical specification and API architecture for '{goal}'",
            assigned_to=AgentRole.ARCHITECT.value,
            priority=1,
        )

        # Step 2: Core Implementation
        t2 = self.dag.add_task(
            title=f"Core implementation for: {goal[:40]}",
            description=f"Write code according to architecture spec for '{goal}'",
            assigned_to=AgentRole.CODER.value,
            dependencies=[t1.task_id],
            priority=2,
        )

        # Step 3: Review & Security Audit
        t3 = self.dag.add_task(
            title=f"Security audit and code review for: {goal[:40]}",
            description=f"Validate correctness, security boundaries, and code quality for '{goal}'",
            assigned_to=AgentRole.CRITIC.value,
            dependencies=[t2.task_id],
            priority=3,
        )

        # Step 4: Final Synthesis & Delivery
        t4 = self.dag.add_task(
            title=f"Final delivery & report for: {goal[:40]}",
            description=f"Synthesize deliverables and finalize execution report for '{goal}'",
            assigned_to=AgentRole.LEADER.value,
            dependencies=[t3.task_id],
            priority=4,
        )

        # Broadcast event to message bus
        self.bus.publish(
            sender_id="coordinator",
            topic="workflow.planned",
            payload={"goal": goal, "task_count": 4},
        )

        return [t1, t2, t3, t4]

    def execute_next_step(self) -> dict[str, Any]:
        """Execute the next available ready tasks in the DAG."""
        ready_tasks = self.dag.get_ready_tasks()
        if not ready_tasks:
            is_done = self.dag.is_complete()
            return {
                "executed": 0,
                "is_complete": is_done,
                "message": "No ready tasks available or execution completed.",
            }

        executed_count = 0
        executed_details = []

        for task in ready_tasks:
            # Find assigned node or matching role node
            nodes = self.topology.get_nodes_by_role(task.assigned_to)
            worker = nodes[0] if nodes else self.topology.get_leader()
            worker_id = worker.node_id if worker else "system_worker"
            worker_name = worker.name if worker else "System Worker"

            # Transition task to IN_PROGRESS
            self.dag.update_task_status(task.task_id, TaskStatus.IN_PROGRESS)

            # Publish task start event
            self.bus.publish(
                sender_id=worker_id,
                topic="task.started",
                payload={"task_id": task.task_id, "title": task.title},
            )

            # Produce mock/computed result
            result_text = f"Successfully completed by {worker_name}: {task.title}"
            self.dag.update_task_status(
                task.task_id,
                TaskStatus.COMPLETED,
                result=result_text,
            )

            # Publish task completed event
            self.bus.publish(
                sender_id=worker_id,
                topic="task.completed",
                payload={"task_id": task.task_id, "result": result_text},
            )

            executed_count += 1
            executed_details.append({"task_id": task.task_id, "worker": worker_name})

        return {
            "executed": executed_count,
            "tasks": executed_details,
            "progress": self.dag.get_progress(),
            "is_complete": self.dag.is_complete(),
        }

    def run_all_steps(self, max_iterations: int = 10) -> dict[str, Any]:
        """Run workflow DAG to completion."""
        iterations = 0
        while iterations < max_iterations and not self.dag.is_complete():
            step_res = self.execute_next_step()
            if step_res["executed"] == 0:
                break
            iterations += 1

        return {
            "iterations": iterations,
            "progress": self.dag.get_progress(),
            "is_complete": self.dag.is_complete(),
        }

    def vote_on_proposal(
        self,
        proposal_text: str,
        default_choice: str = "approve",
    ) -> ConsensusDecision:
        """Initiate swarm voting deliberation across all active nodes."""
        voters = self.topology.list_nodes(active_only=True)
        decision = self.consensus.simulate_mock_deliberation(
            proposal_text=proposal_text,
            voter_nodes=voters,
            default_choice=default_choice,
        )

        # Broadcast consensus outcome to bus
        self.bus.publish(
            sender_id="coordinator",
            topic="consensus.reached",
            payload=decision.to_dict(),
        )
        return decision

    def get_status_summary(self) -> dict[str, Any]:
        """Generate comprehensive cluster status summary."""
        leader = self.topology.get_leader()
        nodes = self.topology.list_nodes()
        progress = self.dag.get_progress()
        recent_msgs = self.bus.get_history(limit=5)
        recent_consensus = self.consensus.get_history(limit=3)

        return {
            "leader": leader.to_dict() if leader else None,
            "nodes_count": len(nodes),
            "active_nodes": [n.to_dict() for n in nodes],
            "dag_progress": progress,
            "tasks": [t.to_dict() for t in self.dag.list_tasks()],
            "recent_messages_count": len(recent_msgs),
            "recent_consensus_count": len(recent_consensus),
        }
'''

SWARM_TOOLS_PY = r'''"""LLM Tool bindings for Multi-Agent Swarm orchestration and consensus."""

from __future__ import annotations

from typing import Any

from dream.swarm.coordinator import SwarmCoordinator

_GLOBAL_SWARM_COORDINATOR: SwarmCoordinator | None = None


def get_global_swarm_coordinator() -> SwarmCoordinator:
    """Get or create singleton SwarmCoordinator."""
    global _GLOBAL_SWARM_COORDINATOR
    if _GLOBAL_SWARM_COORDINATOR is None:
        _GLOBAL_SWARM_COORDINATOR = SwarmCoordinator()
    return _GLOBAL_SWARM_COORDINATOR


def reset_global_swarm_coordinator() -> None:
    """Reset singleton SwarmCoordinator for tests."""
    global _GLOBAL_SWARM_COORDINATOR
    _GLOBAL_SWARM_COORDINATOR = None


def swarm_spawn_node(
    name: str,
    role: str = "specialist",
    model: str = "gpt-4o",
    capabilities: list[str] | None = None,
) -> dict[str, Any]:
    """Spawn and register a new specialized agent node in the swarm cluster."""
    coord = get_global_swarm_coordinator()
    node = coord.topology.register_node(
        name=name,
        role=role,
        model=model,
        capabilities=capabilities or [],
    )
    return node.to_dict()


def swarm_plan_workflow(goal: str) -> list[dict[str, Any]]:
    """Decompose a complex goal into an orchestrated Swarm Task DAG."""
    coord = get_global_swarm_coordinator()
    tasks = coord.plan_workflow(goal)
    return [t.to_dict() for t in tasks]


def swarm_execute_step() -> dict[str, Any]:
    """Execute the next available ready tasks in the Swarm DAG."""
    coord = get_global_swarm_coordinator()
    return coord.execute_next_step()


def swarm_run_all(goal: str = "") -> dict[str, Any]:
    """Plan (if goal provided) and execute all tasks in the Swarm DAG to completion."""
    coord = get_global_swarm_coordinator()
    if goal:
        coord.plan_workflow(goal)
    return coord.run_all_steps()


def swarm_reach_consensus(proposal: str) -> dict[str, Any]:
    """Initiate a multi-agent voting and deliberation process across swarm nodes."""
    coord = get_global_swarm_coordinator()
    decision = coord.vote_on_proposal(proposal)
    return decision.to_dict()


def swarm_get_status() -> dict[str, Any]:
    """Retrieve comprehensive real-time status of the Swarm cluster."""
    coord = get_global_swarm_coordinator()
    return coord.get_status_summary()


def swarm_broadcast_message(topic: str, message: str) -> dict[str, Any]:
    """Publish a broadcast message to all nodes on the swarm event bus."""
    coord = get_global_swarm_coordinator()
    msg = coord.bus.publish(
        sender_id="agent",
        topic=topic,
        payload={"message": message},
    )
    return msg.to_dict()


def get_swarm_tools() -> list[Any]:
    """Return all Swarm management tools for LLM agent binding."""
    return [
        swarm_spawn_node,
        swarm_plan_workflow,
        swarm_execute_step,
        swarm_run_all,
        swarm_reach_consensus,
        swarm_get_status,
        swarm_broadcast_message,
    ]
'''

SWARM_SLASH_PY = r'''"""Interactive slash command handler for Multi-Agent Swarm management."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.swarm.tools import get_global_swarm_coordinator


def handle_swarm_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/swarm` slash command in interactive REPL or TUI."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors

    coord = get_global_swarm_coordinator()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "status"

    if subcmd in ("status", "info", "ls", "list"):
        summary = coord.get_status_summary()
        title = (
            "\U0001f41d "
            "\u0648\u0636\u0639\u06cc\u062a "
            "\u06a9\u0644\u0627\u0633\u062a\u0631 "
            "\u0633\u0648\u0627\u0631\u0645 "
            f"({summary['nodes_count']} \u0639\u0627\u0645\u0644 \u0641\u0639\u0627\u0644):"
        )
        output(cm.bold(title))
        leader = summary.get("leader")
        if leader:
            ldr_txt = f"{leader['name']} ({leader['role']})"
            lbl_lead = "\u0631\u0647\u0628\u0631 \u0633\u0648\u0627\u0631\u0645"
            output(f"  \u2022 {lbl_lead}: {cm.cyan(ldr_txt)}")

        mem_lbl = "\u0639\u0627\u0645\u0644\u200c\u0647\u0627\u06cc \u0639\u0636\u0648:"
        output(cm.bold(f"  {mem_lbl}"))
        for n in summary["active_nodes"]:
            role_badge = cm.yellow(f"[{n['role']}]")
            output(f"    \u2022 {n['name']:<22} {role_badge} ({n['model']})")

        prog = summary["dag_progress"]
        p_txt = f"{prog['pct']}% ({prog['completed']}/{prog['total']})"
        prog_lbl = "\u067e\u06cc\u0634\u0631\u0641\u062a \u062a\u0633\u06a9\u200c\u0647\u0627"
        output(f"  \u2022 {prog_lbl}: {cm.green(p_txt)}")
        return True

    if subcmd in ("run", "exec", "plan"):
        if len(parts) < 3:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0647\u062f\u0641 \u06cc\u0627 "
                "\u0639\u0646\u0648\u0627\u0646 "
                "\u062a\u0633\u06a9 "
                "\u0631\u0627 "
                "\u0648\u0627\u0631\u062f "
                "\u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        goal = " ".join(parts[2:])
        plan_msg = (
            f"\U0001f41d \u0628\u0631\u0646\u0627\u0645\u0647\u200c\u0631\u06cc\u0632\u06cc "
            f"\u0648 \u0627\u062c\u0631\u0627\u06cc "
            f"\u0633\u0648\u0627\u0631\u0645 "
            f"\u0628\u0631\u0627\u06cc: '{goal}'..."
        )
        output(cm.cyan(plan_msg))
        tasks = coord.plan_workflow(goal)
        dag_msg = (
            f"  \u2713 {len(tasks)} "
            "\u062a\u0633\u06a9 \u062f\u0631 "
            "\u06af\u0631\u0627\u0641 DAG "
            "\u0627\u06cc\u062c\u0627\u062f "
            "\u0634\u062f."
        )
        output(cm.green(dag_msg))

        res = coord.run_all_steps()
        succ = (
            f"\u2713 \u0627\u062c\u0631\u0627 \u062f\u0631 "
            f"{res['iterations']} \u06af\u0627\u0645 \u0628\u0627 "
            "\u0645\u0648\u0641\u0642\u06cc\u062a "
            "\u06a9\u0627\u0645\u0644 \u0634\u062f."
        )
        output(cm.green(succ))
        return True

    if subcmd in ("vote", "consensus"):
        if len(parts) < 3:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0645\u062a\u0646 "
                "\u067e\u06cc\u0634\u0646\u0647\u0627\u062f "
                "\u0631\u0627 "
                "\u0648\u0627\u0631\u062f "
                "\u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        prop = " ".join(parts[2:])
        vote_init = (
            "\U0001f5f3\ufe0f \u062f\u0631 "
            "\u062d\u0627\u0644 \u0627\u062e\u0630 "
            "\u0622\u0631\u0627\u06cc "
            "\u0639\u0627\u0645\u0644\u200c\u0647\u0627\u06cc "
            "\u0633\u0648\u0627\u0631\u0645..."
        )
        output(cm.cyan(vote_init))
        dec = coord.vote_on_proposal(prop)
        status_color = cm.green if dec.passed else cm.red
        verdict_txt = (
            f"\u0646\u062a\u06cc\u062c\u0647 "
            f"\u0627\u062c\u0645\u0627\u0639: {dec.verdict.upper()} "
            f"(\u0627\u0637\u0645\u06cc\u0646\u0627\u0646: {dec.confidence})"
        )
        output(status_color(f"  \u2022 {verdict_txt}"))
        if dec.reasoning:
            reasons_lbl = "\u062f\u0644\u0627\u06cc\u0644"
            output(f"  \u2022 {reasons_lbl}: {cm.dim(dec.reasoning[:80])}...")
        return True

    if subcmd == "spawn":
        if len(parts) < 3:
            err = (
                "\u2717 \u0646\u0627\u0645 "
                "\u0639\u0627\u0645\u0644 \u0644\u0627\u0632\u0645 \u0627\u0633\u062a. "
                "\u0645\u062b\u0627\u0644: /swarm spawn SecurityAgent critic"
            )
            output(cm.red(err))
            return True
        name = parts[2]
        role = parts[3] if len(parts) > 3 else "specialist"
        node = coord.topology.register_node(name=name, role=role)
        succ_spawn = (
            f"\u2713 \u0639\u0627\u0645\u0644 '{node.name}' "
            f"\u0628\u0627 \u0646\u0642\u0634 '{node.role.value}' "
            "\u0627\u0636\u0627\u0641\u0647 "
            "\u0634\u062f."
        )
        output(cm.green(succ_spawn))
        return True

    if subcmd == "reset":
        coord.reset_swarm()
        reset_msg = (
            "\u2713 \u06a9\u0644\u0627\u0633\u062a\u0631 "
            "\u0633\u0648\u0627\u0631\u0645 "
            "\u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a "
            "\u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc "
            "\u0634\u062f."
        )
        output(cm.green(reset_msg))
        return True

    # Help
    help_title = (
        "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
        "\u062f\u0633\u062a\u0648\u0631 /swarm:"
    )
    output(cm.bold(help_title))
    output(
        "  /swarm status                       - "
        "\u0646\u0645\u0627\u06cc\u0634 \u0648\u0636\u0639\u06cc\u062a "
        "\u06a9\u0644\u0627\u0633\u062a\u0631 / Swarm status"
    )
    output(
        "  /swarm run <goal>                   - "
        "\u0627\u062c\u0631\u0627\u06cc \u06af\u0631\u0648\u0647\u06cc "
        "\u062a\u0633\u06a9 / Execute multi-agent plan"
    )
    output(
        "  /swarm vote <proposal>              - "
        "\u0631\u0623\u06cc\u200c\u06af\u06cc\u0631\u06cc "
        "\u0648 \u0627\u062c\u0645\u0627\u0639 / Deliberation & vote"
    )
    output(
        "  /swarm spawn <name> [role]          - "
        "\u0627\u0636\u0627\u0641\u0647 \u06a9\u0631\u062f\u0646 "
        "\u0639\u0627\u0645\u0644 \u062c\u062f\u06cc\u062f / Spawn node"
    )
    output(
        "  /swarm reset                        - "
        "\u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc "
        "\u06a9\u0644\u0627\u0633\u062a\u0631 / Reset cluster"
    )
    return True
'''

SWARM_INIT_PY = r'''"""Multi-Agent Swarm, Distributed RPC & Consensus Protocol subsystem."""

from __future__ import annotations

from dream.swarm.bus import MessageBus
from dream.swarm.consensus import ConsensusEngine
from dream.swarm.coordinator import SwarmCoordinator
from dream.swarm.dag import TaskDAG
from dream.swarm.slash import handle_swarm_command
from dream.swarm.tools import (
    get_global_swarm_coordinator,
    get_swarm_tools,
    reset_global_swarm_coordinator,
    swarm_broadcast_message,
    swarm_execute_step,
    swarm_get_status,
    swarm_plan_workflow,
    swarm_reach_consensus,
    swarm_run_all,
    swarm_spawn_node,
)
from dream.swarm.topology import SwarmTopology
from dream.swarm.types import (
    AgentRole,
    ConsensusDecision,
    SwarmMessage,
    SwarmNode,
    SwarmTask,
    TaskStatus,
)

__all__ = [
    "AgentRole",
    "ConsensusDecision",
    "ConsensusEngine",
    "MessageBus",
    "SwarmCoordinator",
    "SwarmMessage",
    "SwarmNode",
    "SwarmTask",
    "SwarmTopology",
    "TaskDAG",
    "TaskStatus",
    "get_global_swarm_coordinator",
    "get_swarm_tools",
    "handle_swarm_command",
    "reset_global_swarm_coordinator",
    "swarm_broadcast_message",
    "swarm_execute_step",
    "swarm_get_status",
    "swarm_plan_workflow",
    "swarm_reach_consensus",
    "swarm_run_all",
    "swarm_spawn_node",
]

try:
    from dream.tools import toolsets

    if hasattr(toolsets, "register_toolset") and "swarm" not in toolsets.BUILTIN_TOOLSETS:
        toolsets.register_toolset(
            "swarm",
            [
                "swarm_spawn_node",
                "swarm_plan_workflow",
                "swarm_execute_step",
                "swarm_run_all",
                "swarm_reach_consensus",
                "swarm_get_status",
                "swarm_broadcast_message",
            ],
            display_name="Multi-Agent Swarm",
            description="Distributed swarm orchestration, DAG task execution, and consensus",
        )
except Exception:
    pass
'''

TESTS_SWARM_PY = r'''"""Tests for Multi-Agent Swarm, Distributed DAG, and Consensus subsystem."""

from __future__ import annotations

from dream.swarm import (
    AgentRole,
    ConsensusEngine,
    MessageBus,
    SwarmCoordinator,
    SwarmTopology,
    TaskDAG,
    TaskStatus,
    get_swarm_tools,
    handle_swarm_command,
    reset_global_swarm_coordinator,
    swarm_broadcast_message,
    swarm_execute_step,
    swarm_get_status,
    swarm_plan_workflow,
    swarm_reach_consensus,
    swarm_run_all,
    swarm_spawn_node,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


def test_swarm_topology_and_leader():
    top = SwarmTopology()
    nodes = top.bootstrap_default_swarm()
    assert len(nodes) == 5

    leader = top.get_leader()
    assert leader is not None
    assert leader.role == AgentRole.LEADER

    # Register custom node
    tester = top.register_node("QA Specialist", AgentRole.SPECIALIST)
    assert tester.name == "QA Specialist"
    assert tester.role == AgentRole.SPECIALIST

    # Heartbeat check
    assert top.heartbeat(tester.node_id) is True
    unhealthy = top.check_health(timeout_seconds=9999.0)
    assert len(unhealthy) == 0

    # Unregister
    assert top.unregister_node(tester.node_id) is True
    assert top.get_node(tester.node_id) is None


def test_swarm_message_bus():
    bus = MessageBus()
    received_msgs = []

    def on_topic(msg):
        received_msgs.append(msg)

    bus.subscribe("code.review", on_topic)

    msg1 = bus.publish(
        sender_id="coder_1",
        topic="code.review",
        payload={"diff": "refactor"},
    )
    assert msg1.topic == "code.review"
    assert len(received_msgs) == 1

    # Send direct message
    msg2 = bus.send_direct(
        sender_id="leader",
        recipient_id="coder_1",
        topic="task.assign",
        payload={"task": "build feature"},
    )
    assert msg2.recipient_id == "coder_1"

    history = bus.get_history(topic="code.review")
    assert len(history) == 1
    assert history[0].msg_id == msg1.msg_id


def test_task_dag_lifecycle_and_cycles():
    dag = TaskDAG()

    t1 = dag.add_task("Design System", priority=1)
    t2 = dag.add_task("Implement Backend", dependencies=[t1.task_id], priority=2)
    t3 = dag.add_task("Write Tests", dependencies=[t2.task_id], priority=3)

    assert dag.detect_cycles() is False

    # Initially only t1 is ready
    ready1 = dag.get_ready_tasks()
    assert len(ready1) == 1
    assert ready1[0].task_id == t1.task_id

    # Complete t1
    dag.update_task_status(t1.task_id, TaskStatus.COMPLETED, result="Design ready")
    ready2 = dag.get_ready_tasks()
    assert len(ready2) == 1
    assert ready2[0].task_id == t2.task_id

    # Complete t2 and t3
    dag.update_task_status(t2.task_id, TaskStatus.COMPLETED, result="Backend ready")
    dag.update_task_status(t3.task_id, TaskStatus.COMPLETED, result="Tests passed")

    assert dag.is_complete() is True
    prog = dag.get_progress()
    assert prog["completed"] == 3
    assert prog["pct"] == 100.0


def test_consensus_engine():
    engine = ConsensusEngine()

    votes = {
        "node_1": {"choice": "approve", "confidence": 0.95, "reason": "Code meets standards"},
        "node_2": {"choice": "approve", "confidence": 0.90, "reason": "Passed security check"},
        "node_3": {"choice": "reject", "confidence": 0.40, "reason": "Needs extra docs"},
    }

    decision = engine.evaluate_proposal(
        proposal_text="Merge Pull Request #42",
        votes=votes,
        strategy="majority",
    )
    assert decision.passed is True
    assert decision.verdict == "approve"
    assert decision.confidence > 0.6
    assert len(decision.votes) == 3


def test_swarm_coordinator_workflow():
    coord = SwarmCoordinator()
    coord.reset_swarm()

    tasks = coord.plan_workflow("Build Distributed Cache")
    assert len(tasks) == 4

    res = coord.run_all_steps()
    assert res["is_complete"] is True
    assert res["iterations"] >= 3

    # Consensus test
    decision = coord.vote_on_proposal("Deploy Distributed Cache to Staging")
    assert decision.passed is True

    summary = coord.get_status_summary()
    assert summary["nodes_count"] >= 5
    assert summary["dag_progress"]["completed"] == 4


def test_swarm_tools_and_slash():
    reset_global_swarm_coordinator()
    tools = get_swarm_tools()
    assert len(tools) == 7

    node = swarm_spawn_node("Research Bot", role="researcher")
    assert node["name"] == "Research Bot"

    plan = swarm_plan_workflow("Optimize Vector Database")
    assert len(plan) == 4

    step_res = swarm_execute_step()
    assert step_res["executed"] >= 1

    run_res = swarm_run_all()
    assert run_res["is_complete"] is True

    vote_res = swarm_reach_consensus("Release V2")
    assert vote_res["passed"] is True

    status_data = swarm_get_status()
    assert status_data["nodes_count"] >= 6

    bcast = swarm_broadcast_message("system.alert", "Swarm operational")
    assert bcast["topic"] == "system.alert"

    # Slash command tests
    lines = []
    handle_swarm_command("/swarm status", output=lines.append)
    assert any("Research Bot" in line or "Swarm Leader" in line for line in lines)

    lines.clear()
    handle_swarm_command("/swarm vote Approve Architecture", output=lines.append)
    assert any("APPROVE" in line for line in lines)

    reset_global_swarm_coordinator()


def test_toolset_includes_swarm():
    assert "swarm" in BUILTIN_TOOLSETS
    toolset = get_toolset("swarm")
    assert toolset is not None
    assert len(toolset.tools) >= 7
    assert "swarm_spawn_node" in toolset.tools
    assert "swarm_reach_consensus" in toolset.tools
'''


def main() -> None:
    repo_dir = Path(__file__).resolve().parent / "dream-repo"
    if not repo_dir.exists():
        repo_dir = Path.cwd()

    print(f"Applying Phase 19 (PR #22) changes to repo at: {repo_dir}")

    swarm_dir = repo_dir / "dream" / "swarm"
    swarm_dir.mkdir(parents=True, exist_ok=True)

    (swarm_dir / "__init__.py").write_text(SWARM_INIT_PY, encoding="utf-8")
    print("  ✓ Created dream/swarm/__init__.py")

    (swarm_dir / "types.py").write_text(SWARM_TYPES_PY, encoding="utf-8")
    print("  ✓ Created dream/swarm/types.py")

    (swarm_dir / "bus.py").write_text(SWARM_BUS_PY, encoding="utf-8")
    print("  ✓ Created dream/swarm/bus.py")

    (swarm_dir / "topology.py").write_text(SWARM_TOPOLOGY_PY, encoding="utf-8")
    print("  ✓ Created dream/swarm/topology.py")

    (swarm_dir / "dag.py").write_text(SWARM_DAG_PY, encoding="utf-8")
    print("  ✓ Created dream/swarm/dag.py")

    (swarm_dir / "consensus.py").write_text(SWARM_CONSENSUS_PY, encoding="utf-8")
    print("  ✓ Created dream/swarm/consensus.py")

    (swarm_dir / "coordinator.py").write_text(SWARM_COORDINATOR_PY, encoding="utf-8")
    print("  ✓ Created dream/swarm/coordinator.py")

    (swarm_dir / "tools.py").write_text(SWARM_TOOLS_PY, encoding="utf-8")
    print("  ✓ Created dream/swarm/tools.py")

    (swarm_dir / "slash.py").write_text(SWARM_SLASH_PY, encoding="utf-8")
    print("  ✓ Created dream/swarm/slash.py")

    # Update dream/tools/toolsets.py if needed
    toolsets_py = repo_dir / "dream" / "tools" / "toolsets.py"
    if toolsets_py.exists():
        content = toolsets_py.read_text(encoding="utf-8")
        if '"swarm":' not in content:
            new_entry = (
                '    "swarm": Toolset(\n'
                '        name="swarm",\n'
                '        description="Distributed swarm orchestration, DAG task execution, and consensus",\n'
                '        tools=(\n'
                '            "swarm_spawn_node",\n'
                '            "swarm_plan_workflow",\n'
                '            "swarm_execute_step",\n'
                '            "swarm_run_all",\n'
                '            "swarm_reach_consensus",\n'
                '            "swarm_get_status",\n'
                '            "swarm_broadcast_message",\n'
                '        ),\n'
                '    ),\n'
            )
            content = content.replace(
                '    "profiles": Toolset(',
                new_entry + '    "profiles": Toolset(',
            )
            toolsets_py.write_text(content, encoding="utf-8")
            print("  ✓ Updated dream/tools/toolsets.py with 'swarm' toolset")

    tests_dir = repo_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_swarm_and_consensus.py").write_text(TESTS_SWARM_PY, encoding="utf-8")
    print("  ✓ Created tests/test_swarm_and_consensus.py")

    print("\nPhase 19 (PR #22) application complete! Run pytest to verify:")
    print("  pytest tests/test_swarm_and_consensus.py")


if __name__ == "__main__":
    main()
