"""Unit and integration tests for Long-Horizon Workflow & Saga Orchestrator Subsystem."""

from __future__ import annotations

import pytest

from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset
from dream.workflow import (
    CheckpointManager,
    SagaOrchestrator,
    StepExecutionStatus,
    WorkflowEngine,
    WorkflowStatus,
    WorkflowStep,
    get_workflow_tools,
    handle_workflow_slash_command,
    reset_global_workflow_engine,
    workflow_create_plan,
    workflow_execute_step,
    workflow_export_diagram,
    workflow_get_status,
    workflow_rollback,
)


@pytest.fixture(autouse=True)
def cleanup_workflow_engine() -> None:
    reset_global_workflow_engine()
    yield
    reset_global_workflow_engine()


def test_toolset_includes_workflow() -> None:
    """Verify workflow toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("workflow")
    assert ts is not None
    assert "workflow_create_plan" in ts.tools
    assert "workflow_execute_step" in ts.tools
    assert "workflow_approve_step" in ts.tools
    assert "workflow_rollback" in ts.tools
    assert "workflow" in BUILTIN_TOOLSETS


def test_saga_forward_and_checkpoint_execution() -> None:
    """Verify forward step execution, state machine advance, and checkpointing."""
    checkpoints = CheckpointManager()
    saga = SagaOrchestrator(checkpoint_manager=checkpoints)
    engine = WorkflowEngine(saga=saga, checkpoint_manager=checkpoints)

    steps = [
        WorkflowStep(
            step_id="s1",
            name_fa="مرحله اول",
            action_tool="action_one",
            action_payload={"key": "val1"},
        ),
        WorkflowStep(
            step_id="s2",
            name_fa="مرحله دوم",
            action_tool="action_two",
            action_payload={"key": "val2"},
        ),
    ]
    wf = engine.create_workflow("گردش‌کار تست", "توضیحات", steps=steps, workflow_id="wf_t1")

    # Step 1
    st1 = engine.execute_next_step(wf.workflow_id)
    assert st1.status == StepExecutionStatus.SUCCESS
    assert wf.current_step_index == 1
    assert len(wf.checkpoints) == 1

    # Step 2
    st2 = engine.execute_next_step(wf.workflow_id)
    assert st2.status == StepExecutionStatus.SUCCESS
    assert wf.current_step_index == 2
    assert wf.status == WorkflowStatus.COMPLETED
    assert len(wf.checkpoints) == 2


def test_human_in_the_loop_approval_gate() -> None:
    """Verify workflow pauses when encountering human approval gate and resumes."""
    engine = WorkflowEngine()

    steps = [
        WorkflowStep(
            step_id="step_auto",
            name_fa="پردازش خودکار",
            action_tool="auto_tool",
            requires_human_approval=False,
        ),
        WorkflowStep(
            step_id="step_gate",
            name_fa="تأیید مدیر",
            action_tool="admin_action",
            requires_human_approval=True,
        ),
    ]
    wf = engine.create_workflow("گردش‌کار تأییدیه", "توضیح", steps=steps, workflow_id="wf_gate")

    # Step 1 executes automatically
    engine.execute_next_step(wf.workflow_id)
    assert wf.status == WorkflowStatus.RUNNING

    # Step 2 hits approval gate
    engine.execute_next_step(wf.workflow_id)
    assert wf.status == WorkflowStatus.PAUSED_APPROVAL

    # Grant approval and resume
    res_app = engine.approve_step(wf.workflow_id)
    assert res_app.status == StepExecutionStatus.SUCCESS
    assert wf.status == WorkflowStatus.COMPLETED


def test_saga_backward_compensation_rollback_on_failure() -> None:
    """Verify Saga backward compensation when an unrecoverable step failure occurs."""
    compensated_log: list[str] = []

    def mock_executor(tool_name: str, payload: dict) -> dict:
        if tool_name == "failing_tool":
            raise RuntimeError("Database connection timed out")
        if tool_name == "rollback_step_1":
            compensated_log.append("compensated_s1")
        return {"status": "ok", "tool": tool_name}

    saga = SagaOrchestrator(tool_executor=mock_executor)
    engine = WorkflowEngine(saga=saga)

    steps = [
        WorkflowStep(
            step_id="s1_deposit",
            name_fa="واریز اولیه",
            action_tool="deposit_step_1",
            compensation_tool="rollback_step_1",
            requires_human_approval=False,
        ),
        WorkflowStep(
            step_id="s2_fail",
            name_fa="مرحله خطا",
            action_tool="failing_tool",
            retry_limit=1,
            requires_human_approval=False,
        ),
    ]
    wf = engine.create_workflow("تست خطا و بازگشت", "توضیح", steps=steps, workflow_id="wf_fail")

    # Run all steps
    rep = engine.run_all(wf.workflow_id)
    assert rep.status == WorkflowStatus.ROLLED_BACK
    assert wf.steps[0].status == StepExecutionStatus.COMPENSATED
    assert "compensated_s1" in compensated_log
    assert "s1_deposit" in rep.rolled_back_steps


def test_workflow_engine_diagram_and_listing() -> None:
    """Verify visual diagram generation and workflow catalog."""
    engine = WorkflowEngine()

    diagram = engine.format_diagram("wf_demo_financial")
    assert "نمودار اجرای گردش‌کار" in diagram
    assert "[START]" in diagram
    assert "جبران‌ساز" in diagram

    wfs = engine.list_workflows()
    assert len(wfs) >= 1
    assert any(w["workflow_id"] == "wf_demo_financial" for w in wfs)


def test_workflow_tools_and_slash_commands() -> None:
    """Verify LLM agent tools and /workflow slash command handlers."""
    tools = get_workflow_tools()
    assert len(tools) >= 6

    # Tool: create plan
    steps_data = [
        {"step_id": "p1", "name_fa": "قدم ۱", "action_tool": "echo"},
        {"step_id": "p2", "name_fa": "قدم ۲", "action_tool": "echo"},
    ]
    res_plan = workflow_create_plan(
        name="برنامه جدید",
        description_fa="توضیحات برنامه",
        steps_data=steps_data,
    )
    assert res_plan["success"] is True
    wf_id = res_plan["workflow_id"]

    # Tool: execute step
    res_step = workflow_execute_step(wf_id)
    assert res_step["success"] is True
    assert res_step["step"]["status"] == "success"

    # Tool: diagram
    res_diag = workflow_export_diagram(wf_id)
    assert res_diag["success"] is True
    assert "نمودار اجرای گردش‌کار" in res_diag["diagram_markdown"]

    # Tool: status
    res_stat = workflow_get_status(wf_id)
    assert res_stat["success"] is True
    assert res_stat["workflow"]["total_steps"] == 2

    # Tool: rollback
    res_rb = workflow_rollback(wf_id)
    assert res_rb["success"] is True

    # Slash: /workflow
    slash_help = handle_workflow_slash_command("/workflow")
    assert "راهنمای دستورات مدیریت گردش‌کار" in slash_help

    # Slash: /workflow list
    slash_list = handle_workflow_slash_command("/workflow list")
    assert "گردش‌کارهای ثبت‌شده" in slash_list

    # Slash: /workflow run
    slash_run = handle_workflow_slash_command(f"/workflow run {wf_id}")
    assert "پایان اجرای گردش‌کار" in slash_run

    # Slash: /workflow approve
    slash_app = handle_workflow_slash_command("/workflow approve wf_demo_financial")
    assert "تاییدیه" in slash_app or "خطا" in slash_app

    # Slash: /workflow diagram
    slash_d = handle_workflow_slash_command(f"/workflow diagram {wf_id}")
    assert "نمودار اجرای گردش‌کار" in slash_d

    # Slash: /workflow status
    slash_s = handle_workflow_slash_command(f"/workflow status {wf_id}")
    assert "وضعیت گردش‌کار" in slash_s

    # Slash: /workflow rollback
    slash_r = handle_workflow_slash_command(f"/workflow rollback {wf_id}")
    assert "بازگشت" in slash_r

    # Slash: /workflow reset
    slash_reset = handle_workflow_slash_command("/workflow reset")
    assert "بازنشانی شد" in slash_reset
