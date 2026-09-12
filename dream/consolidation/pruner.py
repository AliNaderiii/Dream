"""Entropy Pruning and Ebbinghaus Forgetting Curve Memory Cleaner."""

from __future__ import annotations

import time

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
                        existing.last_accessed_at = max(
                            existing.last_accessed_at, item.last_accessed_at
                        )
                        existing.decay_score = max(existing.decay_score, item.decay_score)
                        matched = True
                        merged_count += 1
                        break

            if not matched:
                unique_memories.append(item)

        return unique_memories, merged_count
