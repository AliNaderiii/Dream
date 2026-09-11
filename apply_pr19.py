#!/usr/bin/env python3
"""apply_pr19.py - Standalone installer for Phase 16 / PR #19:
Skills Hub Ecosystem, Self-Improving Skill Synthesis & Portable Bundle Manager.

This installer creates or updates the following files in the target repository:
  - dream/skills/hub.py
  - dream/skills/evolution.py
  - dream/skills/bundle.py
  - dream/skills/hub_tools.py
  - dream/skills/hub_slash.py
  - dream/tools/toolsets.py
  - tests/test_skills_hub_and_evolution.py
"""

from __future__ import annotations

import sys
from pathlib import Path

SKILLS_HUB_PY = r'''"""Central community Skills Hub: discovery, installation, and lifecycle management."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dream.skills.format import validate_skill_name


@dataclass(slots=True)
class SkillHubManifest:
    """Metadata and package manifest for a community Hub skill."""

    name: str
    version: str = "1.0.0"
    author: str = "Dream Community"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=lambda: ["all"])
    dependencies: list[str] = field(default_factory=list)
    content_md: str = ""
    references: dict[str, str] = field(default_factory=dict)
    downloads: int = 0
    rating: float = 5.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "tags": self.tags,
            "platforms": self.platforms,
            "dependencies": self.dependencies,
            "references_count": len(self.references),
            "downloads": self.downloads,
            "rating": self.rating,
        }


# Curated Built-in Community Catalog (Iranian & International Skills)
_CURATED_HUB_CATALOG: dict[str, SkillHubManifest] = {
    "iran-tax-calculator": SkillHubManifest(
        name="iran-tax-calculator",
        version="1.2.0",
        author="Ali Naderi & Dream Team",
        description=(
            "محاسبه دقیق مالیات حقوق، مالیات بر ارزش افزوده و مالیات مشاغل "
            "بر اساس بخشنامه‌های جدید"
        ),
        tags=["iran", "tax", "finance", "fa", "accounting"],
        platforms=["all"],
        content_md="""---
name: iran-tax-calculator
description: محاسبه دقیق مالیات حقوق، مالیات بر ارزش افزوده و مالیات مشاغل
version: 1.2.0
---

# محاسبه مالیات ایران

## دستورالعمل:
1. دریافت ناخالص حقوق یا مبلغ فاکتور
2. کسر معافیت‌های قانونی مصوب سال جاری
3. اعمال پله‌های مالیاتی (۱۰٪، ۱۵٪، ۲۰٪، ۳۰٪)
4. ارائه تفکیک دقیق مالیات و درآمد خالص
""",
        references={"rules.md": "بخشنامه‌های مالیاتی سال ۱۴۰۳ و ۱۴۰۴ سازمان امور مالیاتی کشور"},
        downloads=1420,
        rating=4.9,
    ),
    "jalali-cron-planner": SkillHubManifest(
        name="jalali-cron-planner",
        version="1.0.1",
        author="Dream Core",
        description="زمان‌بندی هوشمند کارها و یادآورها بر اساس تقویم هجری شمسی و تعطیلات رسمی ایران",
        tags=["jalali", "calendar", "cron", "iran", "productivity"],
        platforms=["all"],
        content_md="""---
name: jalali-cron-planner
description: زمان‌بندی هوشمند کارها بر اساس تقویم جلالی
version: 1.0.1
---

# برنامه‌ریزی تقویم جلالی

## دستورالعمل:
1. استخراج مناسبت‌ها و تعطیلات رسمی تاریخ مورد نظر
2. محاسبه اختلاف روزهای کاری تا موعد تحویل
3. تنظیم یادآورهای متناسب با ساعات اداری ایران
""",
        references={},
        downloads=890,
        rating=4.8,
    ),
    "crypto-fiat-rates": SkillHubManifest(
        name="crypto-fiat-rates",
        version="1.1.0",
        author="FinTech Community",
        description="استعلام نرخ لحظه‌ای تتر، بیت‌کوین و ارزهای خارجی به ریال و تومان",
        tags=["crypto", "forex", "toman", "finance", "rates"],
        platforms=["all"],
        content_md="""---
name: crypto-fiat-rates
description: استعلام لحظه‌ای نرخ طلا، ارز و رمزارزها به تومان
version: 1.1.0
---

# نرخ ارز و رمزارز

## دستورالعمل:
1. استعلام آخرین نرخ تتر و دلار آزاد
2. تبدیل مقادیر رمزارزی به تومان با کارمزد شبکه
3. نمایش بازه نوسان ۲۴ ساعته
""",
        references={},
        downloads=2100,
        rating=4.95,
    ),
    "code-refactoring-pro": SkillHubManifest(
        name="code-refactoring-pro",
        version="2.0.0",
        author="Software Architecture Guild",
        description=(
            "Advanced automated code refactoring, type annotating, and SOLID clean architecture"
        ),
        tags=["coding", "python", "typescript", "architecture", "clean-code"],
        platforms=["all"],
        content_md="""---
name: code-refactoring-pro
description: Advanced code refactoring and clean architecture compliance
version: 2.0.0
---

# Code Refactoring Pro

## Instructions:
1. Identify code smells and cyclomatic complexity hotspots.
2. Apply SOLID principles and eliminate duplicate logic.
3. Add strict Python/TypeScript typing annotations.
4. Verify unit test backward-compatibility.
""",
        references={"patterns.md": "Design patterns and refactoring catalogs."},
        downloads=3450,
        rating=5.0,
    ),
    "persian-content-seo": SkillHubManifest(
        name="persian-content-seo",
        version="1.3.0",
        author="Digital Marketing Group",
        description="بهینه‌سازی و بازنویسی سئو مقالات فارسی با رعایت نیم‌فاصله‌ها و کلمات کلیدی LSI",
        tags=["seo", "persian", "content", "copywriting", "fa"],
        platforms=["all"],
        content_md="""---
name: persian-content-seo
description: بهینه‌سازی حرفه‌ای مقالات وبلاگ و سئو زبان فارسی
version: 1.3.0
---

# سئو محتوای فارسی

## دستورالعمل:
1. بررسی چگالی کلمات کلیدی اصلی و مترادف‌ها (LSI)
2. اصلاح ساختار تیترها (H1 تا H4)
3. اعمال قوانین نگارشی و نیم‌فاصله‌های استاندارد
4. تدوین متاتگ‌های عنوان و توضیحات جذاب
""",
        references={},
        downloads=1120,
        rating=4.85,
    ),
}


class SkillsHubCatalog:
    """Manager for browsing, downloading, and installing community skills."""

    def __init__(self, custom_catalog: dict[str, SkillHubManifest] | None = None) -> None:
        self.catalog = dict(_CURATED_HUB_CATALOG)
        if custom_catalog:
            self.catalog.update(custom_catalog)

    def search(self, query: str = "", tag: str | None = None) -> list[SkillHubManifest]:
        """Search skills by keyword matching in name, description, or tags."""
        q = query.strip().lower()
        results: list[SkillHubManifest] = []

        for skill in self.catalog.values():
            if tag and tag.lower() not in [t.lower() for t in skill.tags]:
                continue
            if not q:
                results.append(skill)
                continue

            # Check match
            in_name = q in skill.name.lower()
            in_desc = q in skill.description.lower()
            in_tags = any(q in t.lower() for t in skill.tags)
            if in_name or in_desc or in_tags:
                results.append(skill)

        results.sort(key=lambda s: (s.rating, s.downloads), reverse=True)
        return results

    def get_manifest(self, skill_name: str) -> SkillHubManifest | None:
        """Fetch manifest of a specific skill."""
        return self.catalog.get(skill_name.strip().lower())

    def install(self, skill_name: str, target_dir: Path | str) -> dict[str, Any]:
        """Install a hub skill into workspace directory with SKILL.md and references."""
        manifest = self.get_manifest(skill_name)
        if not manifest:
            return {
                "success": False,
                "error": f"Skill '{skill_name}' not found in Skills Hub catalog.",
            }

        try:
            valid_name = validate_skill_name(manifest.name)
        except Exception as err:
            return {"success": False, "error": f"Invalid skill name: {err}"}

        base_dir = Path(target_dir)
        skill_path = base_dir / valid_name
        skill_path.mkdir(parents=True, exist_ok=True)

        # Write SKILL.md
        skill_file = skill_path / "SKILL.md"
        skill_file.write_text(manifest.content_md.strip() + "\n", encoding="utf-8")

        # Write references if any
        ref_files = []
        if manifest.references:
            ref_dir = skill_path / "references"
            ref_dir.mkdir(parents=True, exist_ok=True)
            for ref_name, ref_body in manifest.references.items():
                ref_file = ref_dir / ref_name
                ref_file.write_text(ref_body.strip() + "\n", encoding="utf-8")
                ref_files.append(ref_name)

        manifest.downloads += 1
        return {
            "success": True,
            "name": manifest.name,
            "version": manifest.version,
            "installed_path": str(skill_path),
            "files": ["SKILL.md"] + ref_files,
        }

    def uninstall(self, skill_name: str, target_dir: Path | str) -> dict[str, Any]:
        """Remove an installed skill from the local workspace."""
        base_dir = Path(target_dir)
        skill_path = base_dir / skill_name
        if not skill_path.exists():
            return {
                "success": False,
                "error": f"Skill '{skill_name}' is not installed at {skill_path}.",
            }

        import shutil

        if skill_path.is_dir():
            shutil.rmtree(skill_path)
        else:
            skill_path.unlink()

        return {"success": True, "name": skill_name, "uninstalled": True}
'''

