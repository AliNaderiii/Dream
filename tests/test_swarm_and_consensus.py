"""Tests for Multi-Agent Swarm, Distributed DAG, and Consensus subsystem."""

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
