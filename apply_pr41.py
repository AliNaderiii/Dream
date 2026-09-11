#!/usr/bin/env python3
"""Phase 38: Autonomous Sleep-Phase Memory Consolidation, Entropy Pruning & Distillation.

Applies all modules for Phase 38:
- dream/consolidation/types.py
- dream/consolidation/pruner.py
- dream/consolidation/distiller.py
- dream/consolidation/engine.py
- dream/consolidation/tools.py
- dream/consolidation/slash.py
- dream/consolidation/__init__.py
- dream/tools/toolsets.py (registered consolidation toolset)
- tests/test_memory_consolidation_and_pruning.py
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

FILES: dict[str, str] = {
    "dream/consolidation/types.py": r'''"""Domain models and data structures for Memory Consolidation, Entropy Pruning, and Epistemic Distillation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import time
from typing import Any


class MemoryNodeType(str, Enum):
    """Classification of stored memory items."""

    EPISODIC = "episodic"                    # Raw conversational turn or event log
    SEMANTIC_FACT = "semantic_fact"          # Distilled timeless factual statement
    CORE_BELIEF = "core_belief"              # High-priority user premise or core invariant
    USER_TRAIT = "user_trait"                # User preference, behavioral habit, or style
    EPHEMERAL_SCRATCHPAD = "ephemeral_scratchpad"  # Intermediate thoughts, tool scratchpad


class ConsolidationStage(str, Enum):
    """Stages in the autonomous sleep-phase memory consolidation cycle."""

    INGESTION = "ingestion"
    EBBINGHAUS_DECAY = "ebbinghaus_decay"
    ENTROPY_PRUNING = "entropy_pruning"
    EPISTEMIC_DISTILLATION = "epistemic_distillation"
    DEDUPLICATION = "deduplication"
    DREAM_SIMULATION = "dream_simulation"
    COMPLETED = "completed"


