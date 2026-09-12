"""Data structures and state definitions for Long-Horizon Workflow & Saga Engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkflowStatus(str, Enum):
    """Lifecycle status of a multi-step workflow execution."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED_APPROVAL = "paused_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class StepExecutionStatus(str, Enum):
    """Execution status of an individual workflow step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    COMPENSATED = "compensated"
    SKIPPED = "skipped"


@dataclass(slots=True)
class WorkflowStep:
    """An individual atomic step with forward action and backward compensation."""

    step_id: str
    name_fa: str
    action_tool: str
    action_payload: dict[str, Any] = field(default_factory=dict)
    compensation_tool: str | None = None
    compensation_payload: dict[str, Any] = field(default_factory=dict)
    requires_human_approval: bool = False
    retry_limit: int = 2
    retry_count: int = 0
    status: StepExecutionStatus = StepExecutionStatus.PENDING
    output: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize workflow step to dictionary."""
        return {
            "step_id": self.step_id,
            "name_fa": self.name_fa,
            "action_tool": self.action_tool,
            "action_payload": self.action_payload,
            "compensation_tool": self.compensation_tool,
            "compensation_payload": self.compensation_payload,
            "requires_human_approval": self.requires_human_approval,
            "retry_limit": self.retry_limit,
            "retry_count": self.retry_count,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "execution_time_ms": round(self.execution_time_ms, 2),
        }


@dataclass(slots=True)
class WorkflowState:
    """Complete serialized state machine for a persistent workflow."""

    workflow_id: str
    name: str
    description_fa: str
    steps: list[WorkflowStep]
    current_step_index: int = 0
    status: WorkflowStatus = WorkflowStatus.PENDING
    context_variables: dict[str, Any] = field(default_factory=dict)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize workflow state to dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description_fa": self.description_fa,
            "total_steps": len(self.steps),
            "current_step_index": self.current_step_index,
            "status": self.status.value,
            "steps": [s.to_dict() for s in self.steps],
            "context_variables": self.context_variables,
            "checkpoints_count": len(self.checkpoints),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class WorkflowReport:
    """Execution telemetry and audit trail report."""

    workflow_id: str
    name: str
    status: WorkflowStatus
    completed_steps: int
    total_steps: int
    duration_ms: float
    summary_fa: str
    steps_detail: list[dict[str, Any]]
    rolled_back_steps: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize workflow report to dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "status": self.status.value,
            "completed_steps": self.completed_steps,
            "total_steps": self.total_steps,
            "duration_ms": round(self.duration_ms, 2),
            "summary_fa": self.summary_fa,
            "steps_detail": self.steps_detail,
            "rolled_back_steps": self.rolled_back_steps,
            "timestamp": self.timestamp,
        }