SKILLS_EVOLUTION_PY = r'''"""Self-improving skill synthesis, execution telemetry, and autonomous optimization."""

from __future__ import annotations

import difflib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SkillRunRecord:
    """Telemetry entry for a single skill invocation."""

    skill_name: str
    success: bool
    latency_ms: float
    error_message: str = ""
    user_feedback_score: float | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass(slots=True)
class SkillHealthReport:
    """Aggregated health score and telemetry diagnostics for a skill."""

    skill_name: str
    total_runs: int
    success_rate: float
    avg_latency_ms: float
    error_count: int
    health_score: float  # 0.0 to 1.0
    needs_optimization: bool
    recent_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "total_runs": self.total_runs,
            "success_rate": self.success_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "error_count": self.error_count,
            "health_score": self.health_score,
            "needs_optimization": self.needs_optimization,
            "recent_errors": self.recent_errors,
        }


class SkillEvolutionEngine:
    """Tracks skill execution telemetry and autonomously proposes optimizations."""

    def __init__(self, failure_threshold: float = 0.25, min_runs_to_evaluate: int = 3) -> None:
        self.failure_threshold = failure_threshold
        self.min_runs_to_evaluate = min_runs_to_evaluate
        self._telemetry: dict[str, list[SkillRunRecord]] = {}

    def record_run(
        self,
        skill_name: str,
        success: bool,
        latency_ms: float,
        error_message: str = "",
        user_feedback_score: float | None = None,
    ) -> None:
        """Record execution outcome for a skill."""
        record = SkillRunRecord(
            skill_name=skill_name,
            success=success,
            latency_ms=latency_ms,
            error_message=error_message,
            user_feedback_score=user_feedback_score,
        )
        if skill_name not in self._telemetry:
            self._telemetry[skill_name] = []
        self._telemetry[skill_name].append(record)

    def evaluate_health(self, skill_name: str) -> SkillHealthReport:
        """Calculate health score and determine if self-improving evolution is required."""
        runs = self._telemetry.get(skill_name, [])
        if not runs:
            return SkillHealthReport(
                skill_name=skill_name,
                total_runs=0,
                success_rate=1.0,
                avg_latency_ms=0.0,
                error_count=0,
                health_score=1.0,
                needs_optimization=False,
            )

        total = len(runs)
        successes = sum(1 for r in runs if r.success)
        errors = [r.error_message for r in runs if not r.success and r.error_message]
        success_rate = successes / total
        avg_latency = sum(r.latency_ms for r in runs) / total

        # Composite score: success rate (80%) + latency factor (20%)
        latency_factor = max(0.0, min(1.0, 1.0 - (avg_latency / 5000.0)))
        health_score = (success_rate * 0.8) + (latency_factor * 0.2)

        needs_optimization = (
            total >= self.min_runs_to_evaluate
            and (1.0 - success_rate) >= self.failure_threshold
        )

        return SkillHealthReport(
            skill_name=skill_name,
            total_runs=total,
            success_rate=success_rate,
            avg_latency_ms=avg_latency,
            error_count=len(errors),
            health_score=health_score,
            needs_optimization=needs_optimization,
            recent_errors=errors[-5:],
        )

    def propose_optimization(
        self,
        skill_name: str,
        current_content: str,
        health: SkillHealthReport,
    ) -> dict[str, Any]:
        """Synthesize an optimized revision for a degraded skill."""
        lines = current_content.splitlines()
        updated_lines: list[str] = []

        # Version bumping logic: v1.0.0 -> v1.1.0
        version_bumped = False
        for line in lines:
            if line.startswith("version:") and not version_bumped:
                m = re.search(r"(\d+)\.(\d+)\.(\d+)", line)
                if m:
                    major, minor = int(m.group(1)), int(m.group(2))
                    new_ver = f"{major}.{minor + 1}.0"
                    updated_lines.append(f"version: {new_ver}")
                    version_bumped = True
                    continue
            updated_lines.append(line)

        # Inject guard steps based on error patterns
        if health.recent_errors:
            error_summary = "; ".join(set(health.recent_errors[:2]))
            guard_note = (
                f"\n## Self-Healing Guard (Auto-Evolved):\n"
                f"- Pre-check inputs to prevent: {error_summary}\n"
                f"- Ensure fallback validation before final step.\n"
            )
            updated_lines.append(guard_note)

        new_content = "\n".join(updated_lines).strip() + "\n"
        diff = list(
            difflib.unified_diff(
                current_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"{skill_name}.v_old",
                tofile=f"{skill_name}.v_evolved",
            )
        )

        return {
            "skill_name": skill_name,
            "original_content": current_content,
            "optimized_content": new_content,
            "diff": "".join(diff),
            "diagnostics": {
                "success_rate": health.success_rate,
                "error_count": health.error_count,
                "reason": "Autonomous recovery from runtime execution failures.",
            },
        }

    def apply_evolution(
        self,
        skill_path: Path | str,
        optimized_content: str,
        backup_dir: Path | str | None = None,
    ) -> dict[str, Any]:
        """Apply the optimized content and save rollback checkpoint."""
        p = Path(skill_path)
        if p.is_dir():
            target_file = p / "SKILL.md"
        else:
            target_file = p

        if not target_file.exists():
            return {"success": False, "error": f"File {target_file} does not exist."}

        # Backup previous version
        original = target_file.read_text(encoding="utf-8")
        b_dir = Path(backup_dir) if backup_dir else target_file.parent / ".backups"
        b_dir.mkdir(parents=True, exist_ok=True)
        backup_file = b_dir / f"{target_file.name}.bak_{int(time.time())}"
        backup_file.write_text(original, encoding="utf-8")

        # Write new version
        target_file.write_text(optimized_content, encoding="utf-8")

        return {
            "success": True,
            "file": str(target_file),
            "backup_file": str(backup_file),
            "timestamp": time.time(),
        }

    def rollback(
        self,
        skill_path: Path | str,
        backup_dir: Path | str | None = None,
    ) -> dict[str, Any]:
        """Restore most recent backup checkpoint."""
        p = Path(skill_path)
        target_file = (p / "SKILL.md") if p.is_dir() else p
        b_dir = Path(backup_dir) if backup_dir else target_file.parent / ".backups"

        if not b_dir.exists():
            return {"success": False, "error": f"No backups found in {b_dir}."}

        backups = sorted(b_dir.glob("*.bak_*"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not backups:
            return {"success": False, "error": "No backup checkpoints found."}

        latest_backup = backups[0]
        content = latest_backup.read_text(encoding="utf-8")
        target_file.write_text(content, encoding="utf-8")

        return {
            "success": True,
            "restored_from": str(latest_backup),
            "file": str(target_file),
        }
'''

