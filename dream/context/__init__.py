"""Layered Context Hierarchy subsystem (SOUL.md, AGENTS.md, USER.md, MEMORY.md)."""

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
