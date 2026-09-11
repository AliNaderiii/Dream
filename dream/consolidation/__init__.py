"""Autonomous Sleep-Phase Memory Consolidation, Entropy Pruning, and Epistemic Distillation Subsystem."""

from __future__ import annotations

from dream.consolidation.distiller import EpistemicDistiller
from dream.consolidation.engine import ConsolidationEngine
from dream.consolidation.pruner import EntropyPruner
from dream.consolidation.slash import handle_consolidation_slash_command
from dream.consolidation.tools import (
    consolidation_add_memory,
    consolidation_distill_session,
    consolidation_export_report,
    consolidation_get_stats,
    consolidation_reset_all,
    consolidation_run_cycle,
    get_consolidation_tools,
    get_global_consolidation_engine,
    reset_global_consolidation_engine,
)
from dream.consolidation.types import (
    ConsolidationReport,
    ConsolidationStage,
    ConsolidationStats,
    MemoryItem,
    MemoryNodeType,
)

# Auto-register consolidation toolset
try:
    from dream.tools.toolsets import Toolset, register_toolset

    register_toolset(
        Toolset(
            name="consolidation",
            description="Autonomous sleep-phase memory consolidation, Ebbinghaus decay, entropy pruning, and contradiction resolution.",
            tools=[
                "consolidation_add_memory",
                "consolidation_run_cycle",
                "consolidation_distill_session",
                "consolidation_get_stats",
                "consolidation_export_report",
                "consolidation_reset_all",
            ],
            metadata={"category": "consolidation", "builtin": True},
        )
    )
except Exception:
    pass

__all__ = [
    "ConsolidationEngine",
    "ConsolidationReport",
    "ConsolidationStage",
    "ConsolidationStats",
    "EntropyPruner",
    "EpistemicDistiller",
    "MemoryItem",
    "MemoryNodeType",
    "consolidation_add_memory",
    "consolidation_distill_session",
    "consolidation_export_report",
    "consolidation_get_stats",
    "consolidation_reset_all",
    "consolidation_run_cycle",
    "get_consolidation_tools",
    "get_global_consolidation_engine",
    "handle_consolidation_slash_command",
    "reset_global_consolidation_engine",
]
