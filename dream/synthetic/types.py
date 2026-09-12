"""Data models and type definitions for Synthetic Data Engine and DPO Distillation."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DatasetFormat(str, Enum):
    """Output serialization formats for LLM Fine-Tuning & Distillation."""

    SHAREGPT = "sharegpt"
    DPO = "dpo"
    KTO = "kto"
    ALPACA = "alpaca"
    COT_REASONING = "cot_reasoning"


class SampleQualityTier(str, Enum):
    """Quality classification tier for synthetic samples."""

    PRISTINE = "pristine"  # Score >= 0.90
    HIGH = "high"          # Score >= 0.75
    ACCEPTABLE = "acceptable"  # Score >= 0.60
    REJECTED = "rejected"  # Score < 0.60


@dataclass
class SyntheticSample:
    """Individual synthetic training instance with reasoning and preference pairs."""

    sample_id: str
    prompt: str
    chosen_response: str
    rejected_response: str = ""
    reasoning_trace: str = ""
    format: DatasetFormat = DatasetFormat.DPO
    quality_score: float = 0.95
    quality_tier: SampleQualityTier = SampleQualityTier.PRISTINE
    language: str = "fa"  # "fa", "en", "multilingual"
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize sample to dictionary."""
        return {
            "sample_id": self.sample_id,
            "prompt": self.prompt,
            "chosen_response": self.chosen_response,
            "rejected_response": self.rejected_response,
            "reasoning_trace": self.reasoning_trace,
            "format": self.format.value,
            "quality_score": round(self.quality_score, 4),
            "quality_tier": self.quality_tier.value,
            "language": self.language,
            "tags": self.tags,
            "metadata": self.metadata,
            "created_at": round(self.created_at, 2),
        }


@dataclass
class FilterCriteria:
    """Quality and decontamination filter rules for dataset curation."""

    min_quality_score: float = 0.70
    min_reasoning_length_chars: int = 20
    deduplication_threshold: float = 0.85
    require_persian_fluency: bool = False
    exclude_rejected_empty: bool = False
    target_languages: list[str] = field(default_factory=lambda: ["fa", "en"])


@dataclass
class DistillationBatch:
    """Group of synthetic samples processed and prepared for training export."""

    batch_id: str
    sample_count: int
    samples: list[SyntheticSample] = field(default_factory=list)
    average_quality: float = 0.90
    format: DatasetFormat = DatasetFormat.DPO
    summary_fa: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize batch to dictionary."""
        return {
            "batch_id": self.batch_id,
            "sample_count": self.sample_count,
            "average_quality": round(self.average_quality, 4),
            "format": self.format.value,
            "summary_fa": self.summary_fa,
            "created_at": round(self.created_at, 2),
            "samples": [s.to_dict() for s in self.samples],
        }


@dataclass
class SyntheticDatasetExport:
    """Result of exporting curated dataset to JSONL / disk."""

    export_id: str
    format: DatasetFormat
    total_samples: int
    jsonl_content: str
    file_path: str = ""
    summary_fa: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize export result to dictionary."""
        return {
            "export_id": self.export_id,
            "format": self.format.value,
            "total_samples": self.total_samples,
            "file_path": self.file_path,
            "summary_fa": self.summary_fa,
            "content_length_chars": len(self.jsonl_content),
        }
