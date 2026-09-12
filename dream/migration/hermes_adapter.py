"""Hermes Agent Workspace migration adapter."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dream.migration.sanitizer import MigrationSanitizer
from dream.migration.types import MigratedItem, MigrationItemType

logger = logging.getLogger(__name__)


class HermesMigrationAdapter:
    """Discovers and parses Hermes Agent workspaces, memory files, and skills."""

    CORE_CONTEXT_FILES = {
        "SOUL.md": MigrationItemType.SOUL,
        "USER.md": MigrationItemType.USER_PROFILE,
        "MEMORY.md": MigrationItemType.MEMORY_NOTE,
        "AGENTS.md": MigrationItemType.CONFIG,
    }

    def __init__(self, sanitizer: MigrationSanitizer | None = None) -> None:
        self.sanitizer = sanitizer or MigrationSanitizer()

    def inspect_workspace(self, root_dir: str | Path) -> list[MigratedItem]:
        """Scan directory structure and extract all Hermes agent artifacts."""
        path = Path(root_dir)
        if not path.exists() or not path.is_dir():
            return []

        items: list[MigratedItem] = []

        # 1. Discover 4 Core Context Files
        for fname, itype in self.CORE_CONTEXT_FILES.items():
            fpath = path / fname
            if fpath.exists() and fpath.is_file():
                try:
                    raw_content = fpath.read_text(encoding="utf-8", errors="replace")
                    norm_content, changes = self.sanitizer.normalize_persian_text(raw_content)
                    items.append(
                        MigratedItem(
                            item_id=f"hermes_{fname.lower().replace('.', '_')}",
                            item_type=itype,
                            title=f"Hermes {fname}",
                            content=norm_content,
                            source_path=str(fpath),
                            target_destination=f"context/{fname}",
                            metadata={
                                "original_filename": fname,
                                "persian_normalizations": changes,
                            },
                            is_persian_normalized=changes > 0,
                        )
                    )
                except Exception as exc:
                    logger.warning(f"Could not read Hermes context file {fpath}: {exc}")

        # 2. Discover Skills in skills/ or .hermes/skills/
        skills_dirs = [path / "skills", path / ".hermes" / "skills"]
        for sdir in skills_dirs:
            if sdir.exists() and sdir.is_dir():
                items.extend(self._discover_skills(sdir))

        # 3. Discover Config / Provider settings
        config_files = [path / "config.json", path / "hermes.json", path / ".env"]
        for cfile in config_files:
            if cfile.exists() and cfile.is_file():
                cfg_item = self._parse_config_file(cfile)
                if cfg_item:
                    items.append(cfg_item)

        return items

    def _discover_skills(self, skills_dir: Path) -> list[MigratedItem]:
        """Walk skills subdirectories to find SKILL.md and scripts."""
        skills: list[MigratedItem] = []
        for skill_folder in skills_dir.iterdir():
            if not skill_folder.is_dir():
                continue

            skill_file = skill_folder / "SKILL.md"
            if skill_file.exists():
                try:
                    content = skill_file.read_text(encoding="utf-8", errors="replace")
                    norm_content, changes = self.sanitizer.normalize_persian_text(content)
                    skill_name = skill_folder.name
                    skills.append(
                        MigratedItem(
                            item_id=f"skill_{skill_name}",
                            item_type=MigrationItemType.SKILL,
                            title=f"Skill: {skill_name}",
                            content=norm_content,
                            source_path=str(skill_file),
                            target_destination=f"skills/{skill_name}/SKILL.md",
                            metadata={
                                "skill_name": skill_name,
                                "folder": str(skill_folder),
                            },
                            is_persian_normalized=changes > 0,
                        )
                    )
                except Exception as exc:
                    logger.warning(f"Failed to read skill {skill_file}: {exc}")

        return skills

    def _parse_config_file(self, config_file: Path) -> MigratedItem | None:
        """Extract configuration parameters and model selections."""
        try:
            content = config_file.read_text(encoding="utf-8", errors="replace")
            meta: dict[str, Any] = {}
            if config_file.suffix.lower() == ".json":
                try:
                    meta = json.loads(content)
                except Exception:
                    meta = {"raw_content": content}
            else:
                # Simple .env key-value parsing
                for line in content.splitlines():
                    if "=" in line and not line.strip().startswith("#"):
                        k, v = line.split("=", 1)
                        meta[k.strip()] = v.strip()

            return MigratedItem(
                item_id=f"cfg_{config_file.stem}",
                item_type=MigrationItemType.CONFIG,
                title=f"Configuration: {config_file.name}",
                content=content,
                source_path=str(config_file),
                target_destination=f"config/{config_file.name}",
                metadata=meta,
                is_persian_normalized=False,
            )
        except Exception as exc:
            logger.warning(f"Failed to parse config {config_file}: {exc}")
            return None
