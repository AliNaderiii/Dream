"""Math calculation tool using safe AST evaluation."""

from __future__ import annotations

import ast
from collections.abc import Callable
from typing import Any

from dream.memory import normalize_fa
from dream.tools.base import tool

_ALLOWED_BINARY_OPERATORS: dict[type[ast.operator], Callable[[int | float, int | float], Any]] = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.FloorDiv: lambda left, right: left // right,
    ast.Mod: lambda left, right: left % right,
    ast.Pow: lambda left, right: left**right,
}
_ALLOWED_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[int | float], Any]] = {
    ast.UAdd: lambda value: value,
    ast.USub: lambda value: -value,
}


def _calculate_node(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINARY_OPERATORS:
        return _ALLOWED_BINARY_OPERATORS[type(node.op)](
            _calculate_node(node.left), _calculate_node(node.right)
        )
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY_OPERATORS:
        return _ALLOWED_UNARY_OPERATORS[type(node.op)](_calculate_node(node.operand))
    raise ValueError("expression contains an unsupported operation")


@tool(risk="safe")
def calculate(expression: str) -> int | float:
    """Evaluate a basic arithmetic expression without executing code.

    :param expression: Arithmetic using numbers, parentheses and allowed operators.
    """
    expression = normalize_fa(expression).translate(str.maketrans({"×": "*", "÷": "/"}))
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("invalid arithmetic expression") from exc
    return _calculate_node(parsed.body)