SKILLS_BUNDLE_PY = r'''"""Skill package bundling, SHA-256 checksum integrity, export, and import."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class SkillBundleManager:
    """Manages exporting and importing standalone portable skill packages."""

    @staticmethod
    def export_bundle(skill_dir: Path | str, output_bundle_path: Path | str) -> dict[str, Any]:
        """Package a skill directory (SKILL.md + references) into a verified bundle."""
        s_dir = Path(skill_dir)
        if not s_dir.exists() or not s_dir.is_dir():
            return {"success": False, "error": f"Directory '{s_dir}' does not exist."}

        skill_md = s_dir / "SKILL.md"
        if not skill_md.exists():
            return {"success": False, "error": f"Missing SKILL.md in '{s_dir}'."}

        files_data: dict[str, str] = {
            "SKILL.md": skill_md.read_text(encoding="utf-8")
        }

        # Pack references
        ref_dir = s_dir / "references"
        if ref_dir.exists() and ref_dir.is_dir():
            for ref_file in ref_dir.glob("*"):
                if ref_file.is_file():
                    try:
                        files_data[f"references/{ref_file.name}"] = ref_file.read_text(
                            encoding="utf-8"
                        )
                    except Exception:
                        pass

        # Calculate payload checksum
        serialized_payload = json.dumps(files_data, sort_keys=True, ensure_ascii=False)
        sha256 = hashlib.sha256(serialized_payload.encode("utf-8")).hexdigest()

        bundle_payload = {
            "format": "dream_skill_bundle_v1",
            "skill_name": s_dir.name,
            "sha256": sha256,
            "files_count": len(files_data),
            "files": files_data,
        }

        out_path = Path(output_bundle_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload_str = json.dumps(bundle_payload, indent=2, ensure_ascii=False)
        out_path.write_text(payload_str, encoding="utf-8")

        return {
            "success": True,
            "bundle_path": str(out_path),
            "sha256": sha256,
            "files_count": len(files_data),
        }

    @staticmethod
    def import_bundle(bundle_path: Path | str, target_skills_dir: Path | str) -> dict[str, Any]:
        """Verify integrity and unpack skill bundle into the target directory."""
        b_path = Path(bundle_path)
        if not b_path.exists() or not b_path.is_file():
            return {"success": False, "error": f"Bundle file '{b_path}' not found."}

        try:
            data = json.loads(b_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"success": False, "error": f"Corrupted JSON in bundle: {exc}"}

        if data.get("format") != "dream_skill_bundle_v1":
            return {"success": False, "error": "Unrecognized bundle format."}

        skill_name = data.get("skill_name", "").strip()
        files = data.get("files", {})
        expected_sha = data.get("sha256", "")

        # Verify checksum
        serialized_payload = json.dumps(files, sort_keys=True, ensure_ascii=False)
        actual_sha = hashlib.sha256(serialized_payload.encode("utf-8")).hexdigest()
        if actual_sha != expected_sha:
            return {
                "success": False,
                "error": f"Checksum mismatch! Expected {expected_sha}, got {actual_sha}.",
            }

        target_base = Path(target_skills_dir)
        dest_dir = target_base / skill_name
        dest_dir.mkdir(parents=True, exist_ok=True)

        written_files = []
        for rel_path_str, content in files.items():
            # Security guard against path traversal
            if ".." in rel_path_str or rel_path_str.startswith(("/", "\\")):
                continue
            dest_file = dest_dir / rel_path_str
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            dest_file.write_text(content, encoding="utf-8")
            written_files.append(rel_path_str)

        return {
            "success": True,
            "skill_name": skill_name,
            "target_dir": str(dest_dir),
            "files": written_files,
        }
'''

