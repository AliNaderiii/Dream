"""Multi-Agent Neural Mesh & Distributed Peer Federation Subsystem for Dream."""

from __future__ import annotations

from dream.federation.consensus import ConsensusCoordinator
from dream.federation.engine import FederationEngine, get_federation_engine
from dream.federation.gossip import GossipEngine
from dream.federation.mesh_router import MeshRouter
from dream.federation.slash import handle_federation_command
from dream.federation.tools import (
    federation_broadcast_gossip,
    federation_delegate_task,
    federation_get_metrics,
    federation_get_topology,
    federation_register_peer,
    federation_reset,
    federation_trigger_election,
    get_federation_tools,
    get_global_federation_engine,
    reset_global_federation_engine,
)
from dream.federation.types import (
    DistributedTask,
    FederationTopology,
    GossipMessage,
    GossipMessageType,
    PeerHealth,
    PeerNode,
    PeerRole,
)

__all__ = [
    "ConsensusCoordinator",
    "DistributedTask",
    "FederationEngine",
    "FederationTopology",
    "GossipEngine",
    "GossipMessage",
    "GossipMessageType",
    "MeshRouter",
    "PeerHealth",
    "PeerNode",
    "PeerRole",
    "federation_broadcast_gossip",
    "federation_delegate_task",
    "federation_get_metrics",
    "federation_get_topology",
    "federation_register_peer",
    "federation_reset",
    "federation_trigger_election",
    "get_federation_engine",
    "get_federation_tools",
    "get_global_federation_engine",
    "handle_federation_command",
    "reset_global_federation_engine",
]
