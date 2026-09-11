#!/usr/bin/env python3
"""apply_pr23.py - Standalone installer for Phase 20 / PR #23:
Layered Context Hierarchy Engine (SOUL.md, AGENTS.md, USER.md, MEMORY.md) & Adaptive Token Budgeting.

This installer creates or updates the following files in the target repository:
  - dream/context/__init__.py
  - dream/context/types.py
  - dream/context/loader.py
  - dream/context/budget.py
  - dream/context/engine.py
  - dream/context/tools.py
  - dream/context/slash.py
  - dream/tools/toolsets.py
  - tests/test_context_hierarchy.py
"""

from __future__ import annotations

import sys
from pathlib import Path

CONTEXT_TYPES_PY = r'''"""Data types and tier models for Layered Context Hierarchy subsystem."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ContextTier(str, Enum):
    """Context hierarchy tiers in decreasing order of priority."""

    SOUL = "soul"
    AGENTS = "agents"
    USER = "user"
    MEMORY = "memory"


@dataclass(slots=True)
class ContextFile:
    """Represents an individual tracked context markdown file."""

    tier: ContextTier
    filename: str
    path: Path
    content: str = ""
    mtime: float = 0.0
    checksum: str = ""
    default_char_budget: int = 2000
    allocated_char_budget: int = 2000
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize context file metadata to dictionary."""
        return {
            "tier": self.tier.value if isinstance(self.tier, ContextTier) else self.tier,
            "filename": self.filename,
            "path": str(self.path),
            "char_length": len(self.content),
            "checksum": self.checksum,
            "default_char_budget": self.default_char_budget,
            "allocated_char_budget": self.allocated_char_budget,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class ContextAssembly:
    """Assembled prompt context combining all prioritized tiers within token budget."""

    rendered_text: str
    tier_lengths: dict[str, int] = field(default_factory=dict)
    total_chars: int = 0
    estimated_tokens: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize assembly output to dictionary."""
        return {
            "rendered_text": self.rendered_text,
            "tier_lengths": self.tier_lengths,
            "total_chars": self.total_chars,
            "estimated_tokens": self.estimated_tokens,
            "timestamp": self.timestamp,
        }
'''