SKILLS_HUB_TOOLS_PY = r'''"""Agent tool interfaces for Skills Hub, Autonomous Evolution, and Bundles."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dream.skills.bundle import SkillBundleManager
from dream.skills.evolution import SkillEvolutionEngine
from dream.skills.hub import SkillsHubCatalog

_GLOBAL_HUB: SkillsHubCatalog | None = None
_GLOBAL_EVOLUTION: SkillEvolutionEngine | None = None


def get_global_skills_hub() -> SkillsHubCatalog:
    """Get singleton skills hub catalog."""
    global _GLOBAL_HUB
    if _GLOBAL_HUB is None:
        _GLOBAL_HUB = SkillsHubCatalog()
    return _GLOBAL_HUB


def get_global_evolution_engine() -> SkillEvolutionEngine:
    """Get singleton skill evolution engine."""
    global _GLOBAL_EVOLUTION
    if _GLOBAL_EVOLUTION is None:
        _GLOBAL_EVOLUTION = SkillEvolutionEngine()
    return _GLOBAL_EVOLUTION


def hub_search_skills(query: str = "", tag: str = "") -> str:
    """Search community skills catalog by keyword or category tag.

    Args:
        query: Search term (e.g. 'tax', 'jalali', 'seo', 'coding').
        tag: Optional category filter.

    Returns:
        JSON string listing available community skills.
    """
    hub = get_global_skills_hub()
    tag_val = tag if tag.strip() else None
    results = hub.search(query=query, tag=tag_val)
    return json.dumps(
        {
            "status": "ok",
            "count": len(results),
            "skills": [s.to_dict() for s in results],
        },
        ensure_ascii=False,
        indent=2,
    )


def hub_install_skill(name: str, target_dir: str = "skills") -> str:
    """Install a vetted skill from the community Skills Hub into the workspace.

    Args:
        name: Name of the skill (e.g. 'iran-tax-calculator', 'jalali-cron-planner').
        target_dir: Destination skills directory.

    Returns:
        JSON string with installation status.
    """
    hub = get_global_skills_hub()
    result = hub.install(name, target_dir=target_dir)
    return json.dumps(result, ensure_ascii=False, indent=2)


def skill_evolve_optimize(skill_name: str, skill_path: str = "") -> str:
    """Autonomously analyze skill execution health and propose self-healing optimizations.

    Args:
        skill_name: Name of the skill to optimize.
        skill_path: Path to the skill file/directory.

    Returns:
        JSON string containing diagnostics, health score, and proposed diff.
    """
    engine = get_global_evolution_engine()
    health = engine.evaluate_health(skill_name)

    path = Path(skill_path) if skill_path else Path(f"skills/{skill_name}/SKILL.md")
    if not path.exists():
        path = Path(f"skills/{skill_name}.txt")

    if not path.exists():
        return json.dumps(
            {
                "status": "error",
                "message": f"Skill file for '{skill_name}' not found at {path}.",
                "health": {
                    "runs": health.total_runs,
                    "success_rate": health.success_rate,
                },
            },
            ensure_ascii=False,
        )

    content = path.read_text(encoding="utf-8")
    proposal = engine.propose_optimization(skill_name, content, health)
    return json.dumps(
        {
            "status": "ok",
            "health": health.to_dict(),
            "proposal": proposal,
        },
        indent=2,
    )


def skill_export_bundle(skill_dir: str, output_path: str) -> str:
    """Package a local skill into a portable bundle with SHA-256 integrity verification.

    Args:
        skill_dir: Path to the skill folder (e.g. 'skills/iran-tax-calculator').
        output_path: Destination bundle file (e.g. 'dist/iran-tax.skill.json').

    Returns:
        JSON string with bundling outcome and checksum.
    """
    res = SkillBundleManager.export_bundle(skill_dir, output_path)
    return json.dumps(res, ensure_ascii=False, indent=2)


def skill_import_bundle(bundle_path: str, target_dir: str = "skills") -> str:
    """Import and verify a skill bundle into the workspace.

    Args:
        bundle_path: Path to the .skill.json bundle file.
        target_dir: Target skills workspace folder.

    Returns:
        JSON string with unpack results.
    """
    res = SkillBundleManager.import_bundle(bundle_path, target_dir)
    return json.dumps(res, ensure_ascii=False, indent=2)


def get_hub_tools() -> dict[str, Callable[..., Any]]:
    """Return dict of skill hub and evolution tools."""
    return {
        "hub_search_skills": hub_search_skills,
        "hub_install_skill": hub_install_skill,
        "skill_evolve_optimize": skill_evolve_optimize,
        "skill_export_bundle": skill_export_bundle,
        "skill_import_bundle": skill_import_bundle,
    }
'''

