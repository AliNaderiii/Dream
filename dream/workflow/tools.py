"""LLM agent tools and singleton managers for Long-Horizon Workflow Subsystem."""

from __future__ import annotations

import logging
from typing import Any

from dream.workflow.engine import WorkflowEngine
from dream.workflow.types import WorkflowStep

logger = logging.getLogger(__name__)

_GLOBAL_WORKFLOW_ENGINE: WorkflowEngine | None = None


def get_global_workflow_engine() -> WorkflowEngine:
    """Retrieve or initialize singleton WorkflowEngine."""
    global _GLOBAL_WORKFLOW_ENGINE
    if _GLOBAL_WORKFLOW_ENGINE is None:
        _GLOBAL_WORKFLOW_ENGINE = WorkflowEngine()
    return _GLOBAL_WORKFLOW_ENGINE


def reset_global_workflow_engine() -> None:
    """Reset global WorkflowEngine instance for test isolation."""
    global _GLOBAL_WORKFLOW_ENGINE
    if _GLOBAL_WORKFLOW_ENGINE is not None:
        _GLOBAL_WORKFLOW_ENGINE.reset()
    _GLOBAL_WORKFLOW_ENGINE = None


def workflow_create_plan(
    name: str,
    description_fa: str,
    steps_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create a new multi-step DAG workflow with optional compensation tools and approval gates.

    Args:
        name: English/Persian title of the workflow.
        description_fa: Persian description of the workflow's goal.
        steps_data: List of step dictionaries with keys: step_id, name_fa, action_tool,
            action_payload, compensation_tool, requires_human_approval.
    """
    engine = get_global_workflow_engine()
    try:
        steps = [
            WorkflowStep(
                step_id=s.get("step_id", f"step_{i + 1}"),
                name_fa=s.get("name_fa", f"مرحله {i + 1}"),
                action_tool=s.get("action_tool", "echo"),
                action_payload=s.get("action_payload", {}),
                compensation_tool=s.get("compensation_tool"),
                compensation_payload=s.get("compensation_payload", {}),
                requires_human_approval=s.get("requires_human_approval", False),
            )
            for i, s in enumerate(steps_data)
        ]
        wf = engine.create_workflow(name=name, description_fa=description_fa, steps=steps)
        return {
            "success": True,
            "workflow_id": wf.workflow_id,
            "name": wf.name,
            "total_steps": len(wf.steps),
            "summary_fa": f"گردش‌کار '{wf.name}' با شناسه `{wf.workflow_id}` با موفقیت ایجاد شد.",
        }
    except Exception as exc:
        logger.error(f"Error creating workflow: {exc}")
        return {"success": False, "error": str(exc)}


def workflow_execute_step(workflow_id: str = "wf_demo_financial") -> dict[str, Any]:
    """Execute the next available step in a workflow state machine.

    Args:
        workflow_id: Identifier of the workflow to advance.
    """
    engine = get_global_workflow_engine()
    try:
        step = engine.execute_next_step(workflow_id)
        wf = engine.get_workflow(workflow_id)
        return {
            "success": True,
            "workflow_id": workflow_id,
            "workflow_status": wf.status.value if wf else "unknown",
            "step": step.to_dict(),
        }
    except Exception as exc:
        logger.error(f"Error executing step: {exc}")
        return {"success": False, "error": str(exc)}


def workflow_approve_step(workflow_id: str = "wf_demo_financial") -> dict[str, Any]:
    """Grant human approval for a paused step and resume workflow execution.

    Args:
        workflow_id: Identifier of the workflow awaiting approval.
    """
    engine = get_global_workflow_engine()
    try:
        step = engine.approve_step(workflow_id)
        return {
            "success": True,
            "workflow_id": workflow_id,
            "approved_step": step.to_dict(),
            "summary_fa": f"مرحله '{step.name_fa}' با موفقیت تایید و اجرا شد.",
        }
    except Exception as exc:
        logger.error(f"Error approving step: {exc}")
        return {"success": False, "error": str(exc)}


def workflow_rollback(workflow_id: str = "wf_demo_financial") -> dict[str, Any]:
    """Trigger manual Saga backward compensation rollback for a workflow.

    Args:
        workflow_id: Identifier of the workflow to compensate.
    """
    engine = get_global_workflow_engine()
    try:
        compensated = engine.rollback(workflow_id)
        return {
            "success": True,
            "workflow_id": workflow_id,
            "compensated_steps": compensated,
            "summary_fa": (
                f"عملیات بازگشت تراکنش‌ها (Saga Rollback) برای گردش‌کار "
                f"`{workflow_id}` با موفقیت انجام شد."
            ),
        }
    except Exception as exc:
        logger.error(f"Error rolling back workflow: {exc}")
        return {"success": False, "error": str(exc)}


def workflow_get_status(workflow_id: str = "wf_demo_financial") -> dict[str, Any]:
    """Get the real-time state machine status and steps detail for a workflow.

    Args:
        workflow_id: Identifier of the workflow to inspect.
    """
    engine = get_global_workflow_engine()
    wf = engine.get_workflow(workflow_id)
    if not wf:
        return {"success": False, "error": f"Workflow '{workflow_id}' not found."}
    return {"success": True, "workflow": wf.to_dict()}


def workflow_export_diagram(workflow_id: str = "wf_demo_financial") -> dict[str, Any]:
    """Export visual ASCII state machine diagram of a workflow.

    Args:
        workflow_id: Identifier of the workflow diagram to render.
    """
    engine = get_global_workflow_engine()
    diagram = engine.format_diagram(workflow_id)
    return {"success": True, "diagram_markdown": diagram}


def workflow_reset() -> dict[str, Any]:
    """Reset all active workflows and return engine to clean state."""
    reset_global_workflow_engine()
    return {"success": True, "message_fa": "موتور گردش‌کار با موفقیت بازنشانی شد."}


def get_workflow_tools() -> list[dict[str, Any]]:
    """Return tool manifests for LLM registration."""
    return [
        {
            "name": "workflow_create_plan",
            "description": (
                "Create a multi-step persistent workflow with Saga compensation "
                "and approval gates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description_fa": {"type": "string"},
                    "steps_data": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["name", "description_fa", "steps_data"],
            },
            "handler": workflow_create_plan,
        },
        {
            "name": "workflow_execute_step",
            "description": "Execute the next step of a workflow.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "default": "wf_demo_financial"},
                },
            },
            "handler": workflow_execute_step,
        },
        {
            "name": "workflow_approve_step",
            "description": "Grant human-in-the-loop approval for a paused workflow step.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "default": "wf_demo_financial"},
                },
            },
            "handler": workflow_approve_step,
        },
        {
            "name": "workflow_rollback",
            "description": "Trigger Saga compensation rollback for completed workflow steps.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "default": "wf_demo_financial"},
                },
            },
            "handler": workflow_rollback,
        },
        {
            "name": "workflow_get_status",
            "description": "Get detailed execution telemetry of a workflow.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "default": "wf_demo_financial"},
                },
            },
            "handler": workflow_get_status,
        },
        {
            "name": "workflow_export_diagram",
            "description": "Export visual ASCII diagram of workflow execution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "default": "wf_demo_financial"},
                },
            },
            "handler": workflow_export_diagram,
        },
    ]
