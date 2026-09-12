"""Domain models and data structures for Memory Consolidation & Distillation."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MemoryNodeType(str, Enum):
    """Classification of stored memory items."""

    EPISODIC = "episodic"  # Raw conversational turn or event log
    SEMANTIC_FACT = "semantic_fact"  # Distilled timeless factual statement
    CORE_BELIEF = "core_belief"  # High-priority user premise or core invariant
    USER_TRAIT = "user_trait"  # User preference, behavioral habit, or style
    EPHEMERAL_SCRATCHPAD = "ephemeral_scratchpad"  # Intermediate thoughts


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
    importance: float = 0.5  # Value between 0.0 (trivial) and 1.0 (vital)
    access_count: int = 1
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)
    decay_score: float = 1.0  # Retrievability R = e^(-t/S)
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
    memory_health_score: float  # 0.0 to 1.0 (Higher means compact, low noise)

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
