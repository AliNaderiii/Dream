"""Refactor Engine Orchestrator and Code Intelligence Lifecycle Manager."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any

from dream.refactor.patcher import DeterministicPatcher
from dream.refactor.symbol_index import ASTSymbolIndexer
from dream.refactor.types import (
    CodeSymbol,
    PatchChange,
    PatchStatus,
    RefactorPlan,
    RefactorReport,
)

logger = logging.getLogger(__name__)


class RefactorEngine:
    """Coordinates symbol indexing, AST-validated patch generation, and atomic code refactoring."""

    def __init__(
        self,
        indexer: ASTSymbolIndexer | None = None,
        patcher: DeterministicPatcher | None = None,
    ) -> None:
        self.indexer = indexer or ASTSymbolIndexer()
        self.patcher = patcher or DeterministicPatcher()
        self._plans: dict[str, RefactorPlan] = {}
        self._reports: list[RefactorReport] = []

    def index_directory(self, root_dir: str | Path) -> int:
        """Scan directory and index all Python symbols."""
        root = Path(root_dir)
        total_symbols = 0
        if not root.exists():
            return 0

        for path in root.rglob("*.py"):
            try:
                code = path.read_text(encoding="utf-8")
                syms = self.indexer.index_source_code(str(path), code)
                total_symbols += len(syms)
            except Exception as exc:
                logger.debug(f"Skipped indexing {path}: {exc}")

        return total_symbols

    def find_symbols(self, query: str) -> list[CodeSymbol]:
        """Search symbol graph by name or substring."""
        return self.indexer.find_symbol(query)

    def create_refactor_plan(
        self,
        goal_fa: str,
        file_modifications: list[dict[str, str]],
    ) -> RefactorPlan:
        """Construct refactor plan with AST verification for each modified file."""
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        changes: list[PatchChange] = []

        for mod in file_modifications:
            f_path = mod["file_path"]
            old_c = mod.get("old_content", "")
            new_c = mod["new_content"]

            if not old_c and Path(f_path).exists():
                old_c = Path(f_path).read_text(encoding="utf-8")

            patch = self.patcher.create_patch(f_path, old_c, new_c)
            changes.append(patch)

        all_valid = all(c.ast_valid for c in changes)
        status = PatchStatus.VALIDATED if all_valid else PatchStatus.FAILED

        plan = RefactorPlan(
            plan_id=plan_id,
            goal_fa=goal_fa,
            changes=changes,
            status=status,
        )
        self._plans[plan_id] = plan
        return plan

    def apply_plan(self, plan_id: str) -> RefactorReport:
        """Apply all patches in a refactoring plan atomically."""
        start_time = time.time()
        plan = self._plans.get(plan_id)
        if not plan:
            raise KeyError(f"Refactor plan '{plan_id}' not found.")

        if plan.status == PatchStatus.FAILED:
            raise ValueError("Cannot apply refactoring plan with syntax validation errors.")

        applied_files: list[str] = []
        diff_snippets: list[str] = []

        try:
            for patch in plan.changes:
                self.patcher.apply_patch(patch, backup=True)
                applied_files.append(patch.file_path)
                if patch.diff_unified:
                    diff_snippets.append(patch.diff_unified)

            plan.status = PatchStatus.APPLIED
            plan.applied_at = time.time()
            summary_fa = (
                f"طرح بازآرایی '{plan.goal_fa}' با موفقیت روی {len(applied_files)} فایل اعمال شد."
            )
        except Exception as exc:
            logger.error(f"Error applying plan {plan_id}: {exc}. Rolling back.")
            self.rollback_plan(plan_id)
            plan.status = PatchStatus.FAILED
            summary_fa = f"خطا در اعمال بازآرایی: {exc}. تغییرات لغو شدند."

        duration_ms = (time.time() - start_time) * 1000
        report = RefactorReport(
            plan_id=plan.plan_id,
            status=plan.status,
            files_modified=applied_files,
            syntax_valid=plan.status == PatchStatus.APPLIED,
            summary_fa=summary_fa,
            diff_summary="\n".join(diff_snippets),
            duration_ms=duration_ms,
        )
        self._reports.append(report)
        return report

    def rollback_plan(self, plan_id: str) -> bool:
        """Rollback all applied file changes in a plan."""
        plan = self._plans.get(plan_id)
        if not plan:
            raise KeyError(f"Refactor plan '{plan_id}' not found.")

        for patch in plan.changes:
            self.patcher.rollback_patch(patch)

        plan.status = PatchStatus.ROLLED_BACK
        return True

    def format_plan_markdown(self, plan_id: str) -> str:
        """Render a formatted diff preview of a refactoring plan."""
        plan = self._plans.get(plan_id)
        if not plan:
            return f"❌ طرح بازآرایی '{plan_id}' یافت نشد."

        validity_text = (
            "معتبر (AST Valid)" if plan.status != PatchStatus.FAILED else "خطای نحو (Syntax Error)"
        )
        lines = [
            f"## 🛠️ پیش‌نمایش طرح بازآرایی کد: {plan.goal_fa} (`{plan.plan_id}`)",
            f"- **وضعیت اعتبارسنجی نحو:** `{validity_text}`",
            f"- **تعداد فایل‌های هدف:** `{len(plan.changes)}`",
            "",
            "### 📄 تغییرات تفکیکی:",
        ]

        for patch in plan.changes:
            lines.append(f"#### فایل: `{patch.file_path}`")
            if patch.syntax_error:
                lines.append(f"⚠️ **خطای نحو:** `{patch.syntax_error}`")
            if patch.diff_unified:
                lines.extend([
                    "```diff",
                    patch.diff_unified.strip(),
                    "```",
                ])
            else:
                lines.append("- تغییری مشاهده نشد (محتوای یکسان).")

        return "\n".join(lines)

    def get_status(self) -> dict[str, Any]:
        """Return engine operational metrics and symbol counts."""
        return {
            "total_plans": len(self._plans),
            "total_reports": len(self._reports),
            "recent_plans": [p.to_dict() for p in list(self._plans.values())[-5:]],
        }

    def reset(self) -> None:
        """Clear all indexed symbols, plans, and reports."""
        self.indexer.clear()
        self._plans.clear()
        self._reports.clear()
