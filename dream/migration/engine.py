"""Migration Engine Orchestrator: Universal importing and conversion pipeline."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any

from dream.migration.hermes_adapter import HermesMigrationAdapter
from dream.migration.openclaw_adapter import OpenClawMigrationAdapter
from dream.migration.sanitizer import MigrationSanitizer
from dream.migration.types import (
    MigratedItem,
    MigrationItemType,
    MigrationOptions,
    MigrationPlan,
    MigrationReport,
    MigrationSourceType,
    MigrationStatus,
)

logger = logging.getLogger(__name__)


class MigrationEngine:
    """End-to-end migration coordinator converting external agent data into Dream format."""

    def __init__(
        self,
        sanitizer: MigrationSanitizer | None = None,
        hermes_adapter: HermesMigrationAdapter | None = None,
        openclaw_adapter: OpenClawMigrationAdapter | None = None,
    ) -> None:
        self.sanitizer = sanitizer or MigrationSanitizer()
        self.hermes_adapter = hermes_adapter or HermesMigrationAdapter(self.sanitizer)
        self.openclaw_adapter = openclaw_adapter or OpenClawMigrationAdapter(self.sanitizer)

        self._reports_history: list[MigrationReport] = []
        self._last_plan: MigrationPlan | None = None

    def auto_detect_source_type(self, root_dir: str | Path) -> MigrationSourceType:
        """Inspect files to determine whether source is Hermes, OpenClaw, or generic."""
        p = Path(root_dir)
        if not p.exists() or not p.is_dir():
            return MigrationSourceType.GENERIC_MD

        # Hermes hallmarks
        if (p / "SOUL.md").exists() or (p / "MEMORY.md").exists() or (p / ".hermes").exists():
            return MigrationSourceType.HERMES

        # OpenClaw hallmarks
        if (p / "claw.json").exists() or (p / "openclaw.json").exists():
            return MigrationSourceType.OPENCLAW

        # Check for JSON data store
        if (p / "memory_store.json").exists():
            return MigrationSourceType.DIRECT_JSON

        return MigrationSourceType.GENERIC_MD

    def analyze_source(
        self,
        source_path: str,
        source_type: MigrationSourceType = MigrationSourceType.AUTO,
    ) -> MigrationPlan:
        """Inspect source workspace and formulate a pre-migration execution plan."""
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"

        if not self.sanitizer.is_safe_source_path(source_path):
            raise PermissionError(f"Access to path '{source_path}' is blocked by security policy.")

        p = Path(source_path)
        if not p.exists():
            raise FileNotFoundError(f"Source path '{source_path}' does not exist.")

        stype = (
            self.auto_detect_source_type(p)
            if source_type == MigrationSourceType.AUTO
            else source_type
        )

        items: list[MigratedItem] = []
        warnings: list[str] = []

        if stype == MigrationSourceType.HERMES:
            items = self.hermes_adapter.inspect_workspace(p)
        elif stype == MigrationSourceType.OPENCLAW:
            items = self.openclaw_adapter.inspect_workspace(p)
        else:
            items = self._inspect_generic_workspace(p)

        if not items:
            warnings.append("هیچ فایل سازگاری برای مهاجرت در این مسیر یافت نشد.")

        # Aggregate counts by item type
        counts: dict[str, int] = {}
        for item in items:
            counts[item.item_type.value] = counts.get(item.item_type.value, 0) + 1

        mem_count = counts.get(MigrationItemType.MEMORY_NOTE.value, 0)
        skills_count = counts.get(MigrationItemType.SKILL.value, 0)

        plan = MigrationPlan(
            plan_id=plan_id,
            source_type=stype,
            source_root=str(p.resolve()),
            total_discovered_items=len(items),
            items_by_type=counts,
            items=items,
            estimated_memories_count=mem_count,
            estimated_skills_count=skills_count,
            warnings=warnings,
        )

        self._last_plan = plan
        return plan

    def execute_migration(
        self,
        source_path: str,
        options: MigrationOptions | None = None,
        source_type: MigrationSourceType = MigrationSourceType.AUTO,
    ) -> MigrationReport:
        """Execute complete conversion and import pipeline into Dream."""
        start_time = time.time()
        opts = options or MigrationOptions()
        migration_id = f"mig_{uuid.uuid4().hex[:8]}"

        plan = self.analyze_source(source_path, source_type=source_type)

        total_imported = 0
        memories_imported = 0
        skills_imported = 0
        configs_imported = 0
        persian_norm_count = 0
        conflicts_resolved = 0
        warnings: list[str] = list(plan.warnings)
        errors: list[str] = []

        # Determine target base directory
        target_root = Path(opts.target_dir) if opts.target_dir else Path.home() / ".dream"

        for item in plan.items:
            # Filter by options
            if item.item_type == MigrationItemType.MEMORY_NOTE and not opts.import_memories:
                continue
            if item.item_type == MigrationItemType.SKILL and not opts.import_skills:
                continue
            if item.item_type == MigrationItemType.CONFIG and not opts.import_configs:
                continue

            # Persian normalization tally
            norm_content, n_count = (
                self.sanitizer.normalize_persian_text(item.content)
                if opts.normalize_persian
                else (item.content, 0)
            )
            persian_norm_count += n_count

            # Write or simulate target file creation
            if not opts.dry_run:
                try:
                    dest_path = target_root / item.target_destination
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    dest_path.write_text(norm_content, encoding="utf-8")
                except Exception as exc:
                    errors.append(f"Failed to write {item.target_destination}: {exc}")
                    continue

            total_imported += 1
            if item.item_type == MigrationItemType.MEMORY_NOTE:
                memories_imported += 1
            elif item.item_type == MigrationItemType.SKILL:
                skills_imported += 1
            elif item.item_type == MigrationItemType.CONFIG:
                configs_imported += 1

        duration_ms = (time.time() - start_time) * 1000
        mode_label = "شبیه‌سازی" if opts.dry_run else "انتقال نهایی"
        summary_fa = (
            f"🔄 عملیات {mode_label} از {plan.source_type.value.upper()} "
            f"با موفقیت انجام شد: {total_imported} آیتم وارد شد "
            f"({memories_imported} حافظه، {skills_imported} مهارت، "
            f"{configs_imported} پیکربندی) و {persian_norm_count} واژه فارسی استاندارد گردید."
        )

        status = MigrationStatus.FAILED if errors else MigrationStatus.COMPLETED

        report = MigrationReport(
            migration_id=migration_id,
            source_type=plan.source_type,
            status=status,
            total_imported=total_imported,
            memories_imported=memories_imported,
            skills_imported=skills_imported,
            configs_imported=configs_imported,
            persian_terms_normalized=persian_norm_count,
            conflicts_resolved=conflicts_resolved,
            duration_ms=duration_ms,
            summary_fa=summary_fa,
            warnings=warnings,
            errors=errors,
        )

        self._reports_history.append(report)
        return report

    def _inspect_generic_workspace(self, root_dir: Path) -> list[MigratedItem]:
        """Discover generic Markdown notes and text files."""
        items: list[MigratedItem] = []
        for f in root_dir.glob("*.md"):
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                norm_c, changes = self.sanitizer.normalize_persian_text(content)
                items.append(
                    MigratedItem(
                        item_id=f"doc_{f.stem}",
                        item_type=MigrationItemType.MEMORY_NOTE,
                        title=f"Document: {f.name}",
                        content=norm_c,
                        source_path=str(f),
                        target_destination=f"memory/{f.name}",
                        metadata={"filename": f.name},
                        is_persian_normalized=changes > 0,
                    )
                )
            except Exception as exc:
                logger.warning(f"Failed to read generic doc {f}: {exc}")

        return items

    def get_status(self) -> dict[str, Any]:
        """Return operational status and historical migration logs."""
        return {
            "total_migrations_executed": len(self._reports_history),
            "last_plan": self._last_plan.to_dict() if self._last_plan else None,
            "recent_reports": [r.to_dict() for r in self._reports_history[-5:]],
        }

    def format_migration_report(self) -> str:
        """Format the latest migration report as a readable Markdown document."""
        if not self._reports_history:
            return "## 🔄 گزارش مهاجرت (Migration Report)\n- تاکنون عملیات مهاجرتی ثبت نشده است."

        rep = self._reports_history[-1]
        lines = [
            "## 🔄 گزارش جامع مهاجرت به Dream (Universal Migration Report)",
            f"- **شناسه عملیات:** `{rep.migration_id}`",
            f"- **مبدأ مهاجرت:** `{rep.source_type.value.upper()}`",
            f"- **وضعیت:** `{rep.status.value.upper()}`",
            f"- **کل آیتم‌های منتقل‌شده:** {rep.total_imported}",
            f"- **حافظه‌ها و یادداشت‌ها:** {rep.memories_imported}",
            f"- **مهارت‌ها و افزونه‌ها:** {rep.skills_imported}",
            f"- **تنظیمات و پیکربندی:** {rep.configs_imported}",
            f"- **اصلاح و نرمال‌سازی حروف فارسی:** {rep.persian_terms_normalized} مورد",
            f"- **مدت زمان اجرا:** {rep.duration_ms:.2f} میلی‌ثانیه",
            "",
            f"**خلاصه فارسی:** {rep.summary_fa}",
        ]

        if rep.warnings:
            lines.append("\n### ⚠️ هشدارها:")
            for w in rep.warnings:
                lines.append(f"- {w}")

        if rep.errors:
            lines.append("\n### ❌ خطاها:")
            for e in rep.errors:
                lines.append(f"- {e}")

        return "\n".join(lines)

    def reset(self) -> None:
        """Reset internal history and cached blueprints."""
        self._reports_history.clear()
        self._last_plan = None