CONTEXT_LOADER_PY = r'''"""Loader and file persistence for multi-tier context files."""

from __future__ import annotations

import hashlib
import time
import unicodedata
from pathlib import Path

from dream.context.types import ContextFile, ContextTier

DEFAULT_CONTEXT_DIR = Path.home() / ".dream" / "context"

TIER_FILENAMES = {
    ContextTier.SOUL: "SOUL.md",
    ContextTier.AGENTS: "AGENTS.md",
    ContextTier.USER: "USER.md",
    ContextTier.MEMORY: "MEMORY.md",
}

DEFAULT_TIER_BUDGETS = {
    ContextTier.SOUL: 1500,
    ContextTier.AGENTS: 2000,
    ContextTier.USER: 1500,
    ContextTier.MEMORY: 3000,
}

DEFAULT_TIER_CONTENTS = {
    ContextTier.SOUL: (
        "# SOUL.md - Dream Agent Core Identity\n\n"
        "\u062f\u0633\u062a\u06cc\u0627\u0631 "
        "\u0647\u0648\u0634\u0645\u0646\u062f "
        "\u062f\u0648\u0632\u0628\u0627\u0646\u0647 "
        "\u062f\u0631\u06cc\u0645 (Dream)\u061b "
        "\u062f\u0642\u06cc\u0642\u060c "
        "\u0635\u0627\u062f\u0642\u060c "
        "\u062d\u0631\u0641\u0647\u200c\u0627\u06cc "
        "\u0648 \u0628\u0627 "
        "\u0627\u0633\u062a\u0627\u0646\u062f\u0627\u0631\u062f\u0647\u0627\u06cc "
        "\u0627\u0645\u0646\u06cc\u062a\u06cc \u0628\u0627\u0644\u0627.\n"
    ),
    ContextTier.AGENTS: (
        "# AGENTS.md - Swarm & Subagent Capabilities\n\n"
        "- Coordinator: Workflow orchestration and task DAG decomposition.\n"
        "- Architect: Technical design and specification.\n"
        "- Coder: Production-grade implementation.\n"
        "- Critic: Security audit, validation, and review.\n"
    ),
    ContextTier.USER: (
        "# USER.md - User Preferences & Profile\n\n"
        "- Preferred Language: Persian (fa) / English (en)\n"
        "- Code Style: Clean, modular, type-annotated, tested\n"
    ),
    ContextTier.MEMORY: (
        "# MEMORY.md - Curated Long-Term Facts\n\n"
        "- Project: Dream Agent Development & Scaling\n"
        "- Target: State-of-the-art autonomous assistant\n"
    ),
}


class ContextLoader:
    """Manages reading, caching, and writing of hierarchical markdown context files."""

    def __init__(self, root_dir: Path | str | None = None) -> None:
        self.root_dir = Path(root_dir) if root_dir else DEFAULT_CONTEXT_DIR
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[ContextTier, ContextFile] = {}
        self._initialize_defaults()

    def _normalize_text(self, text: str) -> str:
        """Apply Unicode NFKC normalization and clean excessive blank lines."""
        norm = unicodedata.normalize("NFKC", text.strip())
        return norm

    def _compute_checksum(self, text: str) -> str:
        """Compute SHA-256 hash of text content."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _get_file_path(self, tier: ContextTier) -> Path:
        """Get file path for context tier."""
        fname = TIER_FILENAMES.get(tier, f"{tier.value.upper()}.md")
        return self.root_dir / fname

    def _initialize_defaults(self) -> None:
        """Ensure all 4 default context files exist on disk."""
        for tier in ContextTier:
            p = self._get_file_path(tier)
            if not p.exists():
                default_content = DEFAULT_TIER_CONTENTS.get(tier, f"# {tier.value.upper()}\n")
                p.write_text(default_content, encoding="utf-8")

    def load_tier(self, tier: ContextTier, force_reload: bool = False) -> ContextFile:
        """Load single tier content from disk with mtime/checksum caching."""
        p = self._get_file_path(tier)
        if not p.exists():
            self._initialize_defaults()

        current_mtime = p.stat().st_mtime if p.exists() else 0.0

        if not force_reload and tier in self._cache:
            cached = self._cache[tier]
            if cached.mtime == current_mtime:
                return cached

        content = p.read_text(encoding="utf-8") if p.exists() else ""
        norm_content = self._normalize_text(content)
        checksum = self._compute_checksum(norm_content)
        budget = DEFAULT_TIER_BUDGETS.get(tier, 2000)

        cfile = ContextFile(
            tier=tier,
            filename=p.name,
            path=p,
            content=norm_content,
            mtime=current_mtime,
            checksum=checksum,
            default_char_budget=budget,
            allocated_char_budget=budget,
            updated_at=time.time(),
        )
        self._cache[tier] = cfile
        return cfile

    def save_tier(self, tier: ContextTier, content: str) -> bool:
        """Write updated content to disk and update cache."""
        p = self._get_file_path(tier)
        norm_content = self._normalize_text(content)
        try:
            p.write_text(norm_content, encoding="utf-8")
            current_mtime = p.stat().st_mtime
            checksum = self._compute_checksum(norm_content)
            budget = DEFAULT_TIER_BUDGETS.get(tier, 2000)

            self._cache[tier] = ContextFile(
                tier=tier,
                filename=p.name,
                path=p,
                content=norm_content,
                mtime=current_mtime,
                checksum=checksum,
                default_char_budget=budget,
                allocated_char_budget=budget,
                updated_at=time.time(),
            )
            return True
        except Exception:
            return False

    def load_all(self, force_reload: bool = False) -> dict[ContextTier, ContextFile]:
        """Load and return all 4 context tiers."""
        result = {}
        for tier in ContextTier:
            result[tier] = self.load_tier(tier, force_reload=force_reload)
        return result
'''

