"""Comprehensive test suite for Autonomous Cron Scheduling and Delivery Dispatcher."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from dream.cron.engine import CronSchedulerEngine
from dream.cron.parser import describe_cron, parse_cron
from dream.cron.slash import handle_schedule_command
from dream.cron.tools import (
    cancel_schedule,
    get_scheduler_engine,
    list_schedules,
    reset_scheduler_engine,
    schedule_task,
    trigger_schedule,
)
from dream.gateway.delivery import GatewayDeliveryRouter
from dream.tools.toolsets import filter_tools, get_toolset


def test_cron_parsing_and_natural_language():
    """Verify parsing standard cron and Persian/English natural language expressions."""
    # Standard 5-field cron
    expr = parse_cron("0 9 * * 1")
    assert expr.expression == "0 9 * * 1"
    assert describe_cron("0 9 * * 1") == "every Monday at 9:00 AM"

    # Persian natural language via engine
    engine = CronSchedulerEngine()
    task = engine.schedule_task(
        prompt="گزارش روزانه",
        timing="هر روز ساعت ۹ صبح",
        delivery_target="telegram:123456",
        name="daily_report",
    )
    assert task.cron_expr == "0 9 * * *"
    assert task.delivery.platform == "telegram"
    assert task.delivery.target_id == "123456"
    assert task.next_run_at is not None


def test_scheduler_lifecycle_and_execution():
    """Verify pausing, resuming, triggering, and deleting scheduled tasks."""
    mock_router = MagicMock(spec=GatewayDeliveryRouter)
    engine = CronSchedulerEngine(delivery_router=mock_router)

    task = engine.schedule_task(
        prompt="بررسی سرورها",
        timing="every monday at 10am",
        delivery_target="discord:general_channel",
        name="server_check",
    )
    assert task.enabled is True

    # Pause
    assert engine.pause_task(task.id) is True
    assert task.enabled is False

    # Resume
    assert engine.resume_task(task.id) is True
    assert task.enabled is True

    # Trigger now with custom runner
    res = engine.trigger_task(task.id, runner_fn=lambda p: f"Output for: {p}")
    assert res["ok"] is True
    assert res["result"] == "Output for: بررسی سرورها"
    assert task.runs_count == 1
    assert task.last_status == "completed"

    # Verify delivery dispatch was called
    mock_router.send_text.assert_called_once()

    # Delete
    assert engine.delete_task(task.id) is True
    assert len(engine.list_tasks()) == 0


def test_scheduler_agent_tools():
    """Verify agent tools for managing schedules."""
    reset_scheduler_engine()
    _ = get_scheduler_engine()

    # Tool: schedule_task
    res_json = schedule_task(
        prompt="یادآوری ارسال فاکتور",
        timing="0 14 * * 6",
        delivery_target="slack:accounting",
        name="invoice_reminder",
    )
    data = json.loads(res_json)
    assert "schedule_id" in data
    sid = data["schedule_id"]

    # Tool: list_schedules
    list_json = list_schedules()
    list_data = json.loads(list_json)
    assert list_data["count"] >= 1
    assert any(t["id"] == sid for t in list_data["schedules"])

    # Tool: trigger_schedule
    trig_json = trigger_schedule(sid)
    trig_data = json.loads(trig_json)
    assert trig_data["ok"] is True

    # Tool: cancel_schedule
    cancel_res = cancel_schedule(sid)
    assert "با موفقیت حذف شد" in cancel_res


def test_schedule_slash_commands():
    """Verify `/schedule` interactive slash commands."""
    reset_scheduler_engine()
    _ = get_scheduler_engine()

    outputs: list[str] = []

    # /schedule add
    handle_schedule_command(
        'add "خلاصه ایمیل‌ها" every day at 08:30', output=outputs.append
    )
    assert any("با موفقیت ثبت شد" in out for out in outputs)

    # /schedule list
    outputs.clear()
    handle_schedule_command("list", output=outputs.append)
    assert any("فهرست تسک‌های زمان‌بندی‌شده" in out for out in outputs)


def test_scheduler_toolset_registration():
    """Verify scheduler toolset registration."""
    ts = get_toolset("scheduler")
    assert ts is not None
    assert "schedule_task" in ts.tools
    assert "list_schedules" in ts.tools

    filtered = filter_tools(toolsets=["scheduler"])
    assert "schedule_task" in filtered
    assert "cancel_schedule" in filtered
