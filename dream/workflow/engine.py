"""Workflow Lifecycle Orchestrator and State Machine Controller."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from dream.workflow.checkpoint import CheckpointManager
from dream.workflow.saga import SagaOrchestrator, ToolExecutorFunc
from dream.workflow.types import (
    StepExecutionStatus,
    WorkflowReport,
    WorkflowState,
    WorkflowStatus,
    WorkflowStep,
)

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Manages creation, execution, approval gates, and compensation for long-horizon workflows."""

    def __init__(
        self,
        saga: SagaOrchestrator | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        tool_executor: ToolExecutorFunc | None = None,
    ) -> None:
        self.checkpoints = checkpoint_manager or CheckpointManager()
        self.saga = saga or SagaOrchestrator(
            checkpoint_manager=self.checkpoints,
            tool_executor=tool_executor,
        )
        self._workflows: dict[str, WorkflowState] = {}
        self._reports: list[WorkflowReport] = []
        self._seed_default_workflow()

    def _seed_default_workflow(self) -> None:
        """Seed a reference multi-step financial transaction workflow with compensation."""
        steps = [
            WorkflowStep(
                step_id="step_1_balance_check",
                name_fa="بررسی موجودی حساب مبدا",
                action_tool="check_account_balance",
                action_payload={"account_id": "ACC-100", "required_amount": 500000},
                compensation_tool=None,
                requires_human_approval=False,
            ),
            WorkflowStep(
                step_id="step_2_funds_hold",
                name_fa="مسدودسازی موقت مبلغ در حساب مبدا",
                action_tool="hold_funds",
                action_payload={"account_id": "ACC-100", "amount": 500000},
                compensation_tool="release_funds",
                compensation_payload={"account_id": "ACC-100", "amount": 500000},
                requires_human_approval=False,
            ),
            WorkflowStep(
                step_id="step_3_manager_approval",
                name_fa="تأییدیه نهایی انتقال وجه توسط مدیر",
                action_tool="verify_signature",
                action_payload={"approval_token": "TOK-99"},
                compensation_tool=None,
                requires_human_approval=True,
            ),
            WorkflowStep(
                step_id="step_4_deposit_destination",
                name_fa="واریز وجه به حساب مقصد و ثبت تراکنش",
                action_tool="deposit_funds",
                action_payload={"account_id": "ACC-200", "amount": 500000},
                compensation_tool="revert_deposit",
                compensation_payload={"account_id": "ACC-200", "amount": 500000},
                requires_human_approval=False,
            ),
        ]
        self.create_workflow(
            name="انتقال وجه بین‌بانکی امن با الگوی Saga",
            description_fa="گردش‌کار چندمرحله‌ای انتقال مالی با قابلیت بازگشت خودکار تراکنش‌ها",
            steps=steps,
            workflow_id="wf_demo_financial",
        )

    def create_workflow(
        self,
        name: str,
        description_fa: str,
        steps: list[WorkflowStep],
        workflow_id: str | None = None,
        context_variables: dict[str, Any] | None = None,
    ) -> WorkflowState:
        """Create and register a new workflow state machine."""
        wf_id = workflow_id or f"wf_{uuid.uuid4().hex[:8]}"
        state = WorkflowState(
            workflow_id=wf_id,
            name=name,
            description_fa=description_fa,
            steps=steps,
            context_variables=context_variables or {},
        )
        self._workflows[wf_id] = state
        return state

    def get_workflow(self, workflow_id: str) -> WorkflowState | None:
        """Retrieve a workflow by ID."""
        return self._workflows.get(workflow_id)

    def execute_next_step(self, workflow_id: str) -> WorkflowStep:
        """Execute the next step of the designated workflow."""
        state = self.get_workflow(workflow_id)
        if not state:
            raise KeyError(f"Workflow '{workflow_id}' not found.")
        return self.saga.execute_step(state)

    def approve_step(self, workflow_id: str) -> WorkflowStep:
        """Grant human approval for a paused step and resume."""
        state = self.get_workflow(workflow_id)
        if not state:
            raise KeyError(f"Workflow '{workflow_id}' not found.")
        return self.saga.approve_and_continue(state)

    def run_all(self, workflow_id: str) -> WorkflowReport:
        """Run workflow continuously until completion, pause for approval, or failure."""
        start_time = time.time()
        state = self.get_workflow(workflow_id)
        if not state:
            raise KeyError(f"Workflow '{workflow_id}' not found.")

        while state.status in (WorkflowStatus.PENDING, WorkflowStatus.RUNNING):
            self.saga.execute_step(state)
            if state.status in (
                WorkflowStatus.PAUSED_APPROVAL,
                WorkflowStatus.COMPLETED,
                WorkflowStatus.FAILED,
                WorkflowStatus.ROLLED_BACK,
            ):
                break

        completed = sum(1 for s in state.steps if s.status == StepExecutionStatus.SUCCESS)
        duration_ms = (time.time() - start_time) * 1000

        summary_fa = (
            f"گردش‌کار '{state.name}' در وضعیت '{state.status.value}' قرار گرفت "
            f"({completed}/{len(state.steps)} مرحله موفق)."
        )

        report = WorkflowReport(
            workflow_id=state.workflow_id,
            name=state.name,
            status=state.status,
            completed_steps=completed,
            total_steps=len(state.steps),
            duration_ms=duration_ms,
            summary_fa=summary_fa,
            steps_detail=[s.to_dict() for s in state.steps],
            rolled_back_steps=[
                s.step_id for s in state.steps if s.status == StepExecutionStatus.COMPENSATED
            ],
        )
        self._reports.append(report)
        return report

    def rollback(self, workflow_id: str) -> list[str]:
        """Manually trigger rollback for a workflow."""
        state = self.get_workflow(workflow_id)
        if not state:
            raise KeyError(f"Workflow '{workflow_id}' not found.")
        return self.saga.rollback_workflow(state)

    def format_diagram(self, workflow_id: str) -> str:
        """Generate a visual ASCII / text diagram of the workflow state machine."""
        state = self.get_workflow(workflow_id)
        if not state:
            return f"❌ گردش‌کار '{workflow_id}' یافت نشد."

        lines = [
            f"## 🔄 نمودار اجرای گردش‌کار: {state.name} (`{state.workflow_id}`)",
            f"- **وضعیت کلی:** `{state.status.value}`",
            f"- **مرحله جاری:** `{state.current_step_index + 1}/{len(state.steps)}`",
            "",
            "```text",
            "[START]",
        ]

        for idx, step in enumerate(state.steps, 1):
            icon = "⚪"
            if step.status == StepExecutionStatus.SUCCESS:
                icon = "🟢"
            elif step.status == StepExecutionStatus.IN_PROGRESS:
                icon = "🟡"
            elif step.status == StepExecutionStatus.FAILED:
                icon = "🔴"
            elif step.status == StepExecutionStatus.COMPENSATED:
                icon = "↩️"

            lines.append("  │")
            lines.append("  ▼")
            approval_tag = " [👤 نیازمند تایید]" if step.requires_human_approval else ""
            lines.append(f"({idx}) {icon} {step.name_fa} [{step.action_tool}]{approval_tag}")
            if step.compensation_tool:
                lines.append(f"      ↳ جبران‌ساز: {step.compensation_tool}")

        lines.extend([
            "  │",
            "  ▼",
            f"[{state.status.value.upper()}]",
            "```",
        ])

        return "\n".join(lines)

    def list_workflows(self) -> list[dict[str, Any]]:
        """List summary of all registered workflows."""
        return [
            {
                "workflow_id": wf.workflow_id,
                "name": wf.name,
                "status": wf.status.value,
                "total_steps": len(wf.steps),
                "current_step": wf.current_step_index,
            }
            for wf in self._workflows.values()
        ]

    def reset(self) -> None:
        """Reset all workflows, checkpoints, and reports."""
        self._workflows.clear()
        self._reports.clear()
        self.checkpoints.clear()
        self._seed_default_workflow()
