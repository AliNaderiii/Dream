"""Consolidation Engine Coordinator: Sleep-phase memory consolidation, pruning, and health metrics."""

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
