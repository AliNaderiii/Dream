"""Master Federation and Multi-Agent Neural Mesh Engine for Dream."""

from __future__ import annotations

import time
import uuid
from typing import Any

from dream.federation.consensus import ConsensusCoordinator
from dream.federation.gossip import GossipEngine
from dream.federation.mesh_router import MeshRouter
from dream.federation.types import (
    DistributedTask,
    FederationTopology,
    GossipMessageType,
    PeerHealth,
    PeerNode,
    PeerRole,
)


class FederationEngine:
    """Master controller orchestrating distributed agent peer discovery, routing, and consensus."""

    def __init__(self, local_node_id: str = "dream-node-primary") -> None:
        self.cluster_id = f"mesh-{uuid.uuid4().hex[:6]}"
        self.local_node_id = local_node_id
        self.peers: dict[str, PeerNode] = {}
        self.tasks: dict[str, DistributedTask] = {}
        self.router = MeshRouter()
        self.gossip = GossipEngine()
        self.consensus = ConsensusCoordinator()
        self._start_time = time.time()

        # Initialize local self node
        self.register_peer(
            node_id=self.local_node_id,
            display_name_fa="گره اصلی دریم (Primary)",
            endpoint="mesh://127.0.0.1:9090",
            role=PeerRole.LEADER,
            capabilities=["core", "orchestration", "general"],
        )
        self.consensus.leader_id = self.local_node_id

    def register_peer(
        self,
        node_id: str,
        display_name_fa: str,
        endpoint: str,
        role: PeerRole = PeerRole.FOLLOWER,
        capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PeerNode:
        """Register or update a peer node in the federation cluster."""
        node = PeerNode(
            node_id=node_id,
            display_name_fa=display_name_fa,
            endpoint=endpoint,
            role=role,
            health=PeerHealth.HEALTHY,
            capabilities=capabilities or ["general"],
            last_heartbeat=time.time(),
            workload_score=0.1,
            metadata=metadata or {},
        )
        self.peers[node_id] = node
        self.router.build_ring(self.peers)
        return node

    def remove_peer(self, node_id: str) -> bool:
        """Remove a peer from the federation mesh."""
        if node_id in self.peers and node_id != self.local_node_id:
            del self.peers[node_id]
            self.router.build_ring(self.peers)
            return True
        return False

    def send_heartbeat(self, node_id: str) -> bool:
        """Update last heartbeat timestamp for a peer node."""
        if node_id in self.peers:
            self.peers[node_id].last_heartbeat = time.time()
            self.peers[node_id].health = PeerHealth.HEALTHY
            return True
        return False

    def broadcast_gossip(
        self,
        msg_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Broadcast a message via epidemic gossip protocol across the mesh."""
        try:
            m_type_enum = GossipMessageType(msg_type.lower())
        except ValueError:
            m_type_enum = GossipMessageType.STATE_SYNC

        msg = self.gossip.create_message(
            msg_type=m_type_enum,
            sender_id=self.local_node_id,
            payload=payload,
        )
        targets = self.gossip.select_gossip_targets(
            active_nodes=list(self.peers.values()),
            exclude_node_id=self.local_node_id,
        )

        return {
            "success": True,
            "message_id": msg.message_id,
            "msg_type": msg.msg_type.value,
            "target_peers_count": len(targets),
            "target_peer_ids": targets,
            "summary_fa": f"پیام گاسیپ `{msg.message_id}` به {len(targets)} گره همتا ارسال شد.",
        }

    def delegate_task(
        self,
        task_name: str,
        required_capability: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Route and delegate an agent task to the most suitable peer node."""
        target_node = self.router.find_best_node_for_capability(self.peers, required_capability)
        assigned_id = target_node.node_id if target_node else self.local_node_id

        task_id = f"tsk-{uuid.uuid4().hex[:6]}"
        now = time.time()

        # Simulated instant execution result
        result_data = {
            "execution_status": "ok",
            "executed_by": assigned_id,
            "output_summary_fa": f"وظیفه `{task_name}` توسط گره `{assigned_id}` پردازش شد.",
        }

        task = DistributedTask(
            task_id=task_id,
            task_name=task_name,
            required_capability=required_capability,
            payload=payload,
            origin_node_id=self.local_node_id,
            assigned_node_id=assigned_id,
            status="completed",
            result=result_data,
            created_at=now,
            completed_at=now + 0.05,
        )
        self.tasks[task_id] = task

        if target_node:
            target_node.workload_score = min(1.0, target_node.workload_score + 0.05)

        return {
            "success": True,
            "task_id": task_id,
            "assigned_node_id": assigned_id,
            "status": task.status,
            "result": task.result,
        }

    def trigger_leader_election(self, candidate_node_id: str | None = None) -> dict[str, Any]:
        """Trigger Raft-lite leader election term across cluster."""
        cid = candidate_node_id or self.local_node_id
        return self.consensus.start_election(candidate_id=cid, active_nodes=self.peers)

    def get_topology(self) -> FederationTopology:
        """Capture comprehensive cluster topology and peer matrix."""
        healthy_cnt = sum(1 for p in self.peers.values() if p.health == PeerHealth.HEALTHY)
        return FederationTopology(
            cluster_id=self.cluster_id,
            current_term=self.consensus.current_term,
            leader_id=self.consensus.leader_id,
            total_peers=len(self.peers),
            healthy_peers=healthy_cnt,
            peers=self.peers,
            active_tasks_count=len(self.tasks),
            metadata={"uptime_sec": round(time.time() - self._start_time, 1)},
        )

    def get_metrics(self) -> dict[str, Any]:
        """Return operational telemetry of the Federation subsystem."""
        topo = self.get_topology()
        return {
            "cluster_id": topo.cluster_id,
            "leader_id": topo.leader_id,
            "current_term": topo.current_term,
            "total_peers": topo.total_peers,
            "healthy_peers": topo.healthy_peers,
            "total_delegated_tasks": len(self.tasks),
            "status": "healthy",
        }

    def reset(self) -> None:
        """Reset federation engine states."""
        self.peers.clear()
        self.tasks.clear()
        self.gossip.clear()
        self.consensus.reset()
        self.register_peer(
            node_id=self.local_node_id,
            display_name_fa="گره اصلی دریم (Primary)",
            endpoint="mesh://127.0.0.1:9090",
            role=PeerRole.LEADER,
            capabilities=["core", "orchestration", "general"],
        )
        self.consensus.leader_id = self.local_node_id


# Global singleton
_GLOBAL_FEDERATION_ENGINE: FederationEngine | None = None


def get_federation_engine() -> FederationEngine:
    """Retrieve global singleton FederationEngine instance."""
    global _GLOBAL_FEDERATION_ENGINE
    if _GLOBAL_FEDERATION_ENGINE is None:
        _GLOBAL_FEDERATION_ENGINE = FederationEngine()
    return _GLOBAL_FEDERATION_ENGINE
