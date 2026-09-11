"""Loader and file persistence for multi-tier context files."""

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
