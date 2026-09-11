"""Slash command handler for managing schedules, cron tasks, and reminders."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from dream.cron.engine import _to_jalali_str
from dream.cron.tools import get_scheduler_engine


def handle_schedule_command(args: str, output: Callable[[str], None] = print) -> bool:
    """Process `/schedule` or `/cron` slash commands.

    Usage:
        /schedule
        /schedule list
        /schedule add "<prompt>" every <timing> [target]
        /schedule pause <id>
        /schedule resume <id>
        /schedule delete <id>
        /schedule run <id>
    """
    parts = args.strip().split()
    engine = get_scheduler_engine()

    if not parts or parts[0].lower() in ("list", "status"):
        tasks = engine.list_tasks()
        if not tasks:
            output(
                "⏰ **هیچ تسک زمان‌بندی‌شده‌ای فعال نیست.**\n"
                "برای ثبت تسک: `/schedule add \"گزارش وضعیت\" every day at 09:00 telegram:123`"
            )
            return True

        output(f"⏰ **فهرست تسک‌های زمان‌بندی‌شده سیستم ({len(tasks)} تسک):**\n")
        for t in tasks:
            icon = "🟢" if t.enabled else "⚪"
            next_jalali = (
                _to_jalali_str(datetime.fromtimestamp(t.next_run_at))
                if t.next_run_at
                else "نامشخص"
            )
            target_str = (
                f"{t.delivery.platform}:{t.delivery.target_id}"
                if t.delivery.target_id
                else t.delivery.platform
            )
            output(
                f"  {icon} **{t.name}** (`{t.id}`)\n"
                f"     پرامپت: {t.prompt}\n"
                f"     الگوی کرون: `{t.cron_expr}` ({t.description})\n"
                f"     موعد اجرای بعدی (شمسی): **{next_jalali}** | مقصد: `{target_str}`\n"
            )
        return True

    action = parts[0].lower()

    if action in ("add", "create") and len(parts) >= 3:
        # Reconstruct text
        raw_rest = " ".join(parts[1:])
        # Format might be: "prompt text" every monday at 9am [target]
        prompt = ""
        timing = ""
        target = "local"

        if '"' in raw_rest:
            first_quote = raw_rest.find('"')
            second_quote = raw_rest.find('"', first_quote + 1)
            if second_quote != -1:
                prompt = raw_rest[first_quote + 1 : second_quote]
                rem = raw_rest[second_quote + 1 :].strip()
                if rem.startswith("every"):
                    rem = rem[5:].strip()
                timing = rem
        else:
            prompt = parts[1]
            timing = " ".join(parts[2:])

        try:
            task = engine.schedule_task(prompt=prompt, timing=timing, delivery_target=target)
            output(
                f"✅ **تسک زمان‌بندی‌شده با موفقیت ثبت شد:**\n"
                f"  • نام/شناسه: **{task.name}** (`{task.id}`)\n"
                f"  • فرمت کرون: `{task.cron_expr}` ({task.description})\n"
            )
            return True
        except Exception as exc:
            output(f"❌ خطا در ایجاد زمان‌بندی: {exc}")
            return True

    if action == "pause" and len(parts) > 1:
        tid = parts[1]
        ok = engine.pause_task(tid)
        if ok:
            output(f"⏸️ تسک زمان‌بندی‌شده `{tid}` متوقف شد.")
        else:
            output(f"❌ تسک با شناسه `{tid}` یافت نشد.")
        return True

    if action == "resume" and len(parts) > 1:
        tid = parts[1]
        ok = engine.resume_task(tid)
        if ok:
            output(f"▶️ اجرای تسک زمان‌بندی‌شده `{tid}` از سر گرفته شد.")
        else:
            output(f"❌ تسک با شناسه `{tid}` یافت نشد.")
        return True

    if action in ("delete", "remove", "cancel") and len(parts) > 1:
        tid = parts[1]
        ok = engine.delete_task(tid)
        if ok:
            output(f"🗑️ تسک زمان‌بندی‌شده `{tid}` حذف شد.")
        else:
            output(f"❌ تسک با شناسه `{tid}` یافت نشد.")
        return True

    if action in ("run", "trigger") and len(parts) > 1:
        tid = parts[1]
        res = engine.trigger_task(tid)
        if res.get("ok"):
            output(f"🚀 تسک `{tid}` با موفقیت اجرا شد.\nنتیجه:\n{res.get('result')}")
        else:
            output(f"❌ خطا در اجرای تسک: {res.get('error')}")
        return True

    output(
        "راهنمای دستورات زمان‌بندی / Schedule Command Help:\n"
        "  /schedule\n"
        "  /schedule list\n"
        "  /schedule add \"<prompt>\" every <timing> [target]\n"
        "  /schedule pause <id>\n"
        "  /schedule resume <id>\n"
        "  /schedule delete <id>\n"
        "  /schedule run <id>"
    )
    return True
