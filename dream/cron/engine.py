"""Autonomous scheduler engine with natural-language parsing and multi-channel delivery."""

from __future__ import annotations

import logging
import secrets
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from dream.cron.parser import describe_cron, next_run_after, parse_cron
from dream.cron.types import DeliveryTargetConfig, ScheduledTaskRecord
from dream.nl_schedule import nl_to_cron

logger = logging.getLogger(__name__)


def _to_jalali_str(dt: datetime) -> str:
    """Format datetime into approximate Jalali date string for UI display."""
    g_year, g_month, g_day = dt.year, dt.month, dt.day
    j_year = g_year - 621 if (g_month > 3 or (g_month == 3 and g_day >= 21)) else g_year - 622
    return f"{j_year:04d}/{g_month:02d}/{g_day:02d} {dt.strftime('%H:%M')}"


class CronSchedulerEngine:
    """Manages scheduled tasks lifecycle, cron evaluation, and multi-platform delivery routing."""

    def __init__(self, delivery_router: Any | None = None) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[str, ScheduledTaskRecord] = {}
        self.delivery_router = delivery_router

    def schedule_task(
        self,
        prompt: str,
        timing: str,
        delivery_target: str | DeliveryTargetConfig = "local",
        name: str = "",
    ) -> ScheduledTaskRecord:
        """Create and register a new scheduled task from natural language or cron expression."""
        timing_clean = timing.strip()
        cron_expr = ""

        # Try raw 5-field cron first
        try:
            parsed = parse_cron(timing_clean)
            cron_expr = parsed.expression
        except ValueError:
            # Try natural language parsing (Persian or English)
            try:
                cron_expr = nl_to_cron(timing_clean)
            except Exception as exc:
                raise ValueError(
                    f"زمان‌بندی نامعتبر است: '{timing}'. "
                    f"لطفاً به صورت عبارات فارسی/انگلیسی یا فرمت کرون وارد کنید. (خطا: {exc})"
                ) from exc

        # Calculate next fire time
        now = datetime.now()
        next_dt = next_run_after(cron_expr, now)
        desc = describe_cron(cron_expr)

        delivery_cfg = (
            DeliveryTargetConfig.from_str(delivery_target)
            if isinstance(delivery_target, str)
            else delivery_target
        )

        task_id = f"cron_{secrets.token_hex(6)}"
        task = ScheduledTaskRecord(
            id=task_id,
            prompt=prompt,
            cron_expr=cron_expr,
            description=desc,
            delivery=delivery_cfg,
            name=name or f"task_{task_id[5:]}",
            enabled=True,
            created_at=time.time(),
            next_run_at=next_dt.timestamp(),
        )

        with self._lock:
            self._tasks[task_id] = task

        logger.info(f"Scheduled task '{task.name}' ({task.id}) on cron '{cron_expr}'.")
        return task

    def list_tasks(self) -> list[ScheduledTaskRecord]:
        """List all registered scheduled tasks."""
        with self._lock:
            return list(self._tasks.values())

    def get_task(self, task_id: str) -> ScheduledTaskRecord | None:
        """Retrieve a task by ID."""
        with self._lock:
            return self._tasks.get(task_id)

    def pause_task(self, task_id: str) -> bool:
        """Pause execution of a scheduled task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.enabled = False
                return True
            return False

    def resume_task(self, task_id: str) -> bool:
        """Resume a paused scheduled task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.enabled = True
                now = datetime.now()
                next_dt = next_run_after(task.cron_expr, now)
                task.next_run_at = next_dt.timestamp()
                return True
            return False

    def delete_task(self, task_id: str) -> bool:
        """Delete a scheduled task."""
        with self._lock:
            return self._tasks.pop(task_id, None) is not None

    def trigger_task(
        self,
        task_id: str,
        runner_fn: Callable[[str], str] | None = None,
    ) -> dict[str, Any]:
        """Manually execute a scheduled task and route output to its delivery target."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return {"ok": False, "error": f"Task '{task_id}' not found"}

        started = time.time()
        result_text = ""
        error_msg = None

        try:
            if runner_fn:
                result_text = runner_fn(task.prompt)
            else:
                now_str = datetime.now(timezone.utc).isoformat()
                result_text = (
                    f"[Scheduled task '{task.name}' executed successfully at {now_str}]"
                )

            # Route to delivery target if available
            self._dispatch_delivery(task, result_text)
            status = "completed"

        except Exception as exc:
            logger.error(f"Execution error for scheduled task '{task.id}': {exc}")
            error_msg = str(exc)
            status = "failed"

        # Update task stats
        with self._lock:
            task.last_run_at = started
            task.runs_count += 1
            task.last_status = status
            task.last_result = result_text if status == "completed" else None
            task.last_error = error_msg
            now = datetime.now()
            next_dt = next_run_after(task.cron_expr, now)
            task.next_run_at = next_dt.timestamp()

        return {
            "ok": status == "completed",
            "task_id": task.id,
            "status": status,
            "result": result_text,
            "error": error_msg,
            "delivery_target": task.delivery.to_dict(),
        }

    def _dispatch_delivery(self, task: ScheduledTaskRecord, message_text: str) -> None:
        """Dispatch task execution result to target platform router."""
        target = task.delivery
        if not target or target.platform in ("local", "none"):
            return

        if not self.delivery_router:
            logger.info(
                f"Delivering output for task '{task.id}' to {target.platform}:{target.target_id}"
            )
            return

        try:
            from dream.gateway.types import PlatformType

            plat_enum = PlatformType(target.platform)
            self.delivery_router.send_text(
                platform=plat_enum,
                recipient_id=target.target_id,
                text=message_text,
                channel_id=target.target_id,
            )
        except Exception as exc:
            logger.error(f"Failed to deliver task output to {target.platform}: {exc}")
