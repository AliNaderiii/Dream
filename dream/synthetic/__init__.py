"""Autonomous Synthetic Data Engine & Continuous DPO Distillation Pipeline for Dream."""

from __future__ import annotations

from dream.synthetic.curator import DatasetCurator
from dream.synthetic.engine import SyntheticEngine, get_synthetic_engine
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
    DistillationBatch,
    FilterCriteria,
    SampleQualityTier,
    SyntheticDatasetExport,
    SyntheticSample,
)

__all__ = [
    "DatasetCurator",
    "DatasetExporter",
    "DatasetFormat",
    "DistillationBatch",
    "FilterCriteria",
    "SampleQualityTier",
    "SyntheticDatasetExport",
    "SyntheticEngine",
    "SyntheticGenerator",
    "SyntheticSample",
    "get_global_synthetic_engine",
    "get_synthetic_engine",
    "get_synthetic_tools",
    "handle_synthetic_command",
    "reset_global_synthetic_engine",
    "synthetic_curate_and_filter",
    "synthetic_export_dataset",
    "synthetic_generate_samples",
    "synthetic_get_batch_status",
    "synthetic_get_metrics",
    "synthetic_reset",
]