SKILLS_HUB_SLASH_PY = r'''"""Slash command handlers for Skills Hub, Autonomous Evolution, and Bundles."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.skills.bundle import SkillBundleManager
from dream.skills.evolution import SkillEvolutionEngine
from dream.skills.hub import SkillsHubCatalog
from dream.skills.hub_tools import get_global_evolution_engine, get_global_skills_hub


def handle_hub_command(
    cmd_text: str,
    hub: SkillsHubCatalog | None = None,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/hub` slash command (search, install, list skills)."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors
    h = hub or get_global_skills_hub()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "list"

    if subcmd in ("list", "all"):
        skills = h.search()
        output(cm.bold(f"🌐 Dream Community Skills Hub ({len(skills)} Skills Available):"))
        for s in skills:
            output(f"  • {cm.green(s.name):<25} [v{s.version}] {cm.yellow('★ ' + str(s.rating))}")
            output(f"    {cm.dim(s.description)}")
        return True

    if subcmd in ("search", "find") and len(parts) > 2:
        query = " ".join(parts[2:])
        results = h.search(query=query)
        if not results:
            output(cm.yellow(f"No skills found matching '{query}'."))
            return True
        output(cm.bold(f"Search results for '{query}' ({len(results)} found):"))
        for s in results:
            output(f"  • {cm.green(s.name)} [v{s.version}]: {s.description}")
        return True

    if subcmd in ("install", "get") and len(parts) > 2:
        name = parts[2]
        res = h.install(name, target_dir="skills")
        if res.get("success"):
            v = res.get("version")
            output(cm.green(f"✓ Successfully installed '{name}' v{v} into skills/"))
        else:
            output(cm.red(f"✗ Installation failed: {res.get('error')}"))
        return True

    # Usage
    output(cm.bold("Usage / راهنمای دستور /hub:"))
    output("  /hub list             - فهرست کل مهارت‌های موجود / List all hub skills")
    output("  /hub search <query>   - جستجوی مهارت در هاب / Search skills")
    output("  /hub install <name>   - نصب مهارت روی دستیار / Install skill")
    return True


def handle_evolve_command(
    cmd_text: str,
    engine: SkillEvolutionEngine | None = None,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/evolve` slash command (inspect health and propose optimization)."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors
    eng = engine or get_global_evolution_engine()
    parts = cmd_text.strip().split()
    if len(parts) < 2:
        output(cm.yellow("Usage: /evolve <skill_name>"))
        return True

    skill_name = parts[1]
    health = eng.evaluate_health(skill_name)
    output(cm.bold(f"Autonomous Evolution Health: {skill_name}"))
    output(f"  • Total Runs:   {health.total_runs}")
    output(f"  • Success Rate: {health.success_rate * 100:.1f}%")
    output(f"  • Health Score: {health.health_score:.2f}")

    if health.needs_optimization:
        output(cm.yellow("⚠️ Skill is degraded. Generating self-healing optimization proposal..."))
    else:
        output(cm.green("✓ Skill health is optimal."))
    return True


def handle_bundle_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/bundle` slash command (export or import portable packages)."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "help"

    if subcmd == "export" and len(parts) > 2:
        skill_name = parts[2]
        out_path = f"dist/{skill_name}.skill.json"
        res = SkillBundleManager.export_bundle(f"skills/{skill_name}", out_path)
        if res.get("success"):
            output(cm.green(f"✓ Skill '{skill_name}' bundled to {out_path}"))
            output(cm.dim(f"  SHA256: {res.get('sha256')}"))
        else:
            output(cm.red(f"✗ Export failed: {res.get('error')}"))
        return True

    if subcmd == "import" and len(parts) > 2:
        b_path = parts[2]
        res = SkillBundleManager.import_bundle(b_path, target_skills_dir="skills")
        if res.get("success"):
            s_name = res.get("skill_name")
            t_dir = res.get("target_dir")
            output(cm.green(f"✓ Imported skill '{s_name}' into {t_dir}"))
        else:
            output(cm.red(f"✗ Import failed: {res.get('error')}"))
        return True

    output(cm.bold("Usage / راهنمای دستور /bundle:"))
    output("  /bundle export <skill_name> - ایجاد بسته خروجی / Export skill bundle")
    output("  /bundle import <path>       - نصب بسته مهارت / Import skill bundle")
    return True
'''