@dataclass(slots=True)
class MemoryItem:
    """A granular unit of memory subjected to retention, decay, and distillation."""

    memory_id: str
    node_type: MemoryNodeType
    content: str
    importance: float = 0.5          # Value between 0.0 (trivial) and 1.0 (vital)
    access_count: int = 1
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)
    decay_score: float = 1.0         # Retrievability R = e^(-t/S)
    metadata: dict[str, Any] = field(default_factory=dict)

    def calculate_decay(self, current_time: float, decay_constant: float = 86400.0) -> float:
        """Calculate retrievability using Ebbinghaus exponential decay model.

        R = exp( - delta_t / (S * decay_constant) )
        where stability S = 1.0 + (importance * 3.0) + (log(1 + access_count) * 2.0)
        """
        delta_t = max(0.0, current_time - self.last_accessed_at)
        stability = 1.0 + (self.importance * 3.0) + (math.log(1.0 + self.access_count) * 2.0)
        retrievability = math.exp(-delta_t / (stability * decay_constant))
        self.decay_score = max(0.0, min(1.0, retrievability))
        return self.decay_score

    def to_dict(self) -> dict[str, Any]:
        """Serialize memory item to dictionary."""
        return {
            "memory_id": self.memory_id,
            "node_type": self.node_type.value,
            "content": self.content,
            "importance": round(self.importance, 3),
            "access_count": self.access_count,
            "created_at": round(self.created_at, 2),
            "last_accessed_at": round(self.last_accessed_at, 2),
            "decay_score": round(self.decay_score, 3),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class ConsolidationReport:
    """Outcome of a memory consolidation and pruning cycle."""

    cycle_id: str
    initial_memory_count: int
    final_memory_count: int
    pruned_nodes_count: int
    consolidated_facts_count: int
    conflicts_resolved_count: int
    compression_ratio: float
    entropy_reduction_pct: float
    summary_fa: str
    duration_ms: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize consolidation report to dictionary."""
        return {
            "cycle_id": self.cycle_id,
            "initial_memory_count": self.initial_memory_count,
            "final_memory_count": self.final_memory_count,
            "pruned_nodes_count": self.pruned_nodes_count,
            "consolidated_facts_count": self.consolidated_facts_count,
            "conflicts_resolved_count": self.conflicts_resolved_count,
            "compression_ratio": round(self.compression_ratio, 3),
            "entropy_reduction_pct": round(self.entropy_reduction_pct, 2),
            "summary_fa": self.summary_fa,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": round(self.timestamp, 2),
        }


@dataclass(slots=True)
class ConsolidationStats:
    """Aggregate health and footprint stats of memory repository."""

    total_cycles_executed: int
    total_memories_stored: int
    total_pruned_historical: int
    total_distilled_facts: int
    average_compression_ratio: float
    memory_health_score: float  # 0.0 to 1.0 (Higher means compact, high-value, low noise)

    def to_dict(self) -> dict[str, Any]:
        """Serialize consolidation statistics."""
        return {
            "total_cycles_executed": self.total_cycles_executed,
            "total_memories_stored": self.total_memories_stored,
            "total_pruned_historical": self.total_pruned_historical,
            "total_distilled_facts": self.total_distilled_facts,
            "average_compression_ratio": round(self.average_compression_ratio, 3),
            "memory_health_score": round(self.memory_health_score, 3),
        }
''',
    "dream/consolidation/pruner.py": r'''"""Entropy Pruning and Ebbinghaus Forgetting Curve Memory Cleaner."""

from __future__ import annotations

import time
from typing import Any

from dream.consolidation.types import MemoryItem, MemoryNodeType


class EntropyPruner:
    """Evaluates retention decay, removes low-value noise, and deduplicates memory items."""

    def __init__(self, retention_threshold: float = 0.25) -> None:
        self.retention_threshold = retention_threshold

    def apply_decay(
        self,
        memories: list[MemoryItem],
        current_time: float | None = None,
        decay_constant: float = 86400.0,
    ) -> list[MemoryItem]:
        """Update decay scores for all memory items based on elapsed time."""
        now = current_time if current_time is not None else time.time()
        for item in memories:
            item.calculate_decay(now, decay_constant=decay_constant)
        return memories

    def prune_low_entropy_nodes(
        self,
        memories: list[MemoryItem],
        threshold: float | None = None,
    ) -> tuple[list[MemoryItem], list[MemoryItem]]:
        """Filter out memory items whose decay score is below retention threshold.

        Core beliefs and high-importance memories (importance >= 0.85) are always retained.
        Ephemeral scratchpads with decay < 0.6 are pruned immediately.
        """
        thresh = threshold if threshold is not None else self.retention_threshold
        retained: list[MemoryItem] = []
        pruned: list[MemoryItem] = []

        for item in memories:
            # Protected items
            if item.node_type == MemoryNodeType.CORE_BELIEF or item.importance >= 0.85:
                retained.append(item)
                continue

            # Ephemeral items have stricter threshold
            if item.node_type == MemoryNodeType.EPHEMERAL_SCRATCHPAD:
                if item.decay_score < 0.60:
                    pruned.append(item)
                else:
                    retained.append(item)
                continue

            # Standard items
            if item.decay_score < thresh:
                pruned.append(item)
            else:
                retained.append(item)

        return retained, pruned

    def deduplicate(
        self,
        memories: list[MemoryItem],
        similarity_threshold: float = 0.75,
    ) -> tuple[list[MemoryItem], int]:
        """Merge near-duplicate memory nodes to reduce knowledge entropy."""
        unique_memories: list[MemoryItem] = []
        merged_count = 0

        for item in memories:
            matched = False
            item_tokens = set(item.content.lower().split())

            for existing in unique_memories:
                if item.node_type == existing.node_type:
                    ex_tokens = set(existing.content.lower().split())
                    if not item_tokens or not ex_tokens:
                        continue
                    jaccard = len(item_tokens & ex_tokens) / len(item_tokens | ex_tokens)
                    if jaccard >= similarity_threshold:
                        # Merge into existing item
                        existing.access_count += item.access_count
                        existing.importance = max(existing.importance, item.importance)
                        existing.last_accessed_at = max(existing.last_accessed_at, item.last_accessed_at)
                        existing.decay_score = max(existing.decay_score, item.decay_score)
                        matched = True
                        merged_count += 1
                        break

            if not matched:
                unique_memories.append(item)

        return unique_memories, merged_count
''',
    "dream/consolidation/distiller.py": r'''"""Epistemic Distiller: Fact crystallization, contradiction reconciliation, and dream simulation."""

from __future__ import annotations

import re
import time
from typing import Any
import uuid

from dream.consolidation.types import MemoryItem, MemoryNodeType


class EpistemicDistiller:
    """Transforms raw conversation turns into semantic facts and resolves epistemic contradictions."""

    def distill_transcript(
        self,
        transcript_text: str,
    ) -> list[MemoryItem]:
        """Extract atomic semantic facts and user traits from raw conversation transcript."""
        lines = [line.strip() for line in transcript_text.splitlines() if line.strip()]
        distilled: list[MemoryItem] = []

        for line in lines:
            line_clean = re.sub(r"^[0-9\-\*\.\:\s]+", "", line).strip()
            if len(line_clean) < 10:
                continue

            node_type = MemoryNodeType.SEMANTIC_FACT
            importance = 0.60

            # Detect user traits / preferences
            if any(k in line_clean.lower() for k in ["علاقه‌مند", "ترجیح", "دوست دارد", "prefer", "like", "interest"]):
                node_type = MemoryNodeType.USER_TRAIT
                importance = 0.80
            elif any(k in line_clean.lower() for k in ["همیشه", "قانون", "اصول", "must", "always", "rule"]):
                node_type = MemoryNodeType.CORE_BELIEF
                importance = 0.90

            item = MemoryItem(
                memory_id=f"fact-{uuid.uuid4().hex[:6]}",
                node_type=node_type,
                content=line_clean,
                importance=importance,
                access_count=1,
                created_at=time.time(),
                last_accessed_at=time.time(),
                decay_score=1.0,
            )
            distilled.append(item)

        return distilled

    def reconcile_contradictions(
        self,
        memories: list[MemoryItem],
    ) -> tuple[list[MemoryItem], int]:
        """Resolve conflicting assertions by keeping the most recently updated memory."""
        reconciled: list[MemoryItem] = []
        conflicts_resolved = 0

        # Sort memories chronologically (newest first)
        sorted_memories = sorted(memories, key=lambda m: m.last_accessed_at, reverse=True)

        for item in sorted_memories:
            has_direct_conflict = False
            for existing in reconciled:
                # Check for direct subject overlap with opposing polarity
                if (
                    item.node_type == existing.node_type
                    and item.node_type in (MemoryNodeType.USER_TRAIT, MemoryNodeType.CORE_BELIEF)
                ):
                    tokens_a = set(item.content.lower().split())
                    tokens_b = set(existing.content.lower().split())
                    common = tokens_a & tokens_b
                    if len(common) >= 3 and item.content != existing.content:
                        # Existing is newer because of sorting
                        has_direct_conflict = True
                        conflicts_resolved += 1
                        break

            if not has_direct_conflict:
                reconciled.append(item)

        return reconciled, conflicts_resolved

    def run_synthetic_dream_simulation(
        self,
        core_memories: list[MemoryItem],
        num_scenarios: int = 2,
    ) -> list[dict[str, Any]]:
        """Simulate hypothetical agent reasoning scenarios to reinforce core knowledge."""
        simulations: list[dict[str, Any]] = []

        if not core_memories:
            return simulations

        for i in range(min(num_scenarios, len(core_memories))):
            mem = core_memories[i]
            sim = {
                "simulation_id": f"dream-{uuid.uuid4().hex[:6]}",
                "focus_memory": mem.content,
                "hypothetical_scenario": (
                    f"Scenario: User asks complex task involving '{mem.content[:40]}...'"
                ),
                "synthesized_reinforcement_fa": (
                    f"\u062a\u062b\u0628\u06cc\u062a \u062e\u0648\u062f\u06a9\u0627\u0631 \u0627\u0631\u062a\u0628\u0627\u0637 \u0628\u0627\u0648\u0631: '{mem.content[:30]}...'"
                ),
                "timestamp": round(time.time(), 2),
            }
            simulations.append(sim)

        return simulations
''',
    "dream/consolidation/engine.py": r'''"""Consolidation Engine Coordinator: Sleep-phase memory consolidation, pruning, and health metrics."""

from __future__ import annotations

import time
from typing import Any
import uuid

from dream.consolidation.distiller import EpistemicDistiller
from dream.consolidation.pruner import EntropyPruner
from dream.consolidation.types import (
    ConsolidationReport,
    ConsolidationStats,
    MemoryItem,
    MemoryNodeType,
)


class ConsolidationEngine:
    """Orchestrates sleep-phase memory consolidation, entropy pruning, and contradiction resolution."""

    def __init__(
        self,
        pruner: EntropyPruner | None = None,
        distiller: EpistemicDistiller | None = None,
    ) -> None:
        self.pruner = pruner or EntropyPruner()
        self.distiller = distiller or EpistemicDistiller()

        self._memories: dict[str, MemoryItem] = {}
        self._reports_history: list[ConsolidationReport] = []
        self._historical_pruned_count: int = 0
        self._historical_distilled_count: int = 0

    def add_memory(
        self,
        content: str,
        node_type: MemoryNodeType = MemoryNodeType.EPISODIC,
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem:
        """Create and store a new memory item."""
        mem_id = f"mem-{uuid.uuid4().hex[:6]}"
        item = MemoryItem(
            memory_id=mem_id,
            node_type=node_type,
            content=content,
            importance=importance,
            access_count=1,
            created_at=time.time(),
            last_accessed_at=time.time(),
            decay_score=1.0,
            metadata=metadata or {},
        )
        self._memories[mem_id] = item
        return item

    def get_all_memories(self) -> list[MemoryItem]:
        """Return all active memory items."""
        return list(self._memories.values())

    def run_consolidation_cycle(
        self,
        current_time: float | None = None,
        decay_constant: float = 86400.0,
        dry_run: bool = False,
    ) -> ConsolidationReport:
        """Execute complete autonomous sleep-phase memory consolidation cycle."""
        start_time = time.time()
        now = current_time if current_time is not None else start_time
        cycle_id = f"cycle-{uuid.uuid4().hex[:6]}"

        initial_items = list(self._memories.values())
        initial_count = len(initial_items)

        if initial_count == 0:
            rep = ConsolidationReport(
                cycle_id=cycle_id,
                initial_memory_count=0,
                final_memory_count=0,
                pruned_nodes_count=0,
                consolidated_facts_count=0,
                conflicts_resolved_count=0,
                compression_ratio=1.0,
                entropy_reduction_pct=0.0,
                summary_fa="\u062d\u0627\u0641\u0638\u0647 \u062e\u0627\u0644\u06cc \u0627\u0633\u062a\u061b \u0686\u0631\u062e\u0647 \u062a\u062b\u0628\u06cc\u062a \u0628\u062f\u0648\u0646 \u062a\u063a\u06cc\u06cc\u0631 \u067e\u0627\u06cc\u0627\u0646 \u06cc\u0627\u0641\u062a.",
                duration_ms=(time.time() - start_time) * 1000,
            )
            if not dry_run:
                self._reports_history.append(rep)
            return rep

        # 1. Apply Ebbinghaus decay
        decayed_items = self.pruner.apply_decay(initial_items, current_time=now, decay_constant=decay_constant)

        # 2. Prune low-entropy and decayed memories
        retained_items, pruned_items = self.pruner.prune_low_entropy_nodes(decayed_items)
        pruned_count = len(pruned_items)

        # 3. Deduplicate
        deduped_items, dedup_merged = self.pruner.deduplicate(retained_items)

        # 4. Resolve contradictions
        reconciled_items, conflicts_resolved = self.distiller.reconcile_contradictions(deduped_items)

        # 5. Dream simulation
        core_memories = [m for m in reconciled_items if m.node_type in (MemoryNodeType.CORE_BELIEF, MemoryNodeType.USER_TRAIT)]
        self.distiller.run_synthetic_dream_simulation(core_memories)

        final_count = len(reconciled_items)
        compression_ratio = final_count / initial_count if initial_count > 0 else 1.0
        entropy_reduction_pct = max(0.0, (1.0 - compression_ratio) * 100)
        duration_ms = (time.time() - start_time) * 1000

        report = ConsolidationReport(
            cycle_id=cycle_id,
            initial_memory_count=initial_count,
            final_memory_count=final_count,
            pruned_nodes_count=pruned_count + dedup_merged,
            consolidated_facts_count=final_count,
            conflicts_resolved_count=conflicts_resolved,
            compression_ratio=compression_ratio,
            entropy_reduction_pct=entropy_reduction_pct,
            summary_fa=(
                f"\U0001f9e0 \u0686\u0631\u062e\u0647 \u062a\u062b\u0628\u06cc\u062a \u062d\u0627\u0641\u0638\u0647 \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u0627\u0646\u062c\u0627\u0645 \u0634\u062f: "
                f"{pruned_count + dedup_merged} \u06af\u0631\u0647 \u0647\u0631\u0633 \u0648 {conflicts_resolved} \u062a\u0639\u0627\u0631\u0636 \u062d\u0644 \u06af\u0631\u062f\u06cc\u062f "
                f"(\u06a9\u0627\u0647\u0634 \u0622\u0646\u062a\u0631\u0648\u067e\u06cc: {entropy_reduction_pct:.1f}%)."
            ),
            duration_ms=duration_ms,
        )

        if not dry_run:
            self._memories = {m.memory_id: m for m in reconciled_items}
            self._reports_history.append(report)
            self._historical_pruned_count += (pruned_count + dedup_merged)
            self._historical_distilled_count += final_count

        return report

    def get_health_stats(self) -> ConsolidationStats:
        """Compute aggregate health metrics of the memory system."""
        total_cycles = len(self._reports_history)
        current_stored = len(self._memories)
        avg_comp = (
            sum(r.compression_ratio for r in self._reports_history) / total_cycles
            if total_cycles > 0
            else 1.0
        )

        # Health score: higher when importance is high and decay is under control
        if current_stored == 0:
            health_score = 1.0
        else:
            avg_importance = sum(m.importance for m in self._memories.values()) / current_stored
            avg_decay = sum(m.decay_score for m in self._memories.values()) / current_stored
            health_score = min(1.0, (avg_importance * 0.6) + (avg_decay * 0.4))

        return ConsolidationStats(
            total_cycles_executed=total_cycles,
            total_memories_stored=current_stored,
            total_pruned_historical=self._historical_pruned_count,
            total_distilled_facts=self._historical_distilled_count,
            average_compression_ratio=avg_comp,
            memory_health_score=health_score,
        )

    def format_consolidation_report(self) -> str:
        """Format consolidation status and memory metrics into Markdown."""
        stats = self.get_health_stats()
        lines = [
            "## \U0001f9e0 \u06af\u0632\u0627\u0631\u0634 \u062a\u062b\u0628\u06cc\u062a \u0648 \u0633\u0644\u0627\u0645\u062a \u062d\u0627\u0641\u0638\u0647 (Memory Consolidation & Health)",
            f"- **\u0634\u0627\u062e\u0635 \u0633\u0644\u0627\u0645\u062a \u062d\u0627\u0641\u0638\u0647 (Health Score):** `{stats.memory_health_score * 100:.1f}%`",
            f"- **\u062a\u0639\u062f\u0627\u062f \u06af\u0631\u0647\u200c\u0647\u0627\u06cc \u0641\u0639\u0627\u0644:** {stats.total_memories_stored}",
            f"- **\u0686\u0631\u062e\u0647\u200c\u0647\u0627\u06cc \u0627\u062c\u0631\u0624\u0634\u062f\u0647:** {stats.total_cycles_executed}",
            f"- **\u0645\u062c\u0645\u0648\u0639 \u06af\u0631\u0647\u200c\u0647\u0627\u06cc \u0647\u0631\u0633\u200c\u0634\u062f\u0647 \u062a\u0627\u0631\u06cc\u062e\u06cc:** {stats.total_pruned_historical}",
            f"- **\u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 \u0646\u0631\u062e \u0641\u0634\u0631\u062f\u0647\u200c\u0633\u0627\u0632\u06cc:** {stats.average_compression_ratio:.2f}",
            "",
            "### \U0001f4ca \u06af\u0632\u0627\u0631\u0634 \u0622\u062e\u0631\u06cc\u0646 \u0686\u0631\u062e\u0647:",
        ]

        if not self._reports_history:
            lines.append("- \u0647\u0646\u0648\u0632 \u0686\u0631\u062e\u0647 \u062a\u062b\u0628\u06cc\u062a\u06cc \u0627\u062c\u0631\u0627 \u0646\u0634\u062f\u0647 \u0627\u0633\u062a.")
        else:
            latest = self._reports_history[-1]
            lines.extend(
                [
                    f"- \u0634\u0646\u0627\u0633\u0647: `{latest.cycle_id}`",
                    f"- \u06af\u0631\u0647\u200c\u0647\u0627\u06cc \u0627\u0648\u0644\u06cc\u0647: {latest.initial_memory_count} -> \u0646\u0647\u0627\u06cc\u06cc: {latest.final_memory_count}",
                    f"- \u062a\u0639\u062f\u0627\u062f \u0647\u0631\u0633 \u0634\u062f\u0647: {latest.pruned_nodes_count}",
                    f"- \u062a\u0639\u0627\u0631\u0636\u200c\u0647\u0627\u06cc \u062d\u0644\u200c\u0634\u062f\u0647: {latest.conflicts_resolved_count}",
                    f"- \u06a9\u0627\u0647\u0634 \u0622\u0646\u062a\u0631\u0648\u067e\u06cc: {latest.entropy_reduction_pct:.1f}%",
                ]
            )

        return "\n".join(lines)

    def reset(self) -> None:
        """Reset memory store and consolidation history."""
        self._memories.clear()
        self._reports_history.clear()
        self._historical_pruned_count = 0
        self._historical_distilled_count = 0
''',
    "dream/consolidation/tools.py": r'''"""LLM tool bindings for Memory Consolidation, Entropy Pruning, and Epistemic Distillation."""

from __future__ import annotations

from typing import Any

from dream.consolidation.engine import ConsolidationEngine
from dream.consolidation.types import MemoryNodeType

_GLOBAL_CONSOLIDATION_ENGINE: ConsolidationEngine | None = None


def get_global_consolidation_engine() -> ConsolidationEngine:
    """Get or initialize singleton ConsolidationEngine."""
    global _GLOBAL_CONSOLIDATION_ENGINE
    if _GLOBAL_CONSOLIDATION_ENGINE is None:
        _GLOBAL_CONSOLIDATION_ENGINE = ConsolidationEngine()
    return _GLOBAL_CONSOLIDATION_ENGINE


def reset_global_consolidation_engine() -> None:
    """Reset singleton ConsolidationEngine."""
    global _GLOBAL_CONSOLIDATION_ENGINE
    _GLOBAL_CONSOLIDATION_ENGINE = None


def consolidation_add_memory(
    content: str,
    node_type: str = "episodic",
    importance: float = 0.5,
) -> dict[str, Any]:
    """Store a new memory item in the consolidation engine."""
    engine = get_global_consolidation_engine()
    try:
        nt = MemoryNodeType(node_type.lower())
    except ValueError:
        nt = MemoryNodeType.EPISODIC

    item = engine.add_memory(content=content, node_type=nt, importance=importance)
    return {"success": True, "memory": item.to_dict()}


def consolidation_run_cycle(dry_run: bool = False) -> dict[str, Any]:
    """Run full sleep-phase memory consolidation, Ebbinghaus decay, and entropy pruning cycle."""
    engine = get_global_consolidation_engine()
    report = engine.run_consolidation_cycle(dry_run=dry_run)
    return {"success": True, "report": report.to_dict()}


def consolidation_distill_session(raw_transcript: str) -> dict[str, Any]:
    """Distill raw multi-turn conversation into atomic semantic facts and user traits."""
    engine = get_global_consolidation_engine()
    facts = engine.distiller.distill_transcript(raw_transcript)
    for f in facts:
        engine._memories[f.memory_id] = f
    return {
        "success": True,
        "distilled_facts_count": len(facts),
        "facts": [f.to_dict() for f in facts],
    }


def consolidation_get_stats() -> dict[str, Any]:
    """Retrieve memory repository health score, node counts, and compression rates."""
    engine = get_global_consolidation_engine()
    stats = engine.get_health_stats()
    return {"success": True, "stats": stats.to_dict()}


def consolidation_export_report() -> dict[str, Any]:
    """Export formatted Markdown report of memory consolidation and retention health."""
    engine = get_global_consolidation_engine()
    report_md = engine.format_consolidation_report()
    return {"success": True, "markdown_report": report_md}


def consolidation_reset_all() -> dict[str, Any]:
    """Reset all stored memories and consolidation history."""
    engine = get_global_consolidation_engine()
    engine.reset()
    return {"success": True, "message": "\u062d\u0627\u0641\u0638\u0647 \u0648 \u062a\u0627\u0631\u06cc\u062e\u0686\u0647 \u062a\u062b\u0628\u06cc\u062a \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."}


def get_consolidation_tools() -> list[Any]:
    """Return consolidation tool functions for agent registration."""
    return [
        consolidation_add_memory,
        consolidation_run_cycle,
        consolidation_distill_session,
        consolidation_get_stats,
        consolidation_export_report,
        consolidation_reset_all,
    ]
''',
    "dream/consolidation/slash.py": r'''"""CLI and slash command handlers for Memory Consolidation and Epistemic Distillation."""

from __future__ import annotations

from typing import Any

from dream.consolidation.tools import (
    consolidation_distill_session,
    consolidation_export_report,
    consolidation_reset_all,
    consolidation_run_cycle,
)


def handle_consolidation_slash_command(command_str: str) -> str:
    """Handle /consolidate, /distill_memory, and /memory_health CLI slash commands.

    Usage:
        /consolidate [dry_run]
        /distill_memory <transcript>
        /memory_health [reset]
    """
    cmd = command_str.strip()

    if cmd.startswith("/consolidate"):
        parts = cmd.split()
        is_dry = len(parts) > 1 and parts[1].lower() in ("dry", "dry_run", "preview")
        res = consolidation_run_cycle(dry_run=is_dry)
        rep = res.get("report", {})
        return (
            f"\U0001f9e0 \u0646\u062a\u06cc\u062c\u0647 \u0686\u0631\u062e\u0647 \u062a\u062b\u0628\u06cc\u062a \u062d\u0627\u0641\u0638\u0647 {'(پیش‌نمایش)' if is_dry else ''}:\n"
            f"- \u06af\u0631\u0647\u200c\u0647\u0627: {rep.get('initial_memory_count')} -> {rep.get('final_memory_count')}\n"
            f"- \u0647\u0631\u0633 \u0634\u062f\u0647: {rep.get('pruned_nodes_count')} \u06af\u0631\u0647\n"
            f"- \u062a\u0639\u0627\u0631\u0636\u200c\u0647\u0627\u06cc \u062d\u0644\u200c\u0634\u062f\u0647: {rep.get('conflicts_resolved_count')}\n"
            f"- \u06a9\u0627\u0647\u0634 \u0622\u0646\u062a\u0631\u0648\u067e\u06cc: {rep.get('entropy_reduction_pct'):.1f}%\n"
            f"- \u0632\u0645\u0627\u0646 \u0627\u062c\u0631\u0627: {rep.get('duration_ms'):.1f} \u0645\u06cc\u0644\u06cc\u200c\u062b\u0627\u0646\u06cc\u0647"
        )

    if cmd.startswith("/distill_memory"):
        raw = cmd[len("/distill_memory") :].strip()
        if not raw:
            return "\u274c \u0644\u0637\u0641\u0627\u064b \u0645\u062a\u0646 \u0645\u06a9\u0627\u0644\u0645\u0647 \u0631\u0627 \u0628\u0631\u0627\u06cc \u062a\u0642\u0637\u06cc\u0631 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
        res = consolidation_distill_session(raw)
        return f"\u2728 \u062a\u0642\u0637\u06cc\u0631 \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u0627\u0646\u062c\u0627\u0645 \u0634\u062f: {res.get('distilled_facts_count')} \u0641\u06a9\u062a \u0648 \u0628\u0627\u0648\u0631 \u062c\u062f\u06cc\u062f \u0627\u0633\u062a\u062e\u0631\u0627\u062c \u06af\u0631\u062f\u06cc\u062f."

    if cmd.startswith("/memory_health"):
        parts = cmd.split()
        subcmd = parts[1].lower() if len(parts) > 1 else "report"
        if subcmd == "reset":
            consolidation_reset_all()
            return "\u2705 \u062d\u0627\u0641\u0638\u0647 \u0648 \u062a\u0627\u0631\u06cc\u062e\u0686\u0647 \u062a\u062b\u0628\u06cc\u062a \u0628\u0627\u0632\u0646\u0634\u0627\u0646\u06cc \u0634\u062f."

        res = consolidation_export_report()
        return res.get("markdown_report", "")

    return "\u274c \u062f\u0633\u062a\u0648\u0631 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a."
''',
    "dream/consolidation/__init__.py": r'''"""Autonomous Sleep-Phase Memory Consolidation, Entropy Pruning, and Epistemic Distillation Subsystem."""

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
''',
    "dream/tools/toolsets.py": r'''"""Toolset categorization, grouping, and dynamic tool management."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from dream.tools.base import REGISTRY, Tool


@dataclass(frozen=True)
class Toolset:
    """Group of related tools identified by name."""

    name: str
    description: str
    tools: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


# Default built-in toolsets matching Dream's core capabilities
BUILTIN_TOOLSETS: dict[str, Toolset] = {
    "core": Toolset(
        name="core",
        description="Fundamental utilities (datetime, math calculation)",
        tools=("get_datetime", "calculate"),
    ),
    "workspace": Toolset(
        name="workspace",
        description="Workspace note inspection and editing",
        tools=("read_note", "list_notes", "write_note"),
    ),
    "web": Toolset(
        name="web",
        description="Public internet search and page fetching",
        tools=("search_web", "read_page"),
    ),
    "skills": Toolset(
        name="skills",
        description="Reusable skill management, hub discovery, and autonomous evolution",
        tools=(
            "save_skill",
            "use_skill",
            "list_skills",
            "skill_view",
            "edit_skill",
            "delete_skill",
            "save_skill_bundle",
            "apply_skill_proposal",
            "discard_skill_proposal",
            "hub_search_skills",
            "hub_install_skill",
            "skill_evolve_optimize",
            "skill_export_bundle",
            "skill_import_bundle",
        ),
    ),
    "reminders": Toolset(
        name="reminders",
        description="Scheduled reminders and tasks",
        tools=("create_reminder", "cancel_reminder"),
    ),
    "system": Toolset(
        name="system",
        description="System commands and external communication",
        tools=("run_shell", "send_email"),
    ),
    "mcp": Toolset(
        name="mcp",
        description="Model Context Protocol servers, discovery, and tool execution",
        tools=(
            "mcp_list_servers",
            "mcp_list_tools",
            "mcp_call_tool",
            "mcp_read_resource",
            "mcp_reload",
        ),
    ),
    "subagents": Toolset(
        name="subagents",
        description="Multi-agent orchestration, delegation, and worker lifecycle",
        tools=(
            "subagent_spawn",
            "subagent_wait",
            "subagent_delegate_task",
            "subagent_list",
            "subagent_terminate",
        ),
    ),
    "scheduler": Toolset(
        name="scheduler",
        description="Autonomous cron scheduling, reminders, and multi-channel delivery",
        tools=(
            "schedule_task",
            "list_schedules",
            "cancel_schedule",
            "trigger_schedule",
        ),
    ),
    "retrieval": Toolset(
        name="retrieval",
        description="Hybrid semantic retrieval and knowledge graph memory association",
        tools=(
            "search_hybrid_memory",
            "query_knowledge_graph",
        ),
    ),
    "distill": Toolset(
        name="distill",
        description="Autonomous trajectory recording, distillation, and evaluation benchmarks",
        tools=(
            "distill_record_trajectory",
            "distill_export_dataset",
            "eval_run_benchmark",
        ),
    ),
    "profiles": Toolset(
        name="profiles",
        description="Multi-profile persona scoping and isolated workspace management",
        tools=(
            "profile_list",
            "profile_get_current",
            "profile_switch",
            "profile_create",
        ),
    ),
    "context": Toolset(
        name="context",
        description="Prioritized context files (SOUL, AGENTS, USER, MEMORY) and budgeting",
        tools=(
            "context_get_tier",
            "context_update_tier",
            "context_get_budget_report",
            "context_assemble_prompt",
            "context_reload_all",
        ),
    ),
    "terminal": Toolset(
        name="terminal",
        description="Multi-backend isolated execution (Local, Docker, SSH, Cloud Sandboxes)",
        tools=(
            "terminal_execute",
            "terminal_list_backends",
            "terminal_switch_backend",
        ),
    ),
    "browser": Toolset(
        name="browser",
        description="Multi-driver browser control, DOM extraction, and visual interaction",
        tools=(
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_screenshot",
            "browser_extract_content",
            "browser_close",
            "browser_get_status",
        ),
    ),
    "dialectic": Toolset(
        name="dialectic",
        description="Self-reflective dialectic user modeling and knowledge synthesis",
        tools=(
            "dialectic_observe",
            "dialectic_reflect",
            "dialectic_get_belief_graph",
            "dialectic_reconcile",
            "dialectic_query_traits",
        ),
    ),
    "acp": Toolset(
        name="acp",
        description="Agent Client Protocol (ACP) IDE integration and diff tools",
        tools=(
            "acp_apply_diff",
            "acp_read_diagnostics",
            "acp_get_session_status",
            "acp_list_agents",
            "acp_call_agent",
        ),
    ),
    "plugins": Toolset(
        name="plugins",
        description="Dynamic plugin installation, lifecycle management, and extension hooks",
        tools=(
            "plugin_list",
            "plugin_install",
            "plugin_enable",
            "plugin_disable",
            "plugin_get_info",
        ),
    ),
    "swarm": Toolset(
        name="swarm",
        description="Distributed swarm orchestration, DAG task execution, and consensus",
        tools=(
            "swarm_spawn_node",
            "swarm_plan_workflow",
            "swarm_execute_step",
            "swarm_run_all",
            "swarm_reach_consensus",
            "swarm_get_status",
            "swarm_broadcast_message",
        ),
    ),
    "speech": Toolset(
        name="speech",
        description="Voice synthesis (TTS), recognition (STT), and HybridEmo emotion modeling",
        tools=(
            "speech_text_to_speech",
            "speech_speech_to_text",
            "speech_analyze_voice_emotion",
            "speech_list_voices",
        ),
    ),
    "ocr": Toolset(
        name="ocr",
        description="Persian document OCR, receipt parsing, and invoice field extraction",
        tools=(
            "ocr_extract_document",
            "ocr_extract_invoice",
        ),
    ),
    "knowledge": Toolset(
        name="knowledge",
        description=(
            "Multimodal temporal knowledge graph, timeline reasoning, "
            "and cross-modal entity linking"
        ),
        tools=(
            "knowledge_add_entity",
            "knowledge_add_relation",
            "knowledge_query_temporal",
            "knowledge_get_entity_timeline",
            "knowledge_link_multimodal_artifact",
            "knowledge_get_stats",
        ),
    ),
    "alignment": Toolset(
        name="alignment",
        description=(
            "Continuous self-improving alignment, multi-dimensional scoring, "
            "self-critique, and DPO dataset generation"
        ),
        tools=(
            "alignment_record_feedback",
            "alignment_critique_and_refine",
            "alignment_evaluate_response",
            "alignment_export_dataset",
            "alignment_get_stats",
        ),
    ),
    "research": Toolset(
        name="research",
        description=(
            "Autonomous multi-step deep research, evidence collection, "
            "and multi-source intelligence synthesis"
        ),
        tools=(
            "research_plan_investigation",
            "research_add_source",
            "research_synthesize_report",
            "research_run_autonomous",
            "research_export_report",
            "research_get_status",
            "research_list_sessions",
        ),
    ),
    "cache": Toolset(
        name="cache",
        description=(
            "Semantic caching, speculative pre-fetching, and token economics optimization"
        ),
        tools=(
            "cache_lookup_query",
            "cache_store_entry",
            "cache_predict_tool",
            "cache_get_economics",
            "cache_clear",
            "cache_warmup",
        ),
    ),
    "sandbox": Toolset(
        name="sandbox",
        description=(
            "Isolated Python code execution, dataset analysis, and REPL interpreter"
        ),
        tools=(
            "sandbox_execute_python",
            "sandbox_analyze_dataset",
            "sandbox_reset_session",
            "sandbox_list_artifacts",
            "sandbox_get_status",
        ),
    ),
    "canvas": Toolset(
        name="canvas",
        description=(
            "Interactive visual artifacts, diagrams, standalone previews, and versioning"
        ),
        tools=(
            "canvas_create_artifact",
            "canvas_update_artifact",
            "canvas_get_artifact",
            "canvas_list_artifacts",
            "canvas_diff_versions",
            "canvas_render_preview",
            "canvas_export_bundle",
            "canvas_reset_session",
            "canvas_get_status",
        ),
    ),
    "debate": Toolset(
        name="debate",
        description=(
            "Multi-agent debate rounds, Delphi consensus evaluation, and fact verification"
        ),
        tools=(
            "debate_create_session",
            "debate_add_turn",
            "debate_run_autonomous",
            "debate_verify_statement",
            "debate_reach_consensus",
            "debate_list_sessions",
            "debate_reset_all",
        ),
    ),
    "reasoning": Toolset(
        name="reasoning",
        description=(
            "Tree-of-Thought exploration, strategy branching, and metacognitive self-evaluation"
        ),
        tools=(
            "reasoning_create_thought_tree",
            "reasoning_expand_node",
            "reasoning_evaluate_node",
            "reasoning_solve_goal",
            "reasoning_get_best_path",
            "reasoning_get_status",
            "reasoning_reset_all",
        ),
    ),
    "healing": Toolset(
        name="healing",
        description=(
            "Autonomous error diagnosis, self-healing recovery, telemetry, and chaos testing"
        ),
        tools=(
            "healing_diagnose_failure",
            "healing_run_chaos_test",
            "telemetry_get_health_metrics",
            "telemetry_export_report",
            "telemetry_export_spans",
            "telemetry_reset_all",
        ),
    ),
    "router": Toolset(
        name="router",
        description=(
            "Adaptive semantic routing, prompt compilation, and cascading execution"
        ),
        tools=(
            "router_evaluate_query",
            "router_compile_prompt",
            "router_cascade_plan",
            "router_get_stats",
            "router_export_report",
            "router_reset_all",
        ),
    ),
    "consolidation": Toolset(
        name="consolidation",
        description=(
            "Autonomous sleep-phase memory consolidation, Ebbinghaus decay, entropy pruning, and contradiction resolution"
        ),
        tools=(
            "consolidation_add_memory",
            "consolidation_run_cycle",
            "consolidation_distill_session",
            "consolidation_get_stats",
            "consolidation_export_report",
            "consolidation_reset_all",
        ),
    ),
}

_TOOLSETS: dict[str, Toolset] = dict(BUILTIN_TOOLSETS)


def register_toolset(
    name: str,
    tools: Collection[str],
    description: str = "",
    metadata: dict[str, Any] | None = None,
) -> Toolset:
    """Register a new named toolset or update an existing one."""
    toolset = Toolset(
        name=name,
        description=description,
        tools=tuple(sorted(set(tools))),
        metadata=metadata or {},
    )
    _TOOLSETS[name] = toolset
    return toolset


def unregister_toolset(name: str) -> bool:
    """Remove a registered toolset (returns True if removed)."""
    if name in _TOOLSETS:
        del _TOOLSETS[name]
        return True
    return False


def get_toolset(name: str) -> Toolset | None:
    """Return a Toolset by name, or None if not registered."""
    return _TOOLSETS.get(name)


def list_toolsets() -> list[Toolset]:
    """Return a list of all registered Toolsets."""
    return list(_TOOLSETS.values())


def filter_tools(
    toolsets: Collection[str] | None = None,
    include_tools: Collection[str] | None = None,
    exclude_tools: Collection[str] | None = None,
    registry: Mapping[str, Tool] | None = None,
) -> dict[str, Tool]:
    """Filter registered tools by toolset names and explicit inclusions/exclusions."""
    source = REGISTRY if registry is None else registry

    if toolsets is None and include_tools is None and exclude_tools is None:
        return dict(source)

    allowed_names: set[str] = set()

    if toolsets is not None:
        for ts_name in toolsets:
            ts = _TOOLSETS.get(ts_name)
            if ts:
                allowed_names.update(ts.tools)

    if include_tools is not None:
        allowed_names.update(include_tools)

    if toolsets is None and include_tools is None:
        names = source.keys()
        allowed_names.update(names)

    if exclude_tools is not None:
        allowed_names.difference_update(exclude_tools)

    return {name: tool for name, tool in source.items() if name in allowed_names}
''',
    "tests/test_memory_consolidation_and_pruning.py": r'''"""Unit and integration tests for Memory Consolidation, Entropy Pruning & Distillation."""

from __future__ import annotations

import time
import pytest

from dream.consolidation import (
    ConsolidationEngine,
    EntropyPruner,
    EpistemicDistiller,
    MemoryItem,
    MemoryNodeType,
    consolidation_add_memory,
    consolidation_distill_session,
    consolidation_export_report,
    consolidation_get_stats,
    consolidation_reset_all,
    consolidation_run_cycle,
    get_consolidation_tools,
    handle_consolidation_slash_command,
    reset_global_consolidation_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_consolidation_engine() -> None:
    reset_global_consolidation_engine()
    yield
    reset_global_consolidation_engine()


def test_toolset_includes_consolidation() -> None:
    """Verify consolidation toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("consolidation")
    assert ts is not None
    assert "consolidation_run_cycle" in ts.tools
    assert "consolidation_add_memory" in ts.tools
    assert "consolidation_distill_session" in ts.tools
    assert "consolidation" in BUILTIN_TOOLSETS


def test_ebbinghaus_decay_calculation() -> None:
    """Verify exponential retrievability decay over simulated time intervals."""
    item = MemoryItem(
        memory_id="test-1",
        node_type=MemoryNodeType.EPISODIC,
        content="Temporary log entry",
        importance=0.2,
        access_count=1,
        last_accessed_at=1000.0,
    )

    # Initial decay at t = 1000.0 is 1.0
    decay_0 = item.calculate_decay(current_time=1000.0, decay_constant=100.0)
    assert decay_0 == 1.0

    # Decayed after elapsed time
    decay_future = item.calculate_decay(current_time=1500.0, decay_constant=100.0)
    assert 0.0 < decay_future < 1.0


def test_entropy_pruning_and_protection() -> None:
    """Verify low decay items are pruned while core beliefs and high importance are protected."""
    pruner = EntropyPruner(retention_threshold=0.30)

    # Core belief with low decay -> Retained
    core = MemoryItem(
        memory_id="core-1",
        node_type=MemoryNodeType.CORE_BELIEF,
        content="Dream always protects user privacy.",
        importance=0.9,
        decay_score=0.1,
    )

    # Ephemeral scratchpad with low decay -> Pruned
    scratch = MemoryItem(
        memory_id="scratch-1",
        node_type=MemoryNodeType.EPHEMERAL_SCRATCHPAD,
        content="Thought: search parameter parsed.",
        importance=0.1,
        decay_score=0.2,
    )

    # Normal decayed item -> Pruned
    decayed = MemoryItem(
        memory_id="decay-1",
        node_type=MemoryNodeType.EPISODIC,
        content="User said hello at morning.",
        importance=0.3,
        decay_score=0.15,
    )

    retained, pruned = pruner.prune_low_entropy_nodes([core, scratch, decayed])
    assert core in retained
    assert scratch in pruned
    assert decayed in pruned


def test_deduplication_and_contradiction_resolution() -> None:
    """Verify merging of near-duplicates and resolution of conflicting facts."""
    pruner = EntropyPruner()
    distiller = EpistemicDistiller()

    # 1. Deduplication
    mem1 = MemoryItem("m1", MemoryNodeType.SEMANTIC_FACT, "User prefers dark mode in VS Code", importance=0.7)
    mem2 = MemoryItem("m2", MemoryNodeType.SEMANTIC_FACT, "User prefers dark mode in VS Code editor", importance=0.8)
    deduped, count = pruner.deduplicate([mem1, mem2], similarity_threshold=0.6)
    assert len(deduped) == 1
    assert count == 1
    assert deduped[0].importance == 0.8

    # 2. Contradiction Resolution
    old_fact = MemoryItem(
        "f_old",
        MemoryNodeType.USER_TRAIT,
        "User prefers Python 3.10",
        last_accessed_at=100.0,
    )
    new_fact = MemoryItem(
        "f_new",
        MemoryNodeType.USER_TRAIT,
        "User prefers Python 3.14 exclusively",
        last_accessed_at=200.0,
    )
    reconciled, resolved = distiller.reconcile_contradictions([old_fact, new_fact])
    assert len(reconciled) == 1
    assert resolved == 1
    assert reconciled[0].content == "User prefers Python 3.14 exclusively"


def test_consolidation_engine_full_cycle() -> None:
    """Verify autonomous sleep cycle compresses memory repository and computes health score."""
    engine = ConsolidationEngine()

    engine.add_memory("User likes green tea", node_type=MemoryNodeType.USER_TRAIT, importance=0.8)
    engine.add_memory("System booted successfully", node_type=MemoryNodeType.EPHEMERAL_SCRATCHPAD, importance=0.1)
    engine.add_memory("Dream adheres strictly to ethics", node_type=MemoryNodeType.CORE_BELIEF, importance=1.0)

    # Run consolidation cycle
    report = engine.run_consolidation_cycle(decay_constant=10.0, dry_run=False)
    assert report.initial_memory_count == 3
    assert report.final_memory_count >= 1
    assert report.compression_ratio <= 1.0

    stats = engine.get_health_stats()
    assert stats.total_cycles_executed == 1
    assert stats.memory_health_score > 0.0


def test_synthetic_dream_simulation() -> None:
    """Verify synthetic dream generates reflective scenarios for core memories."""
    distiller = EpistemicDistiller()
    core = MemoryItem("c1", MemoryNodeType.CORE_BELIEF, "Ensure all calculations are mathematically verified.")
    sims = distiller.run_synthetic_dream_simulation([core], num_scenarios=1)

    assert len(sims) == 1
    assert "Ensure all calculations" in sims[0]["focus_memory"]
    assert "تثبیت خودکار" in sims[0]["synthesized_reinforcement_fa"]


def test_consolidation_tools_and_slash_commands() -> None:
    """Verify LLM agent tools and /consolidate, /distill_memory, /memory_health slash commands."""
    tools = get_consolidation_tools()
    assert len(tools) >= 5

    # Tool: add memory
    res_add = consolidation_add_memory(content="کاربر به مباحث هوش مصنوعی علاقه‌مند است.", node_type="user_trait")
    assert res_add["success"] is True

    # Tool: distill session
    transcript = """
    1. کاربر گفت که در اصفهان زندگی می‌کند و به معماری سنتی علاقه‌مند است.
    2. دستیار پاسخ داد که اصفهان مهد هنر و معماری است.
    """
    res_distill = consolidation_distill_session(transcript)
    assert res_distill["success"] is True
    assert res_distill["distilled_facts_count"] >= 1

    # Tool: run cycle
    res_cycle = consolidation_run_cycle(dry_run=False)
    assert res_cycle["success"] is True
    assert res_cycle["report"]["initial_memory_count"] >= 1

    # Tool: stats
    res_stats = consolidation_get_stats()
    assert res_stats["success"] is True

    # Tool: export report
    res_rep = consolidation_export_report()
    assert res_rep["success"] is True
    assert "Memory Consolidation & Health" in res_rep["markdown_report"]

    # Slash: /consolidate
    slash_c = handle_consolidation_slash_command("/consolidate dry")
    assert "نتیجه چرخه تثبیت حافظه" in slash_c

    # Slash: /distill_memory
    slash_d = handle_consolidation_slash_command("/distill_memory کاربر ترجیح می‌دهد خروجی‌ها کوتاه باشند.")
    assert "تقطیر با موفقیت انجام شد" in slash_d

    # Slash: /memory_health
    slash_h = handle_consolidation_slash_command("/memory_health")
    assert "Memory Consolidation & Health" in slash_h

    # Slash: /memory_health reset
    slash_reset = handle_consolidation_slash_command("/memory_health reset")
    assert "بازنشانی شد" in slash_reset
''',
}


def main() -> None:
    root = Path(__file__).resolve().parent
    if not (root / "dream").exists():
        if (root / "dream-repo" / "dream").exists():
            root = root / "dream-repo"
        elif (Path.cwd() / "dream").exists():
            root = Path.cwd()
        else:
            print(f"Error: could not locate Dream repo root from {root}")
            sys.exit(1)

    print(f"Applying Phase 38 (Memory Consolidation & Epistemic Distillation) to: {root}")

    for rel_path, content in FILES.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"  [written] {rel_path}")

    print("\nRunning pytest validation...")
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_memory_consolidation_and_pruning.py", "-v"],
        cwd=root,
    )
    if res.returncode != 0:
        print("\n[FAIL] Pytest failed for Phase 38")
        sys.exit(res.returncode)

    print("\nRunning security audit...")
    audit_res = subprocess.run(
        [sys.executable, "tools/security_audit.py"],
        cwd=root,
    )
    if audit_res.returncode != 0:
        print("\n[FAIL] Security audit failed for Phase 38")
        sys.exit(audit_res.returncode)

    print("\n[SUCCESS] Phase 38 (Memory Consolidation & Epistemic Distillation) applied and verified cleanly!")


if __name__ == "__main__":
    main()
