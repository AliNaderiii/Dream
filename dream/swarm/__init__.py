"""Multi-Agent Swarm, Distributed RPC & Consensus Protocol subsystem."""

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
