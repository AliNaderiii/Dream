"""Central community Skills Hub: discovery, installation, and lifecycle management."""

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
