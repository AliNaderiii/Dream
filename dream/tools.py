"""A small, schema-driven tool registry with explicit risk tiers.

Tools are ordinary Python functions.  Their callable signatures are the single
source of truth for provider schemas, preventing a hand-maintained schema from
drifting away from the code that ultimately receives model arguments.
"""

from __future__ import annotations

import ast
import inspect
import json
import logging
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints
from zoneinfo import ZoneInfo

from dream.memory import normalize_fa

__all__ = [
    "REGISTRY",
    "Tool",
    "_safe_path",
    "anthropic_schemas",
    "calculate",
    "execute",
    "get_datetime",
    "list_notes",
    "openai_schemas",
    "read_note",
    "run_shell",
    "send_email",
    "tool",
    "write_note",
]

RISKS = frozenset({"safe", "guarded", "dangerous"})
WORKSPACE_ROOT = Path(os.environ.get("DREAM_WORKSPACE_ROOT", Path.cwd())).resolve()


@dataclass(frozen=True, slots=True)
class Tool:
    """A registered callable and the schema derived from its signature."""

    name: str
    function: Callable[..., Any]
    description: str
    schema: dict[str, Any]
    risk: str


REGISTRY: dict[str, Tool] = {}
logger = logging.getLogger(__name__)


def _param_descriptions(docstring: str) -> dict[str, str]:
    """Extract reStructuredText ``:param name: text`` descriptions."""
    descriptions: dict[str, str] = {}
    for line in inspect.cleandoc(docstring).splitlines():
        line = line.strip()
        if not line.startswith(":param ") or ":" not in line[7:]:
            continue
        name, description = line[7:].split(":", 1)
        descriptions[name.strip()] = description.strip()
    return descriptions


def _union_json_type(args: tuple[Any, ...]) -> dict[str, Any]:
    """Describe a union, unwrapping ``X | None`` to the schema for ``X``.

    An optional parameter is still the type it wraps: ``list | None`` accepts a
    list, so a model told it is a ``string`` will send the wrong thing.
    """
    members = [arg for arg in args if arg is not type(None)]
    if not members:
        return {"type": "null"}
    if len(members) == 1:
        return _json_type(members[0])
    return {"anyOf": [_json_type(member) for member in members]}


def _json_type(annotation: Any) -> dict[str, Any]:
    """Translate the supported Python annotations to JSON Schema."""
    origin = get_origin(annotation)
    if origin is Union or origin is UnionType:
        return _union_json_type(get_args(annotation))
    if origin is Literal:
        values = list(get_args(annotation))
        schema: dict[str, Any] = {"enum": values}
        if values:
            schema["type"] = _json_type(type(values[0]))["type"]
        return schema
    if origin is list or annotation is list:
        return {"type": "array"}
    if origin is dict or annotation is dict:
        return {"type": "object"}
    types = {str: "string", int: "integer", float: "number", bool: "boolean"}
    return {"type": types.get(annotation, "string")}


def tool(*, risk: str = "safe") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a function and derive its input schema from type hints."""
    if risk not in RISKS:
        raise ValueError(f"risk must be one of {sorted(RISKS)}, got {risk!r}")

    def register(function: Callable[..., Any]) -> Callable[..., Any]:
        signature = inspect.signature(function)
        hints = get_type_hints(function)
        descriptions = _param_descriptions(function.__doc__ or "")
        properties: dict[str, Any] = {}
        required: list[str] = []
        for name, parameter in signature.parameters.items():
            if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
                continue
            property_schema = _json_type(hints.get(name, parameter.annotation))
            if name in descriptions:
                property_schema["description"] = descriptions[name]
            properties[name] = property_schema
            if parameter.default is inspect.Parameter.empty:
                required.append(name)
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        REGISTRY[function.__name__] = Tool(
            name=function.__name__,
            function=function,
            description=inspect.cleandoc(function.__doc__ or "").split("\n\n", 1)[0],
            schema=schema,
            risk=risk,
        )
        return function

    return register


def openai_schemas() -> list[dict[str, Any]]:
    """Return registered tools in OpenAI's function-tool format."""
    return [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": t.schema},
        }
        for t in REGISTRY.values()
    ]


