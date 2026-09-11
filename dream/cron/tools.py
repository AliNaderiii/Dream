"""Agent tools for creating and managing autonomous scheduled tasks and reminders."""

from __future__ import annotations

import json
import logging

from dream.cron.engine import CronSchedulerEngine
from dream.tools.base import tool

logger = logging.getLogger(__name__)

_GLOBAL_SCHEDULER_ENGINE: CronSchedulerEngine | None = None


def get_scheduler_engine() -> CronSchedulerEngine:
    """Retrieve or initialize singleton CronSchedulerEngine."""
    global _GLOBAL_SCHEDULER_ENGINE
    if _GLOBAL_SCHEDULER_ENGINE is None:
        _GLOBAL_SCHEDULER_ENGINE = CronSchedulerEngine()
    return _GLOBAL_SCHEDULER_ENGINE


def reset_scheduler_engine() -> None:
    """Reset global CronSchedulerEngine instance for isolated testing."""
    global _GLOBAL_SCHEDULER_ENGINE
    _GLOBAL_SCHEDULER_ENGINE = None


@tool(risk="guarded")
def schedule_task(
    prompt: str,
    timing: str,
    delivery_target: str = "local",
    name: str = "",
) -> str:
    """Create a persistent scheduled task running on a natural-language or cron schedule.

    :param prompt: The task instruction or query to execute autonomously.
    :param timing: Schedule in Persian/English (e.g. 'هر روز ساعت ۹ صبح', '0 9 * * 1').
    :param delivery_target: Destination (e.g. 'telegram:12345', 'discord:C1', 'local').
    :param name: Optional mnemonic label for the task.
    """
    engine = get_scheduler_engine()
    try:
        task = engine.schedule_task(
            prompt=prompt,
            timing=timing,
            delivery_target=delivery_target,
            name=name,
        )
        return json.dumps(
            {
                "schedule_id": task.id,
                "name": task.name,
                "cron_expression": task.cron_expr,
                "description": task.description,
                "delivery_target": task.delivery.to_dict(),
                "message": f"Task '{task.name}' scheduled successfully on '{task.cron_expr}'.",
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return json.dumps(
            {"error": f"خطا در ایجاد زمان‌بندی: {exc}"},
            ensure_ascii=False,
        )


@tool(risk="safe")
def list_schedules() -> str:
    """List all configured recurring scheduled tasks and their status."""
    engine = get_scheduler_engine()
    tasks = [t.to_dict() for t in engine.list_tasks()]
    return json.dumps({"schedules": tasks, "count": len(tasks)}, ensure_ascii=False, indent=2)


@tool(risk="guarded")
def cancel_schedule(schedule_id: str) -> str:
    """Cancel and delete a scheduled recurring task.

    :param schedule_id: ID of the schedule to remove.
    """
    engine = get_scheduler_engine()
    ok = engine.delete_task(schedule_id)
    if ok:
        return f"زمان‌بندی با شناسه '{schedule_id}' با موفقیت حذف شد."
    return f"زمان‌بندی با شناسه '{schedule_id}' یافت نشد."


@tool(risk="guarded")
def trigger_schedule(schedule_id: str) -> str:
    """Manually trigger an immediate execution of a scheduled task.

    :param schedule_id: ID of the schedule to run now.
    """
    engine = get_scheduler_engine()
    res = engine.trigger_task(schedule_id)
    return json.dumps(res, ensure_ascii=False, indent=2)
