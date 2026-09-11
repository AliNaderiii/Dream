"""Swarm Topology management, node registration, and health tracking."""

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
