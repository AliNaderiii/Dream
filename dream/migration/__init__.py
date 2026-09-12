"""Universal Migration Subsystem for Hermes Agent, OpenClaw, and External Frameworks."""

from __future__ import annotations

from dream.migration.engine import MigrationEngine
from dream.migration.hermes_adapter import HermesMigrationAdapter
from dream.migration.openclaw_adapter import OpenClawMigrationAdapter
from dream.migration.sanitizer import MigrationSanitizer
from dream.migration.slash import handle_migration_slash_command
from dream.migration.tools import (
    get_global_migration_engine,
    get_migration_tools,
    migration_analyze_source,
    migration_execute,
    migration_export_report,
    migration_get_status,
    migration_reset,
    reset_global_migration_engine,
)
from dream.migration.types import (
    MigratedItem,
    MigrationItemType,
    MigrationOptions,
    MigrationPlan,
    MigrationReport,
    MigrationSourceType,
    MigrationStatus,
)

__all__ = [
    "HermesMigrationAdapter",
    "MigratedItem",
    "MigrationEngine",
    "MigrationItemType",
    "MigrationOptions",
    "MigrationPlan",
    "MigrationReport",
    "MigrationSanitizer",
    "MigrationSourceType",
    "MigrationStatus",
    "OpenClawMigrationAdapter",
    "get_global_migration_engine",
    "get_migration_tools",
    "handle_migration_slash_command",
    "migration_analyze_source",
    "migration_execute",
    "migration_export_report",
    "migration_get_status",
    "migration_reset",
    "reset_global_migration_engine",
]