def anthropic_schemas() -> list[dict[str, Any]]:
    """Return registered tools in Anthropic's tool format."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.schema}
        for t in REGISTRY.values()
    ]


def _safe_path(rel: str) -> Path:
    """Resolve a relative workspace path, rejecting every escape attempt."""
    candidate = Path(rel)
    if candidate.is_absolute():
        raise PermissionError("absolute paths are not permitted")
    path = (WORKSPACE_ROOT / candidate).resolve()
    try:
        path.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise PermissionError("path escapes the workspace root") from exc
    return path


@tool(risk="safe")
def get_datetime(timezone_name: str = "Asia/Tehran") -> str:
    """Return the current date and time in an IANA time zone.

    :param timezone_name: IANA zone name, such as ``Asia/Tehran``.
    """
    return datetime.now(ZoneInfo(timezone_name)).isoformat()


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


@tool(risk="safe")
def read_note(filename: str) -> str:
    """Read a UTF-8 text file from the workspace.

    :param filename: Relative path of the note to read.
    """
    return _safe_path(filename).read_text(encoding="utf-8")


@tool(risk="safe")
def list_notes() -> list[str]:
    """List regular files in the workspace, relative to its root."""
    return sorted(
        str(path.relative_to(WORKSPACE_ROOT))
        for path in WORKSPACE_ROOT.rglob("*")
        if path.is_file()
    )


@tool(risk="guarded")
def write_note(filename: str, content: str) -> str:
    """Write UTF-8 text to a workspace file.

    :param filename: Relative path of the note to write.
    :param content: Exact text to store in the note.
    """
    path = _safe_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"wrote {path.relative_to(WORKSPACE_ROOT)}"


@tool(risk="dangerous")
def run_shell(command: str, timeout: int = 30) -> dict[str, Any]:
    """Run a shell command after explicit human approval.

    :param command: Shell command to run.
    :param timeout: Maximum execution time in seconds.
    """
    completed = subprocess.run(
        command,
        shell=True,
        cwd=WORKSPACE_ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


@tool(risk="dangerous")
def send_email(to: str, subject: str, body: str) -> dict[str, str]:
    """Describe an email that would be sent; this stub never sends mail.

    :param to: Intended recipient address.
    :param subject: Intended email subject.
    :param body: Intended email body.
    """
    return {
        "status": "dry-run",
        "message": f"Would send email to {to!r} with subject {subject!r}",
        "body": body,
    }


def _failure_payload(error_type: str, message: str) -> dict[str, Any]:
    """Build an error payload that cannot be mistaken for a result.

    The agent feeds this string straight back to the model. A bare
    ``{"error": ...}`` is easy for a small model to skim past and narrate as a
    success, so every failure carries an explicit ``"status": "error"`` and a
    message that starts with ``Tool call failed:``.
    """
    return {"status": "error", "error": {"type": error_type, "message": message}}


def execute(name: str, arguments: dict[str, Any], *, approved: bool = False) -> str:
    """Run a registered tool and JSON-encode its result or error.

    Dangerous tools remain blocked unless an approval gate explicitly passes
    ``approved=True``. This keeps direct callers fail-closed while allowing the
    agent runtime to enforce a human decision on its execution path.
    """
    registered = REGISTRY.get(name)
    if registered is None:
        return json.dumps(
            _failure_payload("unknown_tool", f"Tool call failed: unknown tool: {name}"),
            ensure_ascii=False,
        )
    if registered.risk == "dangerous" and not approved:
        return json.dumps(
            _failure_payload(
                "approval_required",
                f"Tool call failed: {name} requires human approval and none was given",
            ),
            ensure_ascii=False,
        )
    if registered.risk == "guarded":
        logger.info("executing guarded tool: %s", name)
    try:
        result = registered.function(**arguments)
        return json.dumps({"status": "ok", "result": result}, ensure_ascii=False)
    except Exception as exc:  # Tool boundaries return data, never leak exceptions.
        return json.dumps(
            _failure_payload(
                type(exc).__name__,
                f"Tool call failed: {name}() raised {type(exc).__name__}: {exc}",
            ),
            ensure_ascii=False,
        )
