"""OpenClaw Agent framework migration adapter."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dream.migration.sanitizer import MigrationSanitizer
from dream.migration.types import MigratedItem, MigrationItemType

logger = logging.getLogger(__name__)


class OpenClawMigrationAdapter:
    """Discovers and parses OpenClaw workspaces, memory dumps, and plugin configs."""

    def __init__(self, sanitizer: MigrationSanitizer | None = None) -> None:
        self.sanitizer = sanitizer or MigrationSanitizer()

    def inspect_workspace(self, root_dir: str | Path) -> list[MigratedItem]:
        """Inspect directory for OpenClaw manifest, memories, and plugins."""
        path = Path(root_dir)
        if not path.exists() or not path.is_dir():
            return []

        items: list[MigratedItem] = []

        # 1. OpenClaw manifest (claw.json or openclaw.json)
        manifest_files = [path / "claw.json", path / "openclaw.json", path / "agent.json"]
        for mfile in manifest_files:
            if mfile.exists() and mfile.is_file():
                try:
                    content = mfile.read_text(encoding="utf-8", errors="replace")
                    data = json.loads(content)
                    items.append(
                        MigratedItem(
                            item_id="openclaw_manifest",
                            item_type=MigrationItemType.CONFIG,
                            title="OpenClaw Agent Manifest",
                            content=content,
                            source_path=str(mfile),
                            target_destination="config/openclaw_manifest.json",
                            metadata=data,
                            is_persian_normalized=False,
                        )
                    )

                    # Extract persona as SOUL if specified
                    if "persona" in data:
                        persona_text = str(data["persona"])
                        norm_p, c = self.sanitizer.normalize_persian_text(persona_text)
                        items.append(
                            MigratedItem(
                                item_id="openclaw_soul",
                                item_type=MigrationItemType.SOUL,
                                title="OpenClaw Persona Soul",
                                content=norm_p,
                                source_path=str(mfile),
                                target_destination="context/SOUL.md",
                                metadata={"extracted_from": mfile.name},
                                is_persian_normalized=c > 0,
                            )
                        )
                except Exception as exc:
                    logger.warning(f"Failed to read OpenClaw manifest {mfile}: {exc}")

        # 2. Memories dump (memory_store.json or memories.json)
        memory_files = [path / "memory_store.json", path / "memories.json"]
        for mem_file in memory_files:
            if mem_file.exists() and mem_file.is_file():
                items.extend(self._parse_memories_file(mem_file))

        # 3. Custom Plugins / Tools
        plugins_dir = path / "plugins"
        if plugins_dir.exists() and plugins_dir.is_dir():
            for pfile in plugins_dir.glob("*.py"):
                try:
                    content = pfile.read_text(encoding="utf-8", errors="replace")
                    items.append(
                        MigratedItem(
                            item_id=f"openclaw_plugin_{pfile.stem}",
                            item_type=MigrationItemType.SKILL,
                            title=f"Plugin: {pfile.name}",
                            content=content,
                            source_path=str(pfile),
                            target_destination=f"skills/{pfile.stem}/plugin.py",
                            metadata={"entrypoint": pfile.name},
                            is_persian_normalized=False,
                        )
                    )
                except Exception as exc:
                    logger.warning(f"Failed to read plugin {pfile}: {exc}")

        return items

    def _parse_memories_file(self, mem_file: Path) -> list[MigratedItem]:
        """Extract individual memory entries from JSON memory store."""
        items: list[MigratedItem] = []
        try:
            content = mem_file.read_text(encoding="utf-8", errors="replace")
            data = json.loads(content)
            entries: list[dict[str, Any]] = []

            if isinstance(data, list):
                entries = data
            elif isinstance(data, dict) and "memories" in data:
                entries = data["memories"]

            for i, entry in enumerate(entries):
                text = entry.get("content") or entry.get("text") or str(entry)
                norm_text, count = self.sanitizer.normalize_persian_text(text)
                items.append(
                    MigratedItem(
                        item_id=f"openclaw_mem_{i+1}",
                        item_type=MigrationItemType.MEMORY_NOTE,
                        title=f"Memory #{i+1}",
                        content=norm_text,
                        source_path=str(mem_file),
                        target_destination=f"memory/openclaw_entry_{i+1}.md",
                        metadata=entry if isinstance(entry, dict) else {},
                        is_persian_normalized=count > 0,
                    )
                )
        except Exception as exc:
            logger.warning(f"Failed to parse OpenClaw memories {mem_file}: {exc}")

        return items
