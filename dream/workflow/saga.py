"""Saga execution pattern and transactional compensation rollback engine."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from dream.workflow.checkpoint import CheckpointManager
from dream.workflow.types import (
    StepExecutionStatus,
    WorkflowState,
    WorkflowStatus,
    WorkflowStep,
)

logger = logging.getLogger(__name__)

ToolExecutorFunc = Callable[[str, dict[str, Any]], Any]


class SagaOrchestrator:
    """Orchestrates forward multi-step workflows with transactional backward compensation."""

    def __init__(
        self,
        checkpoint_manager: CheckpointManager | None = None,
        tool_executor: ToolExecutorFunc | None = None,
    ) -> None:
        self.checkpoints = checkpoint_manager or CheckpointManager()
        self.tool_executor = tool_executor or self._default_mock_tool_executor

    def execute_step(self, state: WorkflowState) -> WorkflowStep:
        """Execute the current step in the workflow state machine."""
        if state.current_step_index >= len(state.steps):
            state.status = WorkflowStatus.COMPLETED
            raise IndexError("All workflow steps have already been processed.")

        step = state.steps[state.current_step_index]

        # Check human approval gate
        if step.requires_human_approval and step.status == StepExecutionStatus.PENDING:
            step.status = StepExecutionStatus.IN_PROGRESS
            state.status = WorkflowStatus.PAUSED_APPROVAL
            return step

        step.status = StepExecutionStatus.IN_PROGRESS
        state.status = WorkflowStatus.RUNNING

        start_time = time.time()
        try:
            # Execute tool action
            output = self.tool_executor(step.action_tool, step.action_payload)
            step.output = output
            step.status = StepExecutionStatus.SUCCESS
            step.error = None
            step.execution_time_ms = (time.time() - start_time) * 1000

            # Record checkpoint
            self.checkpoints.save_checkpoint(state, label=f"Completed {step.name_fa}")

            # Advance state index
            state.current_step_index += 1
            if state.current_step_index >= len(state.steps):
                state.status = WorkflowStatus.COMPLETED

        except Exception as exc:
            step.execution_time_ms = (time.time() - start_time) * 1000
            step.retry_count += 1
            step.error = str(exc)

            if step.retry_count <= step.retry_limit:
                logger.warning(
                    f"Step {step.step_id} failed, retry "
                    f"{step.retry_count}/{step.retry_limit}: {exc}"
                )
                step.status = StepExecutionStatus.PENDING
            else:
                step.status = StepExecutionStatus.FAILED
                state.status = WorkflowStatus.FAILED
                logger.error(f"Step {step.step_id} failed permanently: {exc}. Initiating rollback.")
                self.rollback_workflow(state)

        return step

    def approve_and_continue(self, state: WorkflowState) -> WorkflowStep:
        """Grant human approval for a paused workflow step and execute it immediately."""
        if state.status != WorkflowStatus.PAUSED_APPROVAL:
            raise ValueError(f"Workflow '{state.workflow_id}' is not awaiting human approval.")

        step = state.steps[state.current_step_index]
        step.requires_human_approval = False
        return self.execute_step(state)

    def rollback_workflow(self, state: WorkflowState) -> list[str]:
        """Execute compensation actions in reverse order for all successful preceding steps."""
        compensated_steps: list[str] = []

        # Iterate backwards from preceding step
        for idx in range(state.current_step_index - 1, -1, -1):
            prev_step = state.steps[idx]
            if prev_step.status == StepExecutionStatus.SUCCESS and prev_step.compensation_tool:
                try:
                    payload = dict(prev_step.compensation_payload)
                    payload["previous_output"] = prev_step.output
                    self.tool_executor(prev_step.compensation_tool, payload)
                    prev_step.status = StepExecutionStatus.COMPENSATED
                    compensated_steps.append(prev_step.step_id)
                except Exception as comp_err:
                    logger.error(
                        f"Compensation failed for step {prev_step.step_id}: {comp_err}"
                    )

        state.status = WorkflowStatus.ROLLED_BACK
        return compensated_steps

    def _default_mock_tool_executor(self, tool_name: str, payload: dict[str, Any]) -> Any:
        """Deterministic mock executor for testing and standalone execution."""
        if "fail" in tool_name.lower():
            raise RuntimeError(f"Simulated execution failure in tool '{tool_name}'.")

        return {
            "status": "success",
            "tool": tool_name,
            "processed_payload": payload,
            "timestamp": time.time(),
        }