CONTEXT_BUDGET_PY = r'''"""Dynamic token and character budget allocation with priority waterfall overflow."""

from __future__ import annotations

from typing import Any

from dream.context.types import ContextFile, ContextTier

TIER_PRIORITY_ORDER = [
    ContextTier.SOUL,
    ContextTier.AGENTS,
    ContextTier.USER,
    ContextTier.MEMORY,
]


class TokenBudgetManager:
    """Manages adaptive token allocation and waterfall overflow across context tiers."""

    def __init__(self, total_max_chars: int = 8000) -> None:
        self.total_max_chars = total_max_chars

    def allocate_budgets(
        self,
        files: dict[ContextTier, ContextFile],
    ) -> dict[ContextTier, int]:
        """Compute waterfall budget allocation so surplus budget flows to lower tiers."""
        allocated: dict[ContextTier, int] = {}
        surplus = 0

        for tier in TIER_PRIORITY_ORDER:
            cfile = files.get(tier)
            base_budget = cfile.default_char_budget if cfile else 2000
            current_len = len(cfile.content) if cfile else 0

            target_budget = base_budget + surplus
            if current_len < target_budget:
                surplus = target_budget - current_len
                allocated[tier] = current_len
            else:
                allocated[tier] = target_budget
                surplus = 0

        # Update files with allocated budgets
        for tier, budget in allocated.items():
            if tier in files:
                files[tier].allocated_char_budget = budget

        return allocated

    def fit_content(self, cfile: ContextFile) -> str:
        """Truncate content cleanly if it exceeds the allocated character budget."""
        budget = cfile.allocated_char_budget
        content = cfile.content

        if len(content) <= budget:
            return content

        notice = "\n\n[... Truncated to fit context budget ...]"
        effective_limit = max(100, budget - len(notice))
        return content[:effective_limit] + notice

    def get_budget_report(
        self,
        files: dict[ContextTier, ContextFile],
    ) -> dict[str, Any]:
        """Generate a breakdown of context file sizes vs allocated budgets."""
        self.allocate_budgets(files)
        report: dict[str, Any] = {
            "total_max_chars": self.total_max_chars,
            "tiers": {},
        }

        total_used = 0
        for tier in TIER_PRIORITY_ORDER:
            cf = files.get(tier)
            if cf:
                used = len(self.fit_content(cf))
                total_used += used
                report["tiers"][tier.value] = {
                    "file": cf.filename,
                    "actual_length": len(cf.content),
                    "allocated_budget": cf.allocated_char_budget,
                    "rendered_length": used,
                }

        report["total_rendered_chars"] = total_used
        report["estimated_tokens"] = round(total_used / 4)
        return report
'''

CONTEXT_ENGINE_PY = r'''"""Master Context Engine assembling prioritized tiers into structured agent system prompt."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from dream.context.budget import TIER_PRIORITY_ORDER, TokenBudgetManager
from dream.context.loader import ContextLoader
from dream.context.types import ContextAssembly, ContextFile, ContextTier


class ContextEngine:
    """Orchestrates multi-tier context loading, token budgeting, and prompt assembly."""

    def __init__(
        self,
        root_dir: Path | str | None = None,
        total_max_chars: int = 8000,
    ) -> None:
        self.loader = ContextLoader(root_dir=root_dir)
        self.budget_manager = TokenBudgetManager(total_max_chars=total_max_chars)

    def assemble_context(self, force_reload: bool = False) -> ContextAssembly:
        """Assemble all 4 context tiers into a coherent system prompt section."""
        files = self.loader.load_all(force_reload=force_reload)
        self.budget_manager.allocate_budgets(files)

        rendered_sections = []
        tier_lengths = {}
        total_chars = 0

        for tier in TIER_PRIORITY_ORDER:
            cfile = files.get(tier)
            if cfile and cfile.content:
                fitted_text = self.budget_manager.fit_content(cfile)
                fn = cfile.filename
                section = (
                    f"<!-- BEGIN CONTEXT TIER: {fn} -->\n"
                    f"{fitted_text}\n"
                    f"<!-- END CONTEXT TIER: {fn} -->"
                )
                rendered_sections.append(section)
                tier_lengths[tier.value] = len(fitted_text)
                total_chars += len(fitted_text)

        full_prompt_context = "\n\n".join(rendered_sections)
        estimated_tokens = round(total_chars / 4)

        return ContextAssembly(
            rendered_text=full_prompt_context,
            tier_lengths=tier_lengths,
            total_chars=total_chars,
            estimated_tokens=estimated_tokens,
            timestamp=time.time(),
        )

    def get_tier(self, tier_name: str | ContextTier) -> ContextFile:
        """Retrieve a specific context tier file."""
        if isinstance(tier_name, str):
            try:
                tier = ContextTier(tier_name.lower())
            except Exception:
                tier = ContextTier.SOUL
        else:
            tier = tier_name
        return self.loader.load_tier(tier)

    def update_tier(self, tier_name: str | ContextTier, content: str) -> bool:
        """Update a specific context tier file content."""
        if isinstance(tier_name, str):
            try:
                tier = ContextTier(tier_name.lower())
            except Exception:
                tier = ContextTier.SOUL
        else:
            tier = tier_name
        return self.loader.save_tier(tier, content)

    def reload_all(self) -> dict[str, Any]:
        """Force reload all context files from disk."""
        files = self.loader.load_all(force_reload=True)
        return {
            tier.value: {
                "file": cf.filename,
                "length": len(cf.content),
                "checksum": cf.checksum,
            }
            for tier, cf in files.items()
        }

    def get_budget_report(self) -> dict[str, Any]:
        """Generate real-time token and character budget breakdown."""
        files = self.loader.load_all()
        return self.budget_manager.get_budget_report(files)
'''

