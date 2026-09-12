"""LLM agent tools and singleton managers for the Universal Migration Subsystem."""

from __future__ import annotations

import logging
from typing import Any

from dream.migration.engine import MigrationEngine
from dream.migration.types import MigrationOptions, MigrationSourceType

logger = logging.getLogger(__name__)

_GLOBAL_MIGRATION_ENGINE: MigrationEngine | None = None


def get_global_migration_engine() -> MigrationEngine:
    """Retrieve or instantiate singleton MigrationEngine."""
    global _GLOBAL_MIGRATION_ENGINE
    if _GLOBAL_MIGRATION_ENGINE is None:
        _GLOBAL_MIGRATION_ENGINE = MigrationEngine()
    return _GLOBAL_MIGRATION_ENGINE


def reset_global_migration_engine() -> None:
    """Reset the global MigrationEngine instance (for test isolation)."""
    global _GLOBAL_MIGRATION_ENGINE
    if _GLOBAL_MIGRATION_ENGINE is not None:
        _GLOBAL_MIGRATION_ENGINE.reset()
    _GLOBAL_MIGRATION_ENGINE = None


def migration_analyze_source(
    source_path: str,
    source_type: str = "auto",
) -> dict[str, Any]:
    """Inspect and analyze external agent workspace (Hermes, OpenClaw, Markdown) before import.

    Args:
        source_path: Absolute or relative directory path of external workspace.
        source_type: Source format ('hermes', 'openclaw', 'generic_md', or 'auto').
    """
    engine = get_global_migration_engine()
    try:
        stype = MigrationSourceType(source_type.lower())
    except ValueError:
        stype = MigrationSourceType.AUTO

    try:
        plan = engine.analyze_source(source_path, source_type=stype)
        return {
            "success": True,
            "plan": plan.to_dict(),
            "message_fa": (
                f"تحلیل مسیر با موفقیت انجام شد: {plan.total_discovered_items} آیتم "
                f"برای انتقال شناسایی گردید."
            ),
        }
    except Exception as exc:
        logger.error(f"Migration analysis error: {exc}")
        return {
            "success": False,
            "error": str(exc),
            "message_fa": f"خطا در تحلیل مسیر مهاجرت: {exc}",
        }


def migration_execute(
    source_path: str,
    source_type: str = "auto",
    dry_run: bool = False,
    import_skills: bool = True,
    import_memories: bool = True,
    normalize_persian: bool = True,
    target_dir: str = "",
) -> dict[str, Any]:
    """Execute complete data migration and schema conversion from Hermes/OpenClaw into Dream.

    Args:
        source_path: Directory path containing the agent files.
        source_type: Framework type ('hermes', 'openclaw', 'generic_md', 'auto').
        dry_run: If True, simulates the migration without writing files to disk.
        import_skills: Whether to import custom skills and tool modules.
        import_memories: Whether to import SOUL.md, USER.md, and MEMORY.md notes.
        normalize_persian: Standardize Persian typography and Arabic character shapes.
        target_dir: Optional custom destination path for imported files.
    """
    engine = get_global_migration_engine()
    try:
        stype = MigrationSourceType(source_type.lower())
    except ValueError:
        stype = MigrationSourceType.AUTO

    options = MigrationOptions(
        dry_run=dry_run,
        import_skills=import_skills,
        import_memories=import_memories,
        normalize_persian=normalize_persian,
        target_dir=target_dir,
    )

    try:
        report = engine.execute_migration(source_path, options=options, source_type=stype)
        return {
            "success": report.status.value != "failed",
            "report": report.to_dict(),
            "summary_fa": report.summary_fa,
        }
    except Exception as exc:
        logger.error(f"Migration execution error: {exc}")
        return {
            "success": False,
            "error": str(exc),
            "summary_fa": f"خطا در اجرای عملیات مهاجرت: {exc}",
        }


def migration_get_status() -> dict[str, Any]:
    """Retrieve operational status, active blueprints, and historical migration logs."""
    engine = get_global_migration_engine()
    status = engine.get_status()
    return {"success": True, **status}


def migration_export_report() -> dict[str, Any]:
    """Export formatted Markdown audit log of the most recent migration."""
    engine = get_global_migration_engine()
    md_rep = engine.format_migration_report()
    return {"success": True, "markdown_report": md_rep}


def migration_reset() -> dict[str, Any]:
    """Reset migration history and cached blueprints."""
    reset_global_migration_engine()
    return {"success": True, "message_fa": "حافظه و وضعیت سیستم مهاجرت بازنشانی شد."}


def get_migration_tools() -> list[dict[str, Any]]:
    """Return tool manifests for LLM registration."""
    return [
        {
            "name": "migration_analyze_source",
            "description": (
                "Inspect and analyze an external agent directory (Hermes or OpenClaw) "
                "before migration.\n"
                "بررسی و تحلیل ساختار پوشه عامل‌های خارجی قبل از مهاجرت."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source_path": {"type": "string", "description": "Workspace directory path"},
                    "source_type": {
                        "type": "string",
                        "enum": ["hermes", "openclaw", "generic_md", "auto"],
                        "default": "auto",
                    },
                },
                "required": ["source_path"],
            },
            "handler": migration_analyze_source,
        },
        {
            "name": "migration_execute",
            "description": (
                "Migrate memories, context files, skills, and settings from Hermes or "
                "OpenClaw into Dream.\n"
                "انتقال کامل حافظه‌ها، مهارت‌ها و تنظیمات از هرمس و اوپن‌کلا به دریم."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source_path": {"type": "string", "description": "Source workspace directory"},
                    "source_type": {
                        "type": "string",
                        "enum": ["hermes", "openclaw", "generic_md", "auto"],
                        "default": "auto",
                    },
                    "dry_run": {"type": "boolean", "default": False},
                    "import_skills": {"type": "boolean", "default": True},
                    "import_memories": {"type": "boolean", "default": True},
                    "normalize_persian": {"type": "boolean", "default": True},
                },
                "required": ["source_path"],
            },
            "handler": migration_execute,
        },
        {
            "name": "migration_get_status",
            "description": "Get migration statistics and execution logs.",
            "parameters": {"type": "object", "properties": {}},
            "handler": migration_get_status,
        },
        {
            "name": "migration_export_report",
            "description": "Export detailed Markdown report of the latest migration.",
            "parameters": {"type": "object", "properties": {}},
            "handler": migration_export_report,
        },
    ]