TOOLSETS_PY = r'''"""Toolset categorization, grouping, and dynamic tool management."""

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
        allowed_names.update(source.keys())

    if exclude_tools is not None:
        allowed_names.difference_update(exclude_tools)

    return {name: tool for name, tool in source.items() if name in allowed_names}
'''

TEST_SKILLS_SYSTEM = r'''"""Comprehensive test suite for Skills Hub, Autonomous Evolution, and Bundles."""

from __future__ import annotations

import json

from dream.skills.bundle import SkillBundleManager
from dream.skills.evolution import SkillEvolutionEngine
from dream.skills.hub import SkillsHubCatalog
from dream.skills.hub_slash import (
    handle_bundle_command,
    handle_evolve_command,
    handle_hub_command,
)
from dream.skills.hub_tools import (
    get_hub_tools,
    hub_install_skill,
    hub_search_skills,
    skill_evolve_optimize,
)
from dream.tools.toolsets import get_toolset


def test_skills_hub_catalog_search_and_filter():
    """Verify hub search, tag filtering, and metadata extraction."""
    hub = SkillsHubCatalog()

    # Search all
    all_skills = hub.search()
    assert len(all_skills) >= 5

    # Tag filter
    iran_skills = hub.search(tag="iran")
    assert len(iran_skills) >= 2
    assert any(s.name == "iran-tax-calculator" for s in iran_skills)

    # Keyword search
    seo_results = hub.search(query="سئو")
    assert len(seo_results) >= 1
    assert seo_results[0].name == "persian-content-seo"


def test_skills_hub_install_and_uninstall(tmp_path):
    """Verify installing a hub skill with SKILL.md and references, then uninstalling."""
    hub = SkillsHubCatalog()
    target = tmp_path / "skills"

    # Install
    res = hub.install("iran-tax-calculator", target_dir=target)
    assert res["success"] is True
    assert (target / "iran-tax-calculator" / "SKILL.md").exists()
    assert (target / "iran-tax-calculator" / "references" / "rules.md").exists()

    # Uninstall
    un_res = hub.uninstall("iran-tax-calculator", target_dir=target)
    assert un_res["success"] is True
    assert not (target / "iran-tax-calculator").exists()


def test_skill_evolution_telemetry_and_health_scoring():
    """Verify runtime telemetry recording, failure detection, and health score calculation."""
    engine = SkillEvolutionEngine(failure_threshold=0.25, min_runs_to_evaluate=3)

    # Healthy skill
    for _ in range(5):
        engine.record_run("math-helper", success=True, latency_ms=120.0)
    health_healthy = engine.evaluate_health("math-helper")
    assert health_healthy.total_runs == 5
    assert health_healthy.success_rate == 1.0
    assert health_healthy.health_score > 0.9
    assert health_healthy.needs_optimization is False

    # Degraded skill
    for _ in range(4):
        engine.record_run(
            "flaky-api",
            success=False,
            latency_ms=3000.0,
            error_message="HTTP Timeout 504",
        )
    health_degraded = engine.evaluate_health("flaky-api")
    assert health_degraded.total_runs == 4
    assert health_degraded.success_rate == 0.0
    assert health_degraded.needs_optimization is True
    assert "HTTP Timeout 504" in health_degraded.recent_errors


def test_skill_evolution_proposal_and_rollback(tmp_path):
    """Verify self-healing optimization proposals, version bumping, and backup rollbacks."""
    engine = SkillEvolutionEngine()
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"

    initial_content = (
        "---\n"
        "name: my-skill\n"
        "version: 1.0.0\n"
        "---\n\n"
        "# My Skill\n"
        "1. Step one\n"
    )
    skill_file.write_text(initial_content, encoding="utf-8")

    # Record errors to trigger degradation
    for _ in range(3):
        engine.record_run("my-skill", success=False, latency_ms=500.0, error_message="Null input")

    health = engine.evaluate_health("my-skill")
    proposal = engine.propose_optimization("my-skill", initial_content, health)
    assert "version: 1.1.0" in proposal["optimized_content"]
    assert "Self-Healing Guard" in proposal["optimized_content"]

    # Apply evolution
    apply_res = engine.apply_evolution(skill_file, proposal["optimized_content"])
    assert apply_res["success"] is True
    assert "version: 1.1.0" in skill_file.read_text(encoding="utf-8")

    # Rollback
    rollback_res = engine.rollback(skill_file)
    assert rollback_res["success"] is True
    assert "version: 1.0.0" in skill_file.read_text(encoding="utf-8")


def test_skill_bundle_export_and_import(tmp_path):
    """Verify portable bundle packaging with SHA-256 integrity verification."""
    skills_root = tmp_path / "src_skills"
    skill_dir = skills_root / "sample-skill"
    ref_dir = skill_dir / "references"
    ref_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text("# Sample Skill\n1. Do task", encoding="utf-8")
    (ref_dir / "data.txt").write_text("Reference content", encoding="utf-8")

    bundle_out = tmp_path / "bundles" / "sample.skill.json"

    # Export bundle
    export_res = SkillBundleManager.export_bundle(skill_dir, bundle_out)
    assert export_res["success"] is True
    assert bundle_out.exists()

    # Import bundle to fresh directory
    dest_skills = tmp_path / "dest_skills"
    import_res = SkillBundleManager.import_bundle(bundle_out, dest_skills)
    assert import_res["success"] is True
    assert (dest_skills / "sample-skill" / "SKILL.md").exists()
    assert (dest_skills / "sample-skill" / "references" / "data.txt").exists()


def test_skills_hub_tools_and_slash_commands(tmp_path):
    """Verify LLM tool calls and slash commands for Skills Hub."""
    # Tool: hub_search_skills
    search_json = hub_search_skills(query="tax")
    parsed_search = json.loads(search_json)
    assert parsed_search["status"] == "ok"
    assert parsed_search["count"] >= 1

    # Tool: hub_install_skill
    dest_dir = str(tmp_path / "installed_skills")
    install_json = hub_install_skill("jalali-cron-planner", target_dir=dest_dir)
    parsed_install = json.loads(install_json)
    assert parsed_install["success"] is True

    # Tool: skill_evolve_optimize
    evolve_json = skill_evolve_optimize(
        "jalali-cron-planner",
        skill_path=f"{dest_dir}/jalali-cron-planner/SKILL.md",
    )
    parsed_evolve = json.loads(evolve_json)
    assert parsed_evolve["status"] == "ok"

    # Tool dict registration
    hub_tools = get_hub_tools()
    assert "hub_search_skills" in hub_tools
    assert "hub_install_skill" in hub_tools
    assert "skill_evolve_optimize" in hub_tools

    # Slash commands
    out: list[str] = []
    handle_hub_command("/hub list", output=out.append)
    assert any("Dream Community Skills Hub" in line for line in out)

    out.clear()
    handle_evolve_command("/evolve math-helper", output=out.append)
    assert any("Autonomous Evolution Health" in line for line in out)

    out.clear()
    handle_bundle_command("/bundle help", output=out.append)
    assert any("Usage" in line for line in out)


def test_toolset_includes_all_skill_tools():
    """Verify toolset grouping contains all legacy and new hub tools."""
    skill_ts = get_toolset("skills")
    assert skill_ts is not None
    assert "hub_search_skills" in skill_ts.tools
    assert "hub_install_skill" in skill_ts.tools
    assert "skill_evolve_optimize" in skill_ts.tools
    assert "save_skill" in skill_ts.tools
'''


