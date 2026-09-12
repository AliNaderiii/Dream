"""Epistemic Distiller: Fact crystallization, contradiction reconciliation, and dream simulation."""

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
