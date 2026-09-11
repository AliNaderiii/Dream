"""Master Swarm Coordinator orchestrating topology, DAG execution, bus messaging, and consensus."""

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
