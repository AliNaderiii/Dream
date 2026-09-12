"""State persistence and checkpoint management for workflow replay."""

from __future__ import annotations

import copy
import time
from typing import Any

from dream.workflow.types import WorkflowState


class CheckpointManager:
    """Manages transactional snapshots and restore points for workflow execution."""

    def __init__(self) -> None:
        self._snapshots: dict[str, list[dict[str, Any]]] = {}

    def save_checkpoint(self, state: WorkflowState, label: str = "") -> dict[str, Any]:
        """Capture immutable snapshot of the workflow state at the current step."""
        checkpoint_entry = {
            "checkpoint_id": f"ckpt_{len(state.checkpoints) + 1}",
            "step_index": state.current_step_index,
            "status": state.status.value,
            "label": label or f"Step {state.current_step_index} Checkpoint",
            "context_variables": copy.deepcopy(state.context_variables),
            "timestamp": time.time(),
        }
        state.checkpoints.append(checkpoint_entry)

        if state.workflow_id not in self._snapshots:
            self._snapshots[state.workflow_id] = []
        self._snapshots[state.workflow_id].append(checkpoint_entry)

        return checkpoint_entry

    def get_checkpoints(self, workflow_id: str) -> list[dict[str, Any]]:
        """Retrieve all recorded checkpoints for a workflow."""
        return self._snapshots.get(workflow_id, [])

    def restore_latest_checkpoint(self, state: WorkflowState) -> bool:
        """Rollback context variables and index to the latest recorded checkpoint."""
        if not state.checkpoints:
            return False

        latest = state.checkpoints[-1]
        state.current_step_index = latest["step_index"]
        state.context_variables = copy.deepcopy(latest["context_variables"])
        return True

    def clear(self, workflow_id: str | None = None) -> None:
        """Clear snapshots for a specific workflow or reset all."""
        if workflow_id:
            self._snapshots.pop(workflow_id, None)
        else:
            self._snapshots.clear()
