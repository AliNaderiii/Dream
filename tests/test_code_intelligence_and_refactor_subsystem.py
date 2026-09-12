"""Unit and integration tests for Code Intelligence & AST Refactor Subsystem."""

from __future__ import annotations

import pytest

from dream.refactor import (
    ASTSymbolIndexer,
    DeterministicPatcher,
    PatchStatus,
    RefactorEngine,
    SymbolType,
    get_refactor_tools,
    handle_refactor_slash_command,
    refactor_apply_patch,
    refactor_find_symbol,
    refactor_generate_patch,
    refactor_get_status,
    refactor_index_symbols,
    refactor_reset,
    refactor_rollback_patch,
    reset_global_refactor_engine,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


@pytest.fixture(autouse=True)
def cleanup_refactor_engine() -> None:
    reset_global_refactor_engine()
    yield
    reset_global_refactor_engine()


def test_toolset_includes_refactor() -> None:
    """Verify refactor toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("refactor")
    assert ts is not None
    assert "refactor_index_symbols" in ts.tools
    assert "refactor_find_symbol" in ts.tools
    assert "refactor_generate_patch" in ts.tools
    assert "refactor_apply_patch" in ts.tools
    assert "refactor" in BUILTIN_TOOLSETS


def test_ast_symbol_indexer() -> None:
    """Verify AST parsing and extraction of functions, classes, and methods."""
    code = """
import os
from typing import Any

class PaymentProcessor:
    \"\"\"Processes customer payments securely.\"\"\"
    def process_transaction(self, amount: int) -> bool:
        return amount > 0

async def fetch_user_data(user_id: str) -> dict:
    return {"id": user_id}
"""
    indexer = ASTSymbolIndexer()
    symbols = indexer.index_source_code("test_payments.py", code)

    assert len(symbols) >= 4

    # Check class
    classes = [s for s in symbols if s.symbol_type == SymbolType.CLASS]
    assert len(classes) == 1
    assert classes[0].name == "PaymentProcessor"
    assert "Processes customer" in classes[0].docstring

    # Check method
    methods = [s for s in symbols if s.symbol_type == SymbolType.METHOD]
    assert len(methods) == 1
    assert methods[0].name == "PaymentProcessor.process_transaction"

    # Check async function
    async_funcs = [s for s in symbols if s.symbol_type == SymbolType.ASYNC_FUNCTION]
    assert len(async_funcs) == 1
    assert async_funcs[0].name == "fetch_user_data"

    # Check query
    found = indexer.find_symbol("PaymentProcessor")
    assert len(found) >= 1
    assert found[0].name == "PaymentProcessor"


def test_deterministic_patcher_and_ast_validation(tmp_path) -> None:
    """Verify unified diff generation, AST syntax validation, and atomic writes."""
    patcher = DeterministicPatcher()

    old_code = "def hello():\n    return 'world'\n"
    new_valid = "def hello():\n    return 'iran'\n"
    new_invalid = "def hello():\n    return 'invalid syntax (missing quote)\n"

    test_file = tmp_path / "mod.py"
    test_file.write_text(old_code, encoding="utf-8")

    # 1. Valid patch
    patch_v = patcher.create_patch(str(test_file), old_code, new_valid)
    assert patch_v.ast_valid is True
    assert "+    return 'iran'" in patch_v.diff_unified

    # Apply valid patch
    patcher.apply_patch(patch_v, backup=True)
    assert test_file.read_text(encoding="utf-8") == new_valid
    assert (tmp_path / "mod.py.bak").exists()

    # Rollback
    patcher.rollback_patch(patch_v)
    assert test_file.read_text(encoding="utf-8") == old_code

    # 2. Invalid syntax patch
    patch_inv = patcher.create_patch(str(test_file), old_code, new_invalid)
    assert patch_inv.ast_valid is False
    assert patch_inv.syntax_error is not None

    with pytest.raises(ValueError, match="Syntax Error"):
        patcher.apply_patch(patch_inv)


def test_refactor_engine_plan_lifecycle(tmp_path) -> None:
    """Verify plan construction, diff markdown generation, and atomic multi-file application."""
    engine = RefactorEngine()

    file_a = tmp_path / "a.py"
    file_b = tmp_path / "b.py"
    file_a.write_text("x = 10\n", encoding="utf-8")
    file_b.write_text("y = 20\n", encoding="utf-8")

    modifications = [
        {"file_path": str(file_a), "new_content": "x = 100\n"},
        {"file_path": str(file_b), "new_content": "y = 200\n"},
    ]

    plan = engine.create_refactor_plan(
        goal_fa="افزایش ضرایب محاسباتی",
        file_modifications=modifications,
    )
    assert plan.status == PatchStatus.VALIDATED
    assert len(plan.changes) == 2

    # Check Markdown
    md = engine.format_plan_markdown(plan.plan_id)
    assert "افزایش ضرایب محاسباتی" in md
    assert "معتبر (AST Valid)" in md

    # Apply
    rep = engine.apply_plan(plan.plan_id)
    assert rep.status == PatchStatus.APPLIED
    assert file_a.read_text(encoding="utf-8") == "x = 100\n"
    assert file_b.read_text(encoding="utf-8") == "y = 200\n"

    # Rollback
    engine.rollback_plan(plan.plan_id)
    assert file_a.read_text(encoding="utf-8") == "x = 10\n"
    assert file_b.read_text(encoding="utf-8") == "y = 20\n"


def test_refactor_tools_and_slash_commands(tmp_path) -> None:
    """Verify LLM agent tools and /refactor slash command handlers."""
    tools = get_refactor_tools()
    assert len(tools) >= 5

    test_file = tmp_path / "sample.py"
    test_file.write_text("def my_func(a, b):\n    return a + b\n", encoding="utf-8")

    # Tool: index
    res_idx = refactor_index_symbols(str(tmp_path))
    assert res_idx["success"] is True
    assert res_idx["total_symbols_indexed"] >= 1

    # Tool: find
    res_find = refactor_find_symbol("my_func")
    assert res_find["success"] is True
    assert res_find["total_matches"] >= 1

    # Tool: generate patch
    res_gen = refactor_generate_patch(
        goal_fa="بهینه‌سازی تابع",
        file_modifications=[{
            "file_path": str(test_file),
            "new_content": "def my_func(a, b):\n    return (a + b) * 2\n",
        }],
    )
    assert res_gen["success"] is True
    plan_id = res_gen["plan_id"]

    # Tool: apply patch
    res_app = refactor_apply_patch(plan_id)
    assert res_app["success"] is True

    # Tool: rollback
    res_rb = refactor_rollback_patch(plan_id)
    assert res_rb["success"] is True

    # Tool: status & reset
    res_st = refactor_get_status()
    assert res_st["success"] is True
    assert res_st["total_plans"] >= 1

    res_res = refactor_reset()
    assert res_res["success"] is True

    # Slash: /refactor
    slash_help = handle_refactor_slash_command("/refactor")
    assert "راهنمای دستورات هوشمندی کد" in slash_help

    # Slash: /refactor index
    slash_idx = handle_refactor_slash_command(f"/refactor index {tmp_path}")
    assert "نماد کدی" in slash_idx

    # Slash: /refactor find
    slash_f = handle_refactor_slash_command("/refactor find my_func")
    assert "نتایج جستجوی نماد" in slash_f

    # Slash: /refactor status
    slash_s = handle_refactor_slash_command("/refactor status")
    assert "وضعیت سیستم بازآرایی کد" in slash_s

    # Slash: /refactor reset
    slash_r = handle_refactor_slash_command("/refactor reset")
    assert "بازنشانی شد" in slash_r
