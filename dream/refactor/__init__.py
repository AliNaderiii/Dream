"""Multimodal Code Intelligence, AST Refactoring & Deterministic Patch Subsystem."""

from __future__ import annotations

from dream.refactor.engine import RefactorEngine
from dream.refactor.patcher import DeterministicPatcher
from dream.refactor.slash import handle_refactor_slash_command
from dream.refactor.symbol_index import ASTSymbolIndexer
from dream.refactor.tools import (
    get_global_refactor_engine,
    get_refactor_tools,
    refactor_apply_patch,
    refactor_find_symbol,
    refactor_generate_patch,
    refactor_get_status,
    refactor_index_symbols,
    refactor_reset,
    refactor_rollback_patch,
    reset_global_refactor_engine,
)
from dream.refactor.types import (
    CodeSymbol,
    PatchChange,
    PatchStatus,
    RefactorPlan,
    RefactorReport,
    SymbolType,
)

__all__ = [
    "ASTSymbolIndexer",
    "CodeSymbol",
    "DeterministicPatcher",
    "PatchChange",
    "PatchStatus",
    "RefactorEngine",
    "RefactorReport",
    "RefactorPlan",
    "SymbolType",
    "get_global_refactor_engine",
    "get_refactor_tools",
    "handle_refactor_slash_command",
    "refactor_apply_patch",
    "refactor_find_symbol",
    "refactor_generate_patch",
    "refactor_get_status",
    "refactor_index_symbols",
    "refactor_reset",
    "refactor_rollback_patch",
    "reset_global_refactor_engine",
]
