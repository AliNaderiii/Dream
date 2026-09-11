"""Master Context Engine assembling prioritized tiers into structured agent system prompt."""

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
