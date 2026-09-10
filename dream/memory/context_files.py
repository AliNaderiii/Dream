"""Tier-4 Persistent Context Files Engine (SOUL.md, USER.md, MEMORY.md, AGENTS.md)."""

from __future__ import annotations

import time
from pathlib import Path

from dream.memory.models import CapacityReport, ContextFile
from dream.memory.normalization import normalize_fa

SOUL_CAPACITY_CHARS = 2_200
USER_CAPACITY_CHARS = 1_375
MEMORY_CAPACITY_CHARS = 2_200
AGENTS_CAPACITY_CHARS = 2_500

DEFAULT_CAPACITIES: dict[str, int] = {
    "soul": SOUL_CAPACITY_CHARS,
    "user": USER_CAPACITY_CHARS,
    "memory": MEMORY_CAPACITY_CHARS,
    "agents": AGENTS_CAPACITY_CHARS,
}

DEFAULT_TEMPLATES: dict[str, str] = {
    "soul": """# SOUL: Persona & Principles
- **Name:** Dream
- **Role:** Autonomous, extremely intelligent AI assistant.
- **Principles:**
  - Truthful, precise, and helpful.
  - Native Persian language excellence (NFKC normalisation, Persian digits, RTL aware).
  - Fail-closed security with safe tool invocation.
""",
    "user": """# USER: Profile & Preferences
- **Language:** Persian (fa) preferred, bilingual English technical terms accepted.
- **Style:** Concise, direct, well-structured, production-grade code.
- **Goals:** Building state-of-the-art AI systems with high reliability.
""",
    "memory": """# MEMORY: Long-Term Curated Facts
- Autonomous multi-provider orchestration enabled.
- Hierarchical multi-subagent delegation enabled.
- Context compression with Jalali calendar preservation active.
""",
    "agents": """# AGENTS: Workspace Protocols
- Validate dependencies and syntax before execution.
- Maintain atomic state changes and 100% test coverage.
- Report resource bounds and respect concurrency budgets.
""",
}


class ContextCapacityError(ValueError):
    """Raised when a context file mutation exceeds its character budget."""


class ContextFileManager:
    """Manages the 4-tier persistent Markdown context files with live capacity metering."""

    def __init__(
        self,
        root_dir: str | Path | None = None,
        *,
        capacities: dict[str, int] | None = None,
        auto_create: bool = True,
    ) -> None:
        self.root_dir = Path(root_dir) if root_dir else Path.cwd()
        self.capacities = dict(DEFAULT_CAPACITIES if capacities is None else capacities)
        self.auto_create = auto_create
        self._files: dict[str, ContextFile] = {}
        self.load_all()

    def _file_path(self, name: str) -> Path:
        canonical_name = f"{name.upper()}.md"
        return self.root_dir / canonical_name

    def load_all(self) -> CapacityReport:
        """Load or bootstrap all 4 context files from disk."""
        for key, limit in self.capacities.items():
            path = self._file_path(key)
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8")
                except OSError:
                    content = DEFAULT_TEMPLATES.get(key, "")
            elif self.auto_create:
                content = DEFAULT_TEMPLATES.get(key, "")
                try:
                    self.root_dir.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")
                except OSError:
                    pass
            else:
                content = ""

            self._files[key] = ContextFile(
                name=key,
                capacity_limit=limit,
                content=content,
                last_updated=time.time(),
            )

        return CapacityReport(files=dict(self._files))

    def get(self, name: str) -> ContextFile | None:
        key = name.lower().replace(".md", "")
        return self._files.get(key)

    def update(
        self,
        name: str,
        new_content: str,
        *,
        enforce_capacity: bool = True,
    ) -> ContextFile:
        """Update a context file in memory and atomically on disk."""
        key = name.lower().replace(".md", "")
        if key not in self.capacities:
            raise KeyError(f"Unknown context file target: {name}")

        limit = self.capacities[key]
        normalized = new_content.strip()

        if enforce_capacity and len(normalized) > limit:
            raise ContextCapacityError(
                f"ظرفیت فایل {key.upper()}.md تکمیل است: {len(normalized):,}/{limit:,} کاراکتر."
            )

        context_file = ContextFile(
            name=key,
            capacity_limit=limit,
            content=normalized,
            last_updated=time.time(),
        )
        self._files[key] = context_file

        # Atomic write to disk
        path = self._file_path(key)
        try:
            self.root_dir.mkdir(parents=True, exist_ok=True)
            temp_path = path.with_suffix(".tmp")
            temp_path.write_text(normalized, encoding="utf-8")
            temp_path.replace(path)
        except OSError:
            pass

        return context_file

    def append_fact(self, name: str, fact_line: str) -> ContextFile:
        """Append a single bullet point fact to a context file."""
        cf = self.get(name)
        current = cf.content if cf else ""
        clean_fact = fact_line.strip()
        if not clean_fact.startswith("- "):
            clean_fact = f"- {clean_fact}"

        new_content = f"{current}\n{clean_fact}" if current else clean_fact
        return self.update(name, new_content)

    def compact(self, name: str) -> ContextFile:
        """Compact a context file by eliminating duplicate or low-priority lines."""
        cf = self.get(name)
        if not cf:
            raise KeyError(f"Unknown target: {name}")

        lines = cf.content.splitlines()
        seen: set[str] = set()
        preserved: list[str] = []

        for line in lines:
            norm = normalize_fa(line)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            preserved.append(line)

        compacted = "\n".join(preserved)
        return self.update(name, compacted, enforce_capacity=False)

    def render_prompt_block(self) -> str:
        """Render the complete Tier-4 Context block with live capacity meters."""
        report = CapacityReport(files=dict(self._files))
        headers = report.format_summary()

        sections = [
            "# PERSISTENT CONTEXT & MEMORY TIERS",
            headers,
            "",
        ]

        tag_order = [
            ("soul", "soul"),
            ("user", "user_profile"),
            ("memory", "curated_memory"),
            ("agents", "agent_rules"),
        ]

        for key, xml_tag in tag_order:
            cf = self._files.get(key)
            if cf and cf.content:
                sections.append(f"<{xml_tag}>\n{cf.content.strip()}\n</{xml_tag}>\n")

        return "\n".join(sections)
