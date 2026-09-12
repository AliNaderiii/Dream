"""Comprehensive unit and integration test suite for Neural Mesh & Federation Subsystem."""

from __future__ import annotations

import pytest

from dream.federation.consensus import ConsensusCoordinator
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
    GossipMessageType,
    PeerHealth,
    PeerNode,
    PeerRole,
)
from dream.tools.toolsets import get_toolset


@pytest.fixture(autouse=True)
def cleanup_federation() -> None:
    reset_global_federation_engine()
    yield
    reset_global_federation_engine()


def test_toolset_includes_federation() -> None:
    """Verify federation toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("federation")
    assert ts is not None
    assert ts.name == "federation"
    assert "federation_register_peer" in ts.tools
    assert "federation_broadcast_gossip" in ts.tools
    assert "federation_delegate_task" in ts.tools
    assert "federation_get_topology" in ts.tools
    assert "federation_trigger_election" in ts.tools


def test_mesh_router_and_hash_ring() -> None:
    """Test consistent hash ring routing and capability matchmaking."""
    router = MeshRouter(replicas=3)
    nodes = {
        "node-vision": PeerNode(
            node_id="node-vision",
            display_name_fa="گره بینایی",
            endpoint="mesh://10.0.0.1",
            capabilities=["vision", "ocr"],
            workload_score=0.2,
        ),
        "node-code": PeerNode(
            node_id="node-code",
            display_name_fa="گره کد",
            endpoint="mesh://10.0.0.2",
            capabilities=["refactor", "sandbox"],
            workload_score=0.5,
        ),
    }

    router.build_ring(nodes)

    # Hash ring routing
    target_node_id = router.route_by_key("task-key-12345")
    assert target_node_id in ("node-vision", "node-code")

    # Capability matching
    best_vision = router.find_best_node_for_capability(nodes, "vision")
    assert best_vision is not None
    assert best_vision.node_id == "node-vision"

    best_code = router.find_best_node_for_capability(nodes, "refactor")
    assert best_code is not None
    assert best_code.node_id == "node-code"


def test_gossip_protocol_dissemination() -> None:
    """Test epidemic gossip packet creation, deduplication, and fanout."""
    gossip = GossipEngine(fanout=2, message_ttl=3)

    msg = gossip.create_message(
        msg_type=GossipMessageType.STATE_SYNC,
        sender_id="node-1",
        payload={"knowledge_version": 42},
    )
    assert msg.message_id.startswith("gsp-")
    assert msg.ttl_hops == 3

    # Deduplication test
    is_new, _ = gossip.process_incoming_message(msg, "node-2")
    assert is_new is False  # Already seen during creation

    # Fanout target selection
    peers = [
        PeerNode("p1", "همتا ۱", "ep1"),
        PeerNode("p2", "همتا ۲", "ep2"),
        PeerNode("p3", "همتا ۳", "ep3"),
    ]
    targets = gossip.select_gossip_targets(peers, exclude_node_id="p1")
    assert len(targets) == 2
    assert "p1" not in targets


def test_consensus_and_leader_election() -> None:
    """Test Raft-lite leader election and quorum proposal agreement."""
    consensus = ConsensusCoordinator()
    nodes = {
        "n1": PeerNode("n1", "گره ۱", "ep1", role=PeerRole.FOLLOWER, health=PeerHealth.HEALTHY),
        "n2": PeerNode("n2", "گره ۲", "ep2", role=PeerRole.FOLLOWER, health=PeerHealth.HEALTHY),
        "n3": PeerNode("n3", "گره ۳", "ep3", role=PeerRole.FOLLOWER, health=PeerHealth.HEALTHY),
    }

    res = consensus.start_election(candidate_id="n1", active_nodes=nodes)
    assert res["is_leader"] is True
    assert res["elected_leader_id"] == "n1"
    assert nodes["n1"].role == PeerRole.LEADER

    # Proposal consensus
    prop_res = consensus.propose_consensus(
        proposal_title_fa="بروزرسانی خط مشی امنیتی",
        proposal_payload={"policy": "strict"},
        active_nodes=nodes,
    )
    assert prop_res["committed"] is True
    assert prop_res["votes_aye"] == 3


def test_federation_engine_and_tools() -> None:
    """Test master FederationEngine, LLM tools, and slash commands."""
    engine = get_global_federation_engine()

    # 1. Register peer
    node2 = engine.register_peer(
        node_id="worker-02",
        display_name_fa="گره پردازشگر فرعی",
        endpoint="mesh://192.168.1.100:9090",
        capabilities=["speech", "audio"],
    )
    assert node2.node_id == "worker-02"
    assert len(engine.peers) == 2

    # 2. Delegate task
    task_res = engine.delegate_task(
        task_name="سنتز صوت",
        required_capability="speech",
        payload={"text": "سلام"},
    )
    assert task_res["success"] is True
    assert task_res["assigned_node_id"] == "worker-02"

    # 3. Topology
    topo = engine.get_topology()
    assert topo.total_peers == 2
    assert topo.healthy_peers == 2

    # 4. LLM Tools
    tools = get_federation_tools()
    assert len(tools) >= 5

    res_reg = federation_register_peer(
        node_id="worker-gpu-03",
        display_name_fa="گره هوش مصنوعی ۳",
        endpoint="mesh://192.168.1.101:9090",
        capabilities=["vision"],
    )
    assert res_reg["success"] is True

    res_gsp = federation_broadcast_gossip(msg_type="heartbeat", payload={"ping": 1})
    assert res_gsp["success"] is True

    res_del = federation_delegate_task(task_name="تحلیل تصویر", required_capability="vision")
    assert res_del["success"] is True
    assert res_del["assigned_node_id"] == "worker-gpu-03"

    res_top = federation_get_topology()
    assert res_top["success"] is True
    assert res_top["total_peers"] == 3

    res_ele = federation_trigger_election()
    assert res_ele["is_leader"] is True

    res_met = federation_get_metrics()
    assert res_met["success"] is True
    assert res_met["status"] == "healthy"

    # 5. Slash commands
    s_help = handle_federation_command("")
    assert "راهنمای دستورات شبکه فدراسیون" in s_help

    s_top = handle_federation_command("topology")
    assert "توپولوژی کلاستر فدراسیون" in s_top

    s_peers = handle_federation_command("peers")
    assert "لیست گره‌های همتا" in s_peers

    s_reg = handle_federation_command("register node-5 گره_پنج mesh://10.0.0.5 ocr,vision")
    assert "با موفقیت به شبکه متصل شد" in s_reg

    s_del = handle_federation_command("delegate OCR_سند ocr")
    assert "واگذار شد" in s_del

    s_ele = handle_federation_command("elect dream-node-primary")
    assert "نتیجه انتخابات" in s_ele

    s_met = handle_federation_command("metrics")
    assert "تله‌متری فدراسیون" in s_met

    s_res = handle_federation_command("reset")
    assert "بازنشانی شد" in s_res

    # Reset tool
    t_res = federation_reset()
    assert t_res["success"] is True