CONTEXT_TOOLS_PY = r'''"""LLM Tool bindings for Layered Context Hierarchy manipulation."""

from __future__ import annotations

from typing import Any

from dream.context.engine import ContextEngine

_GLOBAL_CONTEXT_ENGINE: ContextEngine | None = None


def get_global_context_engine() -> ContextEngine:
    """Get or create singleton ContextEngine."""
    global _GLOBAL_CONTEXT_ENGINE
    if _GLOBAL_CONTEXT_ENGINE is None:
        _GLOBAL_CONTEXT_ENGINE = ContextEngine()
    return _GLOBAL_CONTEXT_ENGINE


def reset_global_context_engine() -> None:
    """Reset singleton for tests."""
    global _GLOBAL_CONTEXT_ENGINE
    _GLOBAL_CONTEXT_ENGINE = None


def context_get_tier(tier: str = "soul") -> dict[str, Any]:
    """Retrieve content and metadata of a specific context tier (soul, agents, user, memory)."""
    engine = get_global_context_engine()
    cf = engine.get_tier(tier)
    return cf.to_dict()


def context_update_tier(tier: str, content: str) -> dict[str, Any]:
    """Update content of a specific context tier file (soul, agents, user, memory)."""
    engine = get_global_context_engine()
    success = engine.update_tier(tier, content)
    cf = engine.get_tier(tier)
    data = cf.to_dict()
    data["success"] = success
    return data


def context_get_budget_report() -> dict[str, Any]:
    """Retrieve current character/token allocation breakdown across all context tiers."""
    engine = get_global_context_engine()
    return engine.get_budget_report()


def context_assemble_prompt() -> dict[str, Any]:
    """Assemble all 4 context tiers into a prioritized system prompt context block."""
    engine = get_global_context_engine()
    assembly = engine.assemble_context()
    return assembly.to_dict()


def context_reload_all() -> dict[str, Any]:
    """Force reload all context files from disk and refresh in-memory cache."""
    engine = get_global_context_engine()
    return engine.reload_all()


def get_context_tools() -> list[Any]:
    """Return list of context hierarchy tool functions for agent binding."""
    return [
        context_get_tier,
        context_update_tier,
        context_get_budget_report,
        context_assemble_prompt,
        context_reload_all,
    ]
'''

