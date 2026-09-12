"""Comprehensive unit and integration test suite for Synthetic Data Engine & DPO Pipeline."""

from __future__ import annotations

import json

import pytest

from dream.synthetic.curator import DatasetCurator
from dream.synthetic.exporter import DatasetExporter
from dream.synthetic.generator import SyntheticGenerator
from dream.synthetic.slash import handle_synthetic_command
from dream.synthetic.tools import (
    get_global_synthetic_engine,
    get_synthetic_tools,
    reset_global_synthetic_engine,
    synthetic_curate_and_filter,
    synthetic_export_dataset,
    synthetic_generate_samples,
    synthetic_get_batch_status,
    synthetic_get_metrics,
    synthetic_reset,
)
from dream.synthetic.types import (
    DatasetFormat,
    FilterCriteria,
    SampleQualityTier,
)
from dream.tools.toolsets import get_toolset


@pytest.fixture(autouse=True)
def cleanup_synthetic() -> None:
    reset_global_synthetic_engine()
    yield
    reset_global_synthetic_engine()


def test_toolset_includes_synthetic() -> None:
    """Verify synthetic toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("synthetic")
    assert ts is not None
    assert ts.name == "synthetic"
    assert "synthetic_generate_samples" in ts.tools
    assert "synthetic_curate_and_filter" in ts.tools
    assert "synthetic_export_dataset" in ts.tools
    assert "synthetic_get_batch_status" in ts.tools


def test_synthetic_generator_dpo_and_sft() -> None:
    """Test generation of DPO pairs and SFT samples."""
    gen = SyntheticGenerator()

    # DPO
    dpo_sample = gen.generate_dpo_pair(
        prompt="چگونه یک عامل خودکار طراحی کنیم؟",
        chosen_response="برای طراحی عامل، مراحل زیر را طی می‌کنیم: ۱. ماژول حافظه، ۲. ابزارها.",
        language="fa",
    )
    assert dpo_sample.format == DatasetFormat.DPO
    assert dpo_sample.quality_tier == SampleQualityTier.PRISTINE
    assert len(dpo_sample.rejected_response) > 0
    assert len(dpo_sample.reasoning_trace) > 0

    # SFT
    sft_sample = gen.generate_sft_sample(
        instruction="توابع بازگشتی را شرح دهید.",
        response="تابع بازگشتی تابعی است که خود را فراخوانی می‌کند.",
        reasoning_trace="بررسی مفهوم بازگشت در برنامه‌نویسی",
        language="fa",
    )
    assert sft_sample.format == DatasetFormat.SHAREGPT
    assert "<thought>" in sft_sample.chosen_response

    # Trajectory Batch
    batch = gen.generate_trajectory_batch(
        seed_topics=["عامل_هوشمند", "گراف_دانش"],
        count_per_topic=2,
    )
    assert len(batch) == 4


def test_dataset_curator_and_filtering() -> None:
    """Test sample scoring, decontamination, and duplicate filtering."""
    curator = DatasetCurator()
    gen = SyntheticGenerator()

    s1 = gen.generate_dpo_pair(
        "توضیح معماری مایکروسرویس در سیستم‌های توزیع‌شده",
        "پاسخ کامل و جامع...",
        language="fa",
    )
    s2 = gen.generate_dpo_pair(
        "توضیح معماری مایکروسرویس در سیستم‌های توزیع‌شده",
        "پاسخ تکراری دیگر...",
        language="fa",
    )  # Duplicate prompt
    s3 = gen.generate_dpo_pair("کوتاه", "کم", language="fa")  # Low quality
    s3.reasoning_trace = "خیلی کوتاه"

    criteria = FilterCriteria(min_quality_score=0.75, deduplication_threshold=0.85)
    accepted, rejected, metrics = curator.curate_and_filter([s1, s2, s3], criteria)

    assert len(accepted) >= 1
    assert len(rejected) >= 1
    assert metrics["retention_rate_pct"] > 0


def test_dataset_exporter_formats() -> None:
    """Test exporting samples to standard JSONL formats (DPO, ShareGPT, Alpaca, KTO)."""
    exporter = DatasetExporter()
    gen = SyntheticGenerator()

    samples = [
        gen.generate_dpo_pair("پرسش یک", "پاسخ برتر یک", language="fa"),
        gen.generate_dpo_pair("Question 2", "Chosen response 2", language="en"),
    ]

    # 1. DPO
    exp_dpo = exporter.export_to_jsonl(samples, target_format=DatasetFormat.DPO)
    assert exp_dpo.total_samples == 2
    first_dpo = json.loads(exp_dpo.jsonl_content.splitlines()[0])
    assert "chosen" in first_dpo
    assert "rejected" in first_dpo

    # 2. ShareGPT
    exp_sg = exporter.export_to_jsonl(samples, target_format=DatasetFormat.SHAREGPT)
    first_sg = json.loads(exp_sg.jsonl_content.splitlines()[0])
    assert "conversations" in first_sg

    # 3. Alpaca
    exp_alp = exporter.export_to_jsonl(samples, target_format=DatasetFormat.ALPACA)
    first_alp = json.loads(exp_alp.jsonl_content.splitlines()[0])
    assert "instruction" in first_alp

    # 4. KTO
    exp_kto = exporter.export_to_jsonl(samples, target_format=DatasetFormat.KTO)
    assert len(exp_kto.jsonl_content.splitlines()) >= 2


def test_synthetic_engine_tools_and_slash() -> None:
    """Test master SyntheticEngine, LLM tools, and slash commands."""
    engine = get_global_synthetic_engine()

    # 1. Generate batch
    batch = engine.generate_batch(seed_topics=["معماری", "امنیت"], count_per_topic=2)
    assert batch.sample_count == 4
    assert len(engine.samples) == 4

    # 2. Curate
    cur_res = engine.curate_and_filter(min_quality_score=0.70)
    assert cur_res["success"] is True

    # 3. Export
    exp_res = engine.export_dataset(target_format="dpo")
    assert exp_res.total_samples > 0

    # 4. LLM Tools
    tools = get_synthetic_tools()
    assert len(tools) >= 4

    t_gen = synthetic_generate_samples(seed_topics=["پایگاه_داده"], count_per_topic=1)
    assert t_gen["success"] is True

    t_cur = synthetic_curate_and_filter(min_quality_score=0.70)
    assert t_cur["success"] is True

    t_exp = synthetic_export_dataset(target_format="sharegpt")
    assert t_exp["success"] is True

    t_bat = synthetic_get_batch_status(batch.batch_id)
    assert t_bat["success"] is True

    t_met = synthetic_get_metrics()
    assert t_met["success"] is True

    # 5. Slash commands
    s_help = handle_synthetic_command("")
    assert "راهنمای دستورات موتور داده‌های سنتتیک" in s_help

    s_gen = handle_synthetic_command("generate هوش_مصنوعی,شبکه 1")
    assert "تولید دسته" in s_gen

    s_cur = handle_synthetic_command("curate 0.70")
    assert "عملیات پالایش داده‌ها" in s_cur

    s_exp = handle_synthetic_command("export dpo")
    assert "صادرات دیتاست" in s_exp

    s_met = handle_synthetic_command("metrics")
    assert "تله‌متری موتور داده‌های سنتتیک" in s_met

    s_res = handle_synthetic_command("reset")
    assert "بازنشانی شد" in s_res

    # Reset tool
    t_res = synthetic_reset()
    assert t_res["success"] is True
