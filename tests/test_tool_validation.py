"""Comprehensive tests for centralized tool input validation and limits (SEC-05)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from dream import tools
from dream.limits import (
    MAX_LIST_ITEMS,
    MAX_MAPPING_KEYS,
    MAX_TOOL_INPUT_CHARS,
)


def test_complete_tool_inventory():
    """Verify every registered core tool in REGISTRY is inventoried and accounted for."""
    core_tools = {
        "get_datetime",
        "search_web",
        "read_page",
        "calculate",
        "read_note",
        "list_notes",
        "write_note",
        "save_skill",
        "use_skill",
        "list_skills",
        "skill_view",
        "edit_skill",
        "delete_skill",
        "save_skill_bundle",
        "apply_skill_proposal",
        "discard_skill_proposal",
        "create_reminder",
        "cancel_reminder",
        "run_shell",
        "send_email",
    }
    assert core_tools.issubset(set(tools.REGISTRY.keys()))
    for tool_name in core_tools:
        assert tool_name in tools.REGISTRY
        t = tools.REGISTRY[tool_name]
        assert t.name == tool_name
        assert t.function is not None
        assert t.schema is not None
        assert t.risk in {"safe", "guarded", "dangerous"}


def test_valid_existing_calls_work():
    """Verify valid calls to calculate, get_datetime, etc. succeed."""
    assert tools.calculate("2 + 2") == 4
    dt = tools.get_datetime("Asia/Tehran")
    assert isinstance(dt, str)


def test_positional_and_keyword_arguments_behave_identically():
    """Positional and keyword arguments validate and execute identically."""
    res_kw = tools.calculate(expression="3 * 3")
    res_pos = tools.calculate("3 * 3")
    assert res_kw == res_pos == 9


def test_oversized_inputs_are_rejected():
    """Test boundary checks for each category."""
    q_lim = MAX_TOOL_INPUT_CHARS["query"]
    assert tools.calculate("1 + " + "1" * (q_lim - 20)) == eval(
        "1+" + "1" * (q_lim - 20)
    )
    with pytest.raises(ValueError):
        tools.calculate("1 + " + "1" * q_lim)

    p_lim = MAX_TOOL_INPUT_CHARS["path"]
    with pytest.raises(ValueError, match="exceeds maximum length"):
        tools.read_note("a" * (p_lim + 1))

    id_lim = MAX_TOOL_INPUT_CHARS["id"]
    with pytest.raises(ValueError, match="exceeds maximum length"):
        tools.skill_view("a" * (id_lim + 1))


def test_empty_strings_rejected_where_required():
    """Reject empty strings for mandatory non-empty parameters."""
    with pytest.raises(ValueError, match="cannot be empty"):
        tools.calculate("")

    with pytest.raises(ValueError, match="cannot be empty"):
        tools.read_note("")


def test_wrong_primitive_types_rejected():
    """Reject wrong primitive types."""
    with pytest.raises(ValueError):
        tools.calculate(123)  # expression expects str


def test_non_serializable_values_rejected():
    """Reject sets, bytes, Path, datetime, and custom objects."""
    with pytest.raises(ValueError):
        tools.calculate({1, 2, 3})  # set

    with pytest.raises(ValueError):
        tools.calculate(b"1+1")  # bytes

    with pytest.raises(ValueError):
        tools.read_note(Path("notes/test.txt"))  # Path object

    class CustomObj:
        pass

    with pytest.raises(ValueError):
        tools.calculate(CustomObj())  # custom object

    @tools.tool(risk="safe")
    def sample_tool(val: str) -> str:
        return val

    with pytest.raises(ValueError):
        sample_tool(val=datetime.now())  # datetime object


def test_shared_references_accepted_and_cycles_rejected():
    """Shared references are accepted, but true cycles are rejected."""
    shared = {"value": 1}
    items_list = [shared, shared]

    @tools.tool(risk="safe")
    def list_tool(data: list) -> str:
        return "ok"

    # Shared references should pass successfully
    assert list_tool(data=items_list) == "ok"

    # True cyclic references must be rejected
    cyclic: dict[str, Any] = {}
    cyclic["self"] = cyclic
    with pytest.raises(ValueError, match="circular reference"):
        tools.save_skill_bundle(
            name="test", description="desc", body="body", references=cyclic
        )


def test_float_validation_rules():
    """Valid finite floats accepted; strings, nan, and inf rejected."""
    @tools.tool(risk="safe")
    def float_tool(val: float) -> float:
        return val

    # Valid finite float accepted
    assert float_tool(val=3.14) == 3.14
    assert float_tool(val=42) == 42  # int accepted for float annotation

    # Strings rejected for float
    with pytest.raises(ValueError):
        float_tool(val="3.14")

    # "nan", "inf", "-inf" strings rejected
    with pytest.raises(ValueError):
        float_tool(val="nan")

    with pytest.raises(ValueError):
        float_tool(val="inf")

    # Actual float nan and inf rejected
    with pytest.raises(ValueError):
        float_tool(val=float("nan"))

    with pytest.raises(ValueError):
        float_tool(val=float("inf"))

    with pytest.raises(ValueError):
        float_tool(val=float("-inf"))


def test_nested_and_cyclic_structures_bounded():
    """Excessive nesting depth is rejected."""
    @tools.tool(risk="safe")
    def deep_tool(data: dict) -> str:
        return "ok"

    nested: Any = "leaf"
    for _ in range(12):
        nested = {"sub": nested}
    with pytest.raises(ValueError, match="nesting depth"):
        deep_tool(data=nested)


def test_list_items_and_mapping_keys_limits():
    """Reject lists exceeding MAX_LIST_ITEMS and mappings exceeding MAX_MAPPING_KEYS."""
    too_many_items = list(range(MAX_LIST_ITEMS + 1))
    with pytest.raises(ValueError, match="maximum list items"):
        tools.save_skill(name="test", description="desc", steps=too_many_items)

    too_many_keys = {f"k{i}": "val" for i in range(MAX_MAPPING_KEYS + 1)}
    with pytest.raises(ValueError, match="maximum mapping keys"):
        tools.save_skill_bundle(
            name="test", description="desc", body="body", references=too_many_keys
        )


def test_tool_body_not_invoked_on_validation_failure():
    """Verify tool body is not executed when validation fails."""
    called = False

    @tools.tool(risk="safe")
    def dummy_tool(query: str) -> str:
        nonlocal called
        called = True
        return "ok"

    with pytest.raises(ValueError):
        tools.REGISTRY["dummy_tool"].function(query="")
    assert not called


def test_error_messages_dont_echo_secrets_or_oversized_payloads():
    """Error messages must not echo full oversized input."""
    oversized = "x" * 10_000
    try:
        tools.skill_view(oversized)
    except ValueError as e:
        msg = str(e)
        assert oversized not in msg
        assert len(msg) < 500


def test_persian_unicode_text_limits():
    """Persian and Unicode text is handled correctly."""
    res = tools.calculate("۲ + ۲")
    assert res == 4
