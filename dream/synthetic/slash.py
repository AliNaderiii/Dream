"""Slash command dispatcher for Synthetic Data Generation & DPO Distillation."""

from __future__ import annotations

import shlex

from dream.synthetic.engine import get_synthetic_engine


def handle_synthetic_command(args_str: str) -> str:
    """Handle /synthetic slash commands.

    Usage:
        /synthetic generate <topic1,topic2> [count]
        /synthetic curate [min_score]
        /synthetic export [format]
        /synthetic metrics
        /synthetic reset
    """
    if not args_str.strip():
        return (
            "🧪 **راهنمای دستورات موتور داده‌های سنتتیک (Synthetic Data & DPO Engine):**\n\n"
            "- `/synthetic generate <t1,t2> [count]` : تولید دسته‌ای نمونه‌های آموزشی DPO/SFT\n"
            "- `/synthetic curate [min_score]` : پالایش، حذف تکراری‌ها و فیلتر کیفی\n"
            "- `/synthetic export [format]` : صادرات دیتاست به فرمت JSONL (dpo, sharegpt, alpaca)\n"
            "- `/synthetic metrics` : مشاهده آمار و وضعیت استخر داده‌ها\n"
            "- `/synthetic reset` : بازنشانی استخر نمونه‌های سنتتیک"
        )

    try:
        parts = shlex.split(args_str)
    except ValueError:
        parts = args_str.split()

    subcmd = parts[0].lower()
    engine = get_synthetic_engine()

    if subcmd == "generate":
        if len(parts) < 2:
            return "❌ موضوعات را مشخص کنید: `/synthetic generate معماری_عامل,بینایی [count]`"
        topics = [t.strip() for t in parts[1].split(",") if t.strip()]
        cnt = int(parts[2]) if len(parts) > 2 else 2
        batch = engine.generate_batch(seed_topics=topics, count_per_topic=cnt, language="fa")
        return (
            f"✅ **تولید دسته `{batch.batch_id}` با موفقیت انجام شد.**\n"
            f"- تعداد: `{batch.sample_count}` | میانگین کیفیت: `{batch.average_quality:.2f}`\n"
            f"- نمونه پرامپت: {batch.samples[0].prompt[:60]}..."
        )

    elif subcmd == "curate":
        min_q = float(parts[1]) if len(parts) > 1 else 0.70
        res = engine.curate_and_filter(min_quality_score=min_q, require_persian=True)
        m = res["metrics"]
        return (
            f"🧹 **عملیات پالایش داده‌ها با موفقیت انجام شد:**\n"
            f"- نمونه‌های اولیه: `{m['total_input_samples']}` | تایید شده: `{m['accepted_count']}`\n"
            f"- نمونه‌های حذف‌شده: `{m['rejected_count']}` | ماندگاری: `{m['retention_rate_pct']}%`\n"
            f"- میانگین نمره کیفیت: `{m['average_quality_score']:.2f}`"
        )

    elif subcmd == "export":
        fmt = parts[1] if len(parts) > 1 else "dpo"
        exp = engine.export_dataset(target_format=fmt)
        return (
            f"📦 **صادرات دیتاست به فرمت `{exp.format.value}` آماده شد:**\n"
            f"- تعداد نمونه‌ها: `{exp.total_samples}` | شناسه: `{exp.export_id}`\n"
            f"- حجم خروجی: `{exp.to_dict()['content_length_chars']:,}` کاراکتر."
        )

    elif subcmd in ("metrics", "stats"):
        m = engine.get_metrics()
        return (
            f"📊 **تله‌متری موتور داده‌های سنتتیک:**\n"
            f"- کل نمونه‌های تولیدشده: `{m['total_generated_samples']}`\n"
            f"- نمونه‌های فعال در استخر: `{m['active_samples_in_pool']}`\n"
            f"- دسته‌های ایجادشده: `{m['total_batches_created']}`\n"
            f"- آپ‌تایم: `{m['uptime_sec']}s`"
        )

    elif subcmd == "reset":
        engine.reset()
        return "🔄 **استخر داده‌های سنتتیک بازنشانی شد.**"

    return f"❌ دستور ناآشنا: `{subcmd}`. برای راهنما `/synthetic` را وارد کنید."
