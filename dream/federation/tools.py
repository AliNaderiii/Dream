"""LLM Agent Tools and Toolset Definitions for Multi-Agent Neural Mesh & Federation."""

from __future__ import annotations

import logging
from typing import Any

from dream.federation.engine import FederationEngine, get_federation_engine

logger = logging.getLogger(__name__)

_GLOBAL_FEDERATION_ENGINE: FederationEngine | None = None


def get_global_federation_engine() -> FederationEngine:
    """Retrieve or initialize global singleton FederationEngine."""
    global _GLOBAL_FEDERATION_ENGINE
    if _GLOBAL_FEDERATION_ENGINE is None:
        _GLOBAL_FEDERATION_ENGINE = get_federation_engine()
    return _GLOBAL_FEDERATION_ENGINE


def reset_global_federation_engine() -> None:
    """Reset global FederationEngine instance for test isolation."""
    global _GLOBAL_FEDERATION_ENGINE
    if _GLOBAL_FEDERATION_ENGINE is not None:
        _GLOBAL_FEDERATION_ENGINE.reset()
    _GLOBAL_FEDERATION_ENGINE = None


def federation_register_peer(
    node_id: str,
    display_name_fa: str,
    endpoint: str,
    capabilities: list[str] | None = None,
) -> dict[str, Any]:
    """Register or join a new agent node to the distributed neural mesh cluster.

    Args:
        node_id: Unique node identifier (e.g. 'dream-worker-gpu-01').
        display_name_fa: Persian label for peer node.
        endpoint: Network protocol endpoint (e.g. 'mesh://192.168.1.50:9090').
        capabilities: List of toolsets/specializations supported (e.g. ['vision', 'ocr']).
    """
    engine = get_global_federation_engine()
    node = engine.register_peer(
        node_id=node_id,
        display_name_fa=display_name_fa,
        endpoint=endpoint,
        capabilities=capabilities,
    )
    return {
        "success": True,
        "node": node.to_dict(),
        "summary_fa": f"گره `{display_name_fa}` با موفقیت به شبکه متصل شد.",
    }


def federation_broadcast_gossip(
    msg_type: str = "state_sync",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Broadcast state or event packet via epidemic gossip protocol.

    Args:
        msg_type: Type of gossip message ('state_sync', 'heartbeat', 'consensus_proposal').
        payload: Arbitrary state dictionary to synchronize.
    """
    engine = get_global_federation_engine()
    return engine.broadcast_gossip(msg_type, payload or {})


def federation_delegate_task(
    task_name: str,
    required_capability: str = "general",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Route and delegate agent execution task to the optimal specialized peer node.

    Args:
        task_name: Description of task (e.g. 'پردازش ویدیوی امنیتی').
        required_capability: Skill requirement (e.g. 'vision', 'refactor', 'speech').
        payload: Task parameters and arguments.
    """
    engine = get_global_federation_engine()
    return engine.delegate_task(task_name, required_capability, payload or {})


def federation_get_topology() -> dict[str, Any]:
    """Retrieve full distributed cluster topology, peer matrix, and leader node."""
    engine = get_global_federation_engine()
    topo = engine.get_topology()
    return {"success": True, **topo.to_dict()}


def federation_trigger_election(candidate_node_id: str = "") -> dict[str, Any]:
    """Initiate Raft-lite leader election across active cluster peers.

    Args:
        candidate_node_id: Node ID campaigning for leadership (defaults to local node).
    """
    engine = get_global_federation_engine()
    return engine.trigger_leader_election(candidate_node_id or None)


def federation_get_metrics() -> dict[str, Any]:
    """Get operational telemetry and liveness metrics for the Federation mesh."""
    engine = get_global_federation_engine()
    return {"success": True, **engine.get_metrics()}


def federation_reset() -> dict[str, Any]:
    """Reset federation cluster states and reconnect local node."""
    reset_global_federation_engine()
    return {"success": True, "message_fa": "شبکه فدراسیون عامل‌ها با موفقیت بازنشانی شد."}


def get_federation_tools() -> list[dict[str, Any]]:
    """Return tool manifests for LLM registration."""
    return [
        {
            "name": "federation_register_peer",
            "description": "Register a new agent peer node in the distributed federation cluster.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string"},
                    "display_name_fa": {"type": "string"},
                    "endpoint": {"type": "string"},
                    "capabilities": {"type": "array"},
                },
                "required": ["node_id", "display_name_fa", "endpoint"],
            },
            "handler": federation_register_peer,
        },
        {
            "name": "federation_broadcast_gossip",
            "description": "Disseminate state update across peer mesh via gossip protocol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "msg_type": {"type": "string", "default": "state_sync"},
                    "payload": {"type": "object"},
                },
            },
            "handler": federation_broadcast_gossip,
        },
        {
            "name": "federation_delegate_task",
            "description": "Route and delegate an agent task to the most specialized healthy peer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_name": {"type": "string"},
                    "required_capability": {"type": "string", "default": "general"},
                    "payload": {"type": "object"},
                },
                "required": ["task_name"],
            },
            "handler": federation_delegate_task,
        },
        {
            "name": "federation_get_topology",
            "description": "Inspect real-time peer topology, cluster leader, and active nodes.",
            "parameters": {"type": "object", "properties": {}},
            "handler": federation_get_topology,
        },
        {
            "name": "federation_trigger_election",
            "description": "Run distributed leader election and consensus quorum.",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_node_id": {"type": "string"},
                },
            },
            "handler": federation_trigger_election,
        },
    ]
