"""Master Engine for Autonomous Synthetic Data Generation and DPO Distillation."""

from __future__ import annotations

import time
import uuid
from typing import Any

from dream.synthetic.curator import DatasetCurator
from dream.synthetic.exporter import DatasetExporter
from dream.synthetic.generator import SyntheticGenerator
from dream.synthetic.types import (
    DatasetFormat,
    DistillationBatch,
    FilterCriteria,
    SyntheticDatasetExport,
    SyntheticSample,
)


class SyntheticEngine:
    """Orchestrates end-to-end synthetic dataset generation, curation, and DPO exports."""

    def __init__(self) -> None:
        self.generator = SyntheticGenerator()
        self.curator = DatasetCurator()
        self.exporter = DatasetExporter()
        self.samples: dict[str, SyntheticSample] = {}
        self.batches: dict[str, DistillationBatch] = {}
        self._start_time = time.time()
        self._total_generated_count = 0

    def generate_batch(
        self,
        seed_topics: list[str],
        count_per_topic: int = 2,
        language: str = "fa",
    ) -> DistillationBatch:
        """Generate and store a batch of synthetic samples."""
        generated = self.generator.generate_trajectory_batch(
            seed_topics=seed_topics,
            count_per_topic=count_per_topic,
            language=language,
        )
        for s in generated:
            self.samples[s.sample_id] = s

        self._total_generated_count += len(generated)
        batch_id = f"bat-{uuid.uuid4().hex[:6]}"
        avg_q = sum(s.quality_score for s in generated) / max(1, len(generated))

        batch = DistillationBatch(
            batch_id=batch_id,
            sample_count=len(generated),
            samples=generated,
            average_quality=avg_q,
            format=DatasetFormat.DPO,
            summary_fa=f"دسته `{batch_id}` شامل {len(generated)} نمونه DPO تولید شد.",
        )
        self.batches[batch_id] = batch
        return batch

    def curate_and_filter(
        self,
        min_quality_score: float = 0.70,
        require_persian: bool = False,
    ) -> dict[str, Any]:
        """Run curation and filtering on all stored samples."""
        criteria = FilterCriteria(
            min_quality_score=min_quality_score,
            require_persian_fluency=require_persian,
        )
        all_samples = list(self.samples.values())
        accepted, rejected, metrics = self.curator.curate_and_filter(all_samples, criteria)

        # Update stored pool with accepted
        self.samples = {s.sample_id: s for s in accepted}
        return {
            "success": True,
            "metrics": metrics,
            "retained_samples_count": len(accepted),
            "rejected_samples_count": len(rejected),
        }

    def export_dataset(
        self,
        target_format: str = "dpo",
        file_path: str = "",
    ) -> SyntheticDatasetExport:
        """Export curated samples into target JSONL format."""
        try:
            fmt_enum = DatasetFormat(target_format.lower())
        except ValueError:
            fmt_enum = DatasetFormat.DPO

        return self.exporter.export_to_jsonl(
            samples=list(self.samples.values()),
            target_format=fmt_enum,
            file_path=file_path,
        )

    def get_metrics(self) -> dict[str, Any]:
        """Return operational telemetry of the Synthetic Data subsystem."""
        uptime = time.time() - self._start_time
        return {
            "uptime_sec": round(uptime, 2),
            "total_generated_samples": self._total_generated_count,
            "active_samples_in_pool": len(self.samples),
            "total_batches_created": len(self.batches),
            "status": "healthy",
        }

    def reset(self) -> None:
        """Reset synthetic sample pool and history."""
        self.samples.clear()
        self.batches.clear()
        self._total_generated_count = 0


# Global Singleton
_GLOBAL_SYNTHETIC_ENGINE: SyntheticEngine | None = None


def get_synthetic_engine() -> SyntheticEngine:
    """Retrieve global singleton SyntheticEngine instance."""
    global _GLOBAL_SYNTHETIC_ENGINE
    if _GLOBAL_SYNTHETIC_ENGINE is None:
        _GLOBAL_SYNTHETIC_ENGINE = SyntheticEngine()
    return _GLOBAL_SYNTHETIC_ENGINE
