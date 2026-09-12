"""Data models, enums, and schemas for the Universal Migration Subsystem."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MigrationSourceType(str, Enum):
    """Supported source agent architectures and formats."""

    HERMES = "hermes"
    OPENCLAW = "openclaw"
    GENERIC_MD = "generic_md"
    DIRECT_JSON = "direct_json"
    AUTO = "auto"


class MigrationItemType(str, Enum):
    """Categories of migrated data artifacts."""

    SOUL = "soul"
    USER_PROFILE = "user_profile"
    MEMORY_NOTE = "memory_note"
    SKILL = "skill"
    CONFIG = "config"
    CONVERSATION = "conversation"
    SUBAGENT = "subagent"


class MigrationStatus(str, Enum):
    """Status lifecycle of a migration session."""

    PENDING = "pending"
    ANALYZING = "analyzing"
    READY = "ready"
    IMPORTING = "importing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class MigratedItem:
    """Individual data payload extracted and converted from external agent."""

    item_id: str
    item_type: MigrationItemType
    title: str
    content: str
    source_path: str
    target_destination: str
    metadata: dict[str, Any] = field(default_factory=dict)
    is_persian_normalized: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize item to dictionary."""
        return {
            "item_id": self.item_id,
            "item_type": self.item_type.value,
            "title": self.title,
            "content": self.content,
            "source_path": self.source_path,
            "target_destination": self.target_destination,
            "metadata": self.metadata,
            "is_persian_normalized": self.is_persian_normalized,
        }


@dataclass(slots=True)
class MigrationOptions:
    """Configurable knobs for controlling the migration pipeline."""

    dry_run: bool = False
    normalize_persian: bool = True
    import_memories: bool = True
    import_skills: bool = True
    import_configs: bool = True
    import_conversations: bool = False
    auto_resolve_conflicts: bool = True
    target_dir: str = ""


@dataclass(slots=True)
class MigrationPlan:
    """Pre-migration inspection blueprint and conversion forecast."""

    plan_id: str
    source_type: MigrationSourceType
    source_root: str
    total_discovered_items: int
    items_by_type: dict[str, int]
    items: list[MigratedItem]
    estimated_memories_count: int
    estimated_skills_count: int
    warnings: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize migration plan to dictionary."""
        return {
            "plan_id": self.plan_id,
            "source_type": self.source_type.value,
            "source_root": self.source_root,
            "total_discovered_items": self.total_discovered_items,
            "items_by_type": self.items_by_type,
            "items": [item.to_dict() for item in self.items],
            "estimated_memories_count": self.estimated_memories_count,
            "estimated_skills_count": self.estimated_skills_count,
            "warnings": self.warnings,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class MigrationReport:
    """Final outcome, metrics, and audit log of completed migration."""

    migration_id: str
    source_type: MigrationSourceType
    status: MigrationStatus
    total_imported: int
    memories_imported: int
    skills_imported: int
    configs_imported: int
    persian_terms_normalized: int
    conflicts_resolved: int
    duration_ms: float
    summary_fa: str
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize migration report to dictionary."""
        return {
            "migration_id": self.migration_id,
            "source_type": self.source_type.value,
            "status": self.status.value,
            "total_imported": self.total_imported,
            "memories_imported": self.memories_imported,
            "skills_imported": self.skills_imported,
            "configs_imported": self.configs_imported,
            "persian_terms_normalized": self.persian_terms_normalized,
            "conflicts_resolved": self.conflicts_resolved,
            "duration_ms": self.duration_ms,
            "summary_fa": self.summary_fa,
            "warnings": self.warnings,
            "errors": self.errors,
            "timestamp": self.timestamp,
        }