CONTEXT_SLASH_PY = r'''"""Interactive slash command handler for Layered Context Hierarchy management."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.context.tools import get_global_context_engine


def handle_context_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/context` slash command in interactive REPL or TUI."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors

    engine = get_global_context_engine()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "status"

    if subcmd in ("status", "list", "ls"):
        report = engine.get_budget_report()
        title = (
            "\U0001f4c4 "
            "\u0648\u0636\u0639\u06cc\u062a "
            "\u0641\u0627\u06cc\u0644\u200c\u0647\u0627\u06cc "
            "\u0632\u0645\u06cc\u0646\u0647 (Context Hierarchy):"
        )
        output(cm.bold(title))
        for _tier_name, info in report["tiers"].items():
            fname = info["file"]
            act_len = info["actual_length"]
            alloc = info["allocated_budget"]
            vol_lbl = "\u062d\u062c\u0645"
            char_lbl = "\u06a9\u0627\u0631\u0627\u06a9\u062a\u0631"
            bud_lbl = "\u0628\u0648\u062f\u062c\u0647"
            output(
                f"  \u2022 {cm.cyan(fname):<14} "
                f"({vol_lbl}: {act_len} {char_lbl} / {bud_lbl}: {alloc})"
            )
        total_chars = report["total_rendered_chars"]
        est_tokens = report["estimated_tokens"]
        tot_lbl = "\u0645\u062c\u0645\u0648\u0639 \u062a\u0648\u06a9\u0646\u200c\u0647\u0627"
        output(f"  \u2022 {tot_lbl}: {cm.green(str(est_tokens))} ({total_chars} chars)")
        return True

    if subcmd in ("view", "show", "cat"):
        target_tier = parts[2].lower() if len(parts) > 2 else "soul"
        cfile = engine.get_tier(target_tier)
        hdr = (
            f"\U0001f4c4 "
            f"\u0645\u062d\u062a\u0648\u0627\u06cc "
            f"{cfile.filename} "
            f"({len(cfile.content)} \u06a9\u0627\u0631\u0627\u06a9\u062a\u0631):"
        )
        output(cm.bold(hdr))
        output(cm.dim("-" * 50))
        output(cfile.content)
        output(cm.dim("-" * 50))
        return True

    if subcmd in ("update", "edit", "set"):
        if len(parts) < 4:
            err = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0646\u0627\u0645 "
                "\u0644\u0627\u06cc\u0647 (soul/agents/user/memory) "
                "\u0648 \u0645\u062a\u0646 \u062c\u062f\u06cc\u062f "
                "\u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(err))
            return True

        target_tier = parts[2].lower()
        new_content = " ".join(parts[3:])
        if engine.update_tier(target_tier, new_content):
            succ = (
                f"\u2713 \u0641\u0627\u06cc\u0644 "
                f"'{target_tier.upper()}.md' "
                "\u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a "
                "\u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc "
                "\u0634\u062f."
            )
            output(cm.green(succ))
        else:
            err_up = (
                "\u2717 \u062e\u0637\u0627 "
                "\u062f\u0631 \u0630\u062e\u06cc\u0631\u0647\u0633\u0627\u0632\u06cc."
            )
            output(cm.red(err_up))
        return True

    if subcmd in ("reload", "refresh"):
        res = engine.reload_all()
        succ_re = (
            f"\u2713 {len(res)} "
            "\u0641\u0627\u06cc\u0644 \u0632\u0645\u06cc\u0646\u0647 "
            "\u0645\u062c\u062f\u062f\u0627\u064b \u0627\u0632 "
            "\u062f\u06cc\u0633\u06a9 \u0628\u0627\u0631\u06af\u0630\u0627\u0631\u06cc "
            "\u0634\u062f\u0646\u062f."
        )
        output(cm.green(succ_re))
        return True

    # Help
    help_title = (
        "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
        "\u062f\u0633\u062a\u0648\u0631 /context:"
    )
    output(cm.bold(help_title))
    output(
        "  /context status                     - "
        "\u0646\u0645\u0627\u06cc\u0634 \u0648\u0636\u0639\u06cc\u062a \u0648 "
        "\u0628\u0648\u062f\u062c\u0647 \u062a\u0648\u06a9\u0646\u200c\u0647\u0627 / Context status"
    )
    output(
        "  /context view <tier>                - "
        "\u0645\u0634\u0627\u0647\u062f\u0647 \u0645\u062d\u062a\u0648\u0627 / View tier content"
    )
    output(
        "  /context update <tier> <text>       - "
        "\u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc / Update context file"
    )
    output(
        "  /context reload                     - "
        "\u0628\u0627\u0631\u06af\u0630\u0627\u0631\u06cc \u0645\u062c\u062f\u062f / Reload cache"
    )
    return True
'''

