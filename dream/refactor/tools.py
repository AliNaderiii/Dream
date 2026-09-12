"""LLM agent tools and singleton managers for Code Intelligence & AST Refactor."""

from __future__ import annotations

import logging
from typing import Any

from dream.refactor.engine import RefactorEngine

logger = logging.getLogger(__name__)

_GLOBAL_REFACTOR_ENGINE: RefactorEngine | None = None


def get_global_refactor_engine() -> RefactorEngine:
    """Retrieve or initialize singleton RefactorEngine."""
    global _GLOBAL_REFACTOR_ENGINE
    if _GLOBAL_REFACTOR_ENGINE is None:
        _GLOBAL_REFACTOR_ENGINE = RefactorEngine()
    return _GLOBAL_REFACTOR_ENGINE


def reset_global_refactor_engine() -> None:
    """Reset global RefactorEngine instance for test isolation."""
    global _GLOBAL_REFACTOR_ENGINE
    if _GLOBAL_REFACTOR_ENGINE is not None:
        _GLOBAL_REFACTOR_ENGINE.reset()
    _GLOBAL_REFACTOR_ENGINE = None


def refactor_index_symbols(directory_path: str = ".") -> dict[str, Any]:
    """Scan and build an AST structural symbol index for Python source files in a directory.

    Args:
        directory_path: Root folder path to index.
    """
    engine = get_global_refactor_engine()
    try:
        count = engine.index_directory(directory_path)
        return {
            "success": True,
            "directory": directory_path,
            "total_symbols_indexed": count,
            "summary_fa": f"تعداد {count} نماد کدی (تابع، کلاس، متد) با موفقیت ایندکس شد.",
        }
    except Exception as exc:
        logger.error(f"Error indexing symbols: {exc}")
        return {"success": False, "error": str(exc)}


def refactor_find_symbol(query: str) -> dict[str, Any]:
    """Search for functions, classes, and methods across the codebase by name.

    Args:
        query: Function or class name to search for.
    """
    engine = get_global_refactor_engine()
    matches = engine.find_symbols(query)
    return {
        "success": True,
        "query": query,
        "total_matches": len(matches),
        "symbols": [s.to_dict() for s in matches],
    }


def refactor_generate_patch(
    goal_fa: str,
    file_modifications: list[dict[str, str]],
) -> dict[str, Any]:
    """Construct a refactoring plan with AST syntax validation and unified diff previews.

    Args:
        goal_fa: Persian explanation of the refactoring purpose.
        file_modifications: List of dicts with 'file_path', optional 'old_content',
            and 'new_content'.
    """
    engine = get_global_refactor_engine()
    try:
        plan = engine.create_refactor_plan(goal_fa, file_modifications)
        diff_md = engine.format_plan_markdown(plan.plan_id)
        return {
            "success": True,
            "plan_id": plan.plan_id,
            "status": plan.status.value,
            "plan": plan.to_dict(),
            "preview_markdown": diff_md,
        }
    except Exception as exc:
        logger.error(f"Error generating patch: {exc}")
        return {"success": False, "error": str(exc)}


def refactor_apply_patch(plan_id: str) -> dict[str, Any]:
    """Apply an AST-verified refactoring plan to disk with automatic backup.

    Args:
        plan_id: Identifier of the refactor plan to execute.
    """
    engine = get_global_refactor_engine()
    try:
        rep = engine.apply_plan(plan_id)
        return {
            "success": rep.syntax_valid,
            "report": rep.to_dict(),
            "summary_fa": rep.summary_fa,
        }
    except Exception as exc:
        logger.error(f"Error applying patch {plan_id}: {exc}")
        return {"success": False, "error": str(exc)}


def refactor_rollback_patch(plan_id: str) -> dict[str, Any]:
    """Rollback applied code modifications for a given refactor plan.

    Args:
        plan_id: Identifier of the plan to revert.
    """
    engine = get_global_refactor_engine()
    try:
        ok = engine.rollback_plan(plan_id)
        return {
            "success": ok,
            "plan_id": plan_id,
            "message_fa": f"طرح بازآرایی `{plan_id}` با موفقیت لغو و بازگردانی شد.",
        }
    except Exception as exc:
        logger.error(f"Error rolling back patch: {exc}")
        return {"success": False, "error": str(exc)}


def refactor_get_status() -> dict[str, Any]:
    """Retrieve operational telemetry and history from RefactorEngine."""
    engine = get_global_refactor_engine()
    return {"success": True, **engine.get_status()}


def refactor_reset() -> dict[str, Any]:
    """Reset indexed symbols, plans, and telemetry."""
    reset_global_refactor_engine()
    return {"success": True, "message_fa": "موتور بازآرایی کد با موفقیت بازنشانی شد."}


def get_refactor_tools() -> list[dict[str, Any]]:
    """Return tool manifests for LLM registration."""
    return [
        {
            "name": "refactor_index_symbols",
            "description": "Index Python functions, classes, and AST symbols across a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory_path": {"type": "string", "default": "."},
                },
            },
            "handler": refactor_index_symbols,
        },
        {
            "name": "refactor_find_symbol",
            "description": "Find AST code symbols (classes, functions, methods) by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
            "handler": refactor_find_symbol,
        },
        {
            "name": "refactor_generate_patch",
            "description": (
                "Generate an AST-verified refactoring plan with unified diffs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_fa": {"type": "string"},
                    "file_modifications": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
                "required": ["goal_fa", "file_modifications"],
            },
            "handler": refactor_generate_patch,
        },
        {
            "name": "refactor_apply_patch",
            "description": "Apply a validated refactoring plan to disk with automatic backup.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string"},
                },
                "required": ["plan_id"],
            },
            "handler": refactor_apply_patch,
        },
        {
            "name": "refactor_rollback_patch",
            "description": "Rollback an applied refactoring plan to original code state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string"},
                },
                "required": ["plan_id"],
            },
            "handler": refactor_rollback_patch,
        },
    ]
