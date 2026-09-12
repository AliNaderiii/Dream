"""LLM Agent Tools and Toolset Definitions for Synthetic Data & DPO Distillation."""

from __future__ import annotations

import logging
from typing import Any

from dream.synthetic.engine import SyntheticEngine, get_synthetic_engine

logger = logging.getLogger(__name__)

_GLOBAL_SYNTHETIC_ENGINE: SyntheticEngine | None = None


def get_global_synthetic_engine() -> SyntheticEngine:
    """Retrieve or initialize global singleton SyntheticEngine."""
    global _GLOBAL_SYNTHETIC_ENGINE
    if _GLOBAL_SYNTHETIC_ENGINE is None:
        _GLOBAL_SYNTHETIC_ENGINE = get_synthetic_engine()
    return _GLOBAL_SYNTHETIC_ENGINE


def reset_global_synthetic_engine() -> None:
    """Reset global SyntheticEngine instance for test isolation."""
    global _GLOBAL_SYNTHETIC_ENGINE
    if _GLOBAL_SYNTHETIC_ENGINE is not None:
        _GLOBAL_SYNTHETIC_ENGINE.reset()
    _GLOBAL_SYNTHETIC_ENGINE = None


def synthetic_generate_samples(
    seed_topics: list[str],
    count_per_topic: int = 2,
    language: str = "fa",
) -> dict[str, Any]:
    """Generate synthetic SFT and DPO preference samples from seed topics.

    Args:
        seed_topics: List of domain topics or task categories to synthesize.
        count_per_topic: Number of samples per topic.
        language: Target dataset language ('fa' or 'en').
    """
    engine = get_global_synthetic_engine()
    batch = engine.generate_batch(
        seed_topics=seed_topics,
        count_per_topic=count_per_topic,
        language=language,
    )
    return {"success": True, **batch.to_dict()}


def synthetic_curate_and_filter(
    min_quality_score: float = 0.70,
    require_persian: bool = False,
) -> dict[str, Any]:
    """Filter, score, and deduplicate stored synthetic samples.

    Args:
        min_quality_score: Minimum acceptable quality threshold (0.0 to 1.0).
        require_persian: Enforce Persian script presence in prompts.
    """
    engine = get_global_synthetic_engine()
    return engine.curate_and_filter(
        min_quality_score=min_quality_score,
        require_persian=require_persian,
    )


def synthetic_export_dataset(
    target_format: str = "dpo",
    file_path: str = "",
) -> dict[str, Any]:
    """Export curated synthetic dataset to standard JSONL format.

    Args:
        target_format: Serialization format ('dpo', 'sharegpt', 'alpaca', 'kto', 'cot_reasoning').
        file_path: Optional destination file path.
    """
    engine = get_global_synthetic_engine()
    export_res = engine.export_dataset(target_format=target_format, file_path=file_path)
    return {"success": True, **export_res.to_dict()}


def synthetic_get_batch_status(batch_id: str) -> dict[str, Any]:
    """Retrieve details for a specific synthetic distillation batch.

    Args:
        batch_id: Unique batch identifier.
    """
    engine = get_global_synthetic_engine()
    batch = engine.batches.get(batch_id)
    if not batch:
        return {"success": False, "error": f"دسته `{batch_id}` یافت نشد."}
    return {"success": True, "batch": batch.to_dict()}


def synthetic_get_metrics() -> dict[str, Any]:
    """Get operational metrics of the Synthetic Data engine."""
    engine = get_global_synthetic_engine()
    return {"success": True, **engine.get_metrics()}


def synthetic_reset() -> dict[str, Any]:
    """Reset synthetic sample pool and history."""
    reset_global_synthetic_engine()
    return {"success": True, "message_fa": "موتور داده‌های سنتتیک با موفقیت بازنشانی شد."}


def get_synthetic_tools() -> list[dict[str, Any]]:
    """Return tool manifests for LLM registration."""
    return [
        {
            "name": "synthetic_generate_samples",
            "description": "Generate synthetic SFT and DPO training pairs from seed topics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seed_topics": {"type": "array"},
                    "count_per_topic": {"type": "integer", "default": 2},
                    "language": {"type": "string", "enum": ["fa", "en"], "default": "fa"},
                },
                "required": ["seed_topics"],
            },
            "handler": synthetic_generate_samples,
        },
        {
            "name": "synthetic_curate_and_filter",
            "description": "Filter, deduplicate, and score synthetic dataset samples.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_quality_score": {"type": "number", "default": 0.70},
                    "require_persian": {"type": "boolean", "default": False},
                },
            },
            "handler": synthetic_curate_and_filter,
        },
        {
            "name": "synthetic_export_dataset",
            "description": "Export synthetic samples to JSONL format (DPO, ShareGPT, Alpaca).",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_format": {
                        "type": "string",
                        "enum": ["dpo", "sharegpt", "alpaca", "kto", "cot_reasoning"],
                        "default": "dpo",
                    },
                    "file_path": {"type": "string"},
                },
            },
            "handler": synthetic_export_dataset,
        },
        {
            "name": "synthetic_get_batch_status",
            "description": "Inspect details and sample count of a distillation batch.",
            "parameters": {
                "type": "object",
                "properties": {
                    "batch_id": {"type": "string"},
                },
                "required": ["batch_id"],
            },
            "handler": synthetic_get_batch_status,
        },
    ]