CONTEXT_INIT_PY = r'''"""Layered Context Hierarchy subsystem (SOUL.md, AGENTS.md, USER.md, MEMORY.md)."""

from __future__ import annotations

from dream.context.budget import TokenBudgetManager
from dream.context.engine import ContextEngine
from dream.context.loader import ContextLoader
from dream.context.slash import handle_context_command
from dream.context.tools import (
    context_assemble_prompt,
    context_get_budget_report,
    context_get_tier,
    context_reload_all,
    context_update_tier,
    get_context_tools,
    get_global_context_engine,
    reset_global_context_engine,
)
from dream.context.types import ContextAssembly, ContextFile, ContextTier

__all__ = [
    "ContextAssembly",
    "ContextEngine",
    "ContextFile",
    "ContextLoader",
    "ContextTier",
    "TokenBudgetManager",
    "context_assemble_prompt",
    "context_get_budget_report",
    "context_get_tier",
    "context_reload_all",
    "context_update_tier",
    "get_context_tools",
    "get_global_context_engine",
    "handle_context_command",
    "reset_global_context_engine",
]

try:
    from dream.tools import toolsets

    if hasattr(toolsets, "register_toolset") and "context" not in toolsets.BUILTIN_TOOLSETS:
        toolsets.register_toolset(
            "context",
            [
                "context_get_tier",
                "context_update_tier",
                "context_get_budget_report",
                "context_assemble_prompt",
                "context_reload_all",
            ],
            display_name="Context Hierarchy",
            description="Prioritized context files (SOUL, AGENTS, USER, MEMORY) and budgeting",
        )
except Exception:
    pass
'''

TESTS_CONTEXT_PY = r'''"""Tests for Layered Context Hierarchy subsystem (SOUL, AGENTS, USER, MEMORY)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from dream.context import (
    ContextEngine,
    ContextLoader,
    ContextTier,
    TokenBudgetManager,
    context_assemble_prompt,
    context_get_budget_report,
    context_get_tier,
    context_reload_all,
    context_update_tier,
    get_context_tools,
    handle_context_command,
    reset_global_context_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


def test_context_loader_defaults():
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ContextLoader(root_dir=tmpdir)
        files = loader.load_all()

        assert len(files) == 4
        assert ContextTier.SOUL in files
        assert ContextTier.AGENTS in files
        assert ContextTier.USER in files
        assert ContextTier.MEMORY in files

        soul_file = files[ContextTier.SOUL]
        assert "SOUL.md" in soul_file.filename
        assert len(soul_file.content) > 20
        assert (Path(tmpdir) / "SOUL.md").exists()


def test_context_loader_update_and_caching():
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ContextLoader(root_dir=tmpdir)

        # Update USER.md
        success = loader.save_tier(ContextTier.USER, "# USER Preferences\nTheme: Dark")
        assert success is True

        # Load back
        user_file = loader.load_tier(ContextTier.USER)
        assert "Theme: Dark" in user_file.content

        # Direct file check
        disk_content = (Path(tmpdir) / "USER.md").read_text(encoding="utf-8")
        assert "Theme: Dark" in disk_content


def test_waterfall_token_budget_allocation():
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ContextLoader(root_dir=tmpdir)
        files = loader.load_all()

        budget_mgr = TokenBudgetManager(total_max_chars=8000)
        allocated = budget_mgr.allocate_budgets(files)

        assert len(allocated) == 4
        report = budget_mgr.get_budget_report(files)

        assert report["total_max_chars"] == 8000
        assert "soul" in report["tiers"]
        assert "memory" in report["tiers"]
        assert report["estimated_tokens"] > 0


def test_context_engine_assembly():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ContextEngine(root_dir=tmpdir)
        assembly = engine.assemble_context()

        assert "BEGIN CONTEXT TIER: SOUL.md" in assembly.rendered_text
        assert "BEGIN CONTEXT TIER: AGENTS.md" in assembly.rendered_text
        assert "BEGIN CONTEXT TIER: USER.md" in assembly.rendered_text
        assert "BEGIN CONTEXT TIER: MEMORY.md" in assembly.rendered_text

        assert assembly.total_chars > 50
        assert assembly.estimated_tokens > 10
        assert len(assembly.tier_lengths) == 4


def test_context_tools_and_slash():
    reset_global_context_engine()
    tools = get_context_tools()
    assert len(tools) == 5

    soul_data = context_get_tier("soul")
    assert soul_data["tier"] == "soul"

    up_res = context_update_tier("user", "# Custom Preferences")
    assert up_res["success"] is True

    budget_data = context_get_budget_report()
    assert "tiers" in budget_data

    prompt_data = context_assemble_prompt()
    assert "BEGIN CONTEXT TIER: SOUL.md" in prompt_data["rendered_text"]

    reloaded = context_reload_all()
    assert "soul" in reloaded

    # Slash command tests
    lines = []
    handle_context_command("/context status", output=lines.append)
    assert any("SOUL.md" in line for line in lines)

    lines.clear()
    handle_context_command("/context view soul", output=lines.append)
    assert any("SOUL.md" in line for line in lines)

    lines.clear()
    handle_context_command("/context reload", output=lines.append)
    assert any("4" in line for line in lines)

    reset_global_context_engine()


def test_toolset_includes_context():
    assert "context" in BUILTIN_TOOLSETS
    toolset = get_toolset("context")
    assert toolset is not None
    assert len(toolset.tools) >= 5
    assert "context_get_tier" in toolset.tools
    assert "context_assemble_prompt" in toolset.tools
'''