def apply_patch(repo_dir: Path) -> None:
    print(f"[*] Applying PR #19 (Skills Hub, Evolution & Bundle System) to: {repo_dir.resolve()}")

    files_to_write = {
        repo_dir / "dream" / "skills" / "hub.py": SKILLS_HUB_PY,
        repo_dir / "dream" / "skills" / "evolution.py": SKILLS_EVOLUTION_PY,
        repo_dir / "dream" / "skills" / "bundle.py": SKILLS_BUNDLE_PY,
        repo_dir / "dream" / "skills" / "hub_tools.py": SKILLS_HUB_TOOLS_PY,
        repo_dir / "dream" / "skills" / "hub_slash.py": SKILLS_HUB_SLASH_PY,
        repo_dir / "dream" / "tools" / "toolsets.py": TOOLSETS_PY,
        repo_dir / "tests" / "test_skills_hub_and_evolution.py": TEST_SKILLS_SYSTEM,
    }

    for path, content in files_to_write.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")
        print(f"  [+] Wrote: {path.relative_to(repo_dir)}")

    print("\n[✓] PR #19 successfully applied!")
    print("Next steps:")
    print("  1. Run tests: pytest -v tests/test_skills_hub_and_evolution.py")
    print("  2. Run linter: ruff check dream/skills tests/test_skills_hub_and_evolution.py")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    apply_patch(target)