def main() -> None:
    repo_dir = Path(__file__).resolve().parent / "dream-repo"
    if not repo_dir.exists():
        repo_dir = Path.cwd()

    print(f"Applying Phase 20 (PR #23) changes to repo at: {repo_dir}")

    context_dir = repo_dir / "dream" / "context"
    context_dir.mkdir(parents=True, exist_ok=True)

    (context_dir / "__init__.py").write_text(CONTEXT_INIT_PY, encoding="utf-8")
    print("  ✓ Created dream/context/__init__.py")

    (context_dir / "types.py").write_text(CONTEXT_TYPES_PY, encoding="utf-8")
    print("  ✓ Created dream/context/types.py")

    (context_dir / "loader.py").write_text(CONTEXT_LOADER_PY, encoding="utf-8")
    print("  ✓ Created dream/context/loader.py")

    (context_dir / "budget.py").write_text(CONTEXT_BUDGET_PY, encoding="utf-8")
    print("  ✓ Created dream/context/budget.py")

    (context_dir / "engine.py").write_text(CONTEXT_ENGINE_PY, encoding="utf-8")
    print("  ✓ Created dream/context/engine.py")

    (context_dir / "tools.py").write_text(CONTEXT_TOOLS_PY, encoding="utf-8")
    print("  ✓ Created dream/context/tools.py")

    (context_dir / "slash.py").write_text(CONTEXT_SLASH_PY, encoding="utf-8")
    print("  ✓ Created dream/context/slash.py")

    # Update dream/tools/toolsets.py
    toolsets_py = repo_dir / "dream" / "tools" / "toolsets.py"
    if toolsets_py.exists():
        content = toolsets_py.read_text(encoding="utf-8")
        if '"context":' not in content:
            new_entry = (
                '    "context": Toolset(\n'
                '        name="context",\n'
                '        description="Prioritized context files (SOUL, AGENTS, USER, MEMORY) and budgeting",\n'
                '        tools=(\n'
                '            "context_get_tier",\n'
                '            "context_update_tier",\n'
                '            "context_get_budget_report",\n'
                '            "context_assemble_prompt",\n'
                '            "context_reload_all",\n'
                '        ),\n'
                '    ),\n'
            )
            content = content.replace(
                '    "swarm": Toolset(',
                new_entry + '    "swarm": Toolset(',
            )
            toolsets_py.write_text(content, encoding="utf-8")
            print("  ✓ Updated dream/tools/toolsets.py with 'context' toolset")

    tests_dir = repo_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_context_hierarchy.py").write_text(TESTS_CONTEXT_PY, encoding="utf-8")
    print("  ✓ Created tests/test_context_hierarchy.py")

    print("\nPhase 20 (PR #23) application complete! Run pytest to verify:")
    print("  pytest tests/test_context_hierarchy.py")


if __name__ == "__main__":
    main()
