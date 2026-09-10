"""Core Tool dataclass, validation engine, parameter categorization, and @tool decorator."""

from __future__ import annotations

import inspect
import json
import logging
import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from dream.limits import (
    MAX_LIST_ITEMS,
    MAX_MAPPING_KEYS,
    MAX_NESTING_DEPTH,
    MAX_SERIALIZED_INPUT_SIZE,
    MAX_TOOL_INPUT_CHARS,
    NUMERIC_RANGES,
    get_parameter_category,
)

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


def _allows_none(annotation: Any, default: Any = inspect.Parameter.empty) -> bool:
    """Whether a parameter annotation or default allows None."""
    if default is not inspect.Parameter.empty and default is None:
        return True
    origin = get_origin(annotation)
    if origin is Union or origin is UnionType:
        return type(None) in get_args(annotation)
    return False


def _check_cycles(value: Any, seen: set[int]) -> None:
    """Pre-check for circular references in input structures using active-path tracking."""
    if isinstance(value, (dict, list, tuple)):
        obj_id = id(value)
        if obj_id in seen:
            raise ValueError("circular reference detected")
        seen.add(obj_id)
        try:
            if isinstance(value, dict):
                for k, v in value.items():
                    _check_cycles(k, seen)
                    _check_cycles(v, seen)
            else:
                for item in value:
                    _check_cycles(item, seen)
        finally:
            seen.remove(obj_id)


def _validate_value(
    tool_name: str,
    param_name: str,
    value: Any,
    annotation: Any,
    depth: int,
    seen: set[int],
    is_optional: bool,
) -> None:
    """Recursively validate a tool argument against its type and boundary limits."""
    if depth > MAX_NESTING_DEPTH:
        raise ValueError(
            f"Parameter {param_name!r} exceeds maximum nesting depth of {MAX_NESTING_DEPTH}"
        )

    if value is None:
        if is_optional:
            return
        raise ValueError(f"Parameter {param_name!r} cannot be None")

    if isinstance(value, (set, frozenset, bytes, bytearray)):
        raise ValueError(
            f"Parameter {param_name!r} contains unsupported type {type(value).__name__}"
        )

    is_container = isinstance(value, (dict, list, tuple))
    obj_id = id(value) if is_container else None
    if is_container:
        if obj_id in seen:
            raise ValueError(f"Parameter {param_name!r} contains a circular reference")
        seen.add(obj_id)

    try:
        origin = get_origin(annotation)
        args = get_args(annotation)
        if origin is Union or origin is UnionType:
            non_none_args = [arg for arg in args if arg is not type(None)]
            if len(non_none_args) == 1:
                annotation = non_none_args[0]
            else:
                matched = False
                for sub_annot in non_none_args:
                    try:
                        _validate_value(
                            tool_name,
                            param_name,
                            value,
                            sub_annot,
                            depth,
                            seen,
                            is_optional=True,
                        )
                        matched = True
                        break
                    except ValueError:
                        continue
                if not matched:
                    raise ValueError(
                        f"Parameter {param_name!r} value does not match allowed union types"
                    )
                return

        if annotation is int:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"Parameter {param_name!r} must be an integer")
            if param_name in NUMERIC_RANGES:
                min_val, max_val = NUMERIC_RANGES[param_name]
                if not (min_val <= value <= max_val):
                    raise ValueError(
                        f"Parameter {param_name!r} value {value} "
                        f"is out of range [{min_val}, {max_val}]"
                    )
        elif annotation is float:
            if tool_name == "remember_fact" and param_name == "importance":
                if isinstance(value, str):
                    pass
                elif not isinstance(value, (float, int)) or isinstance(value, bool):
                    raise ValueError(f"Parameter {param_name!r} must be a number")
                else:
                    fval = float(value)
                    if not math.isfinite(fval):
                        raise ValueError(
                            f"Parameter {param_name!r} contains non-finite float value"
                        )
                    if param_name in NUMERIC_RANGES:
                        min_val, max_val = NUMERIC_RANGES[param_name]
                        if not (min_val <= fval <= max_val):
                            raise ValueError(
                                f"Parameter {param_name!r} value {fval} "
                                f"is out of range [{min_val}, {max_val}]"
                            )
            else:
                if isinstance(value, str):
                    raise ValueError(f"Parameter {param_name!r} must be a number, got str")
                if not isinstance(value, (float, int)) or isinstance(value, bool):
                    raise ValueError(f"Parameter {param_name!r} must be a number")
                fval = float(value)
                if not math.isfinite(fval):
                    raise ValueError(
                        f"Parameter {param_name!r} contains non-finite float value"
                    )
                if param_name in NUMERIC_RANGES:
                    min_val, max_val = NUMERIC_RANGES[param_name]
                    if not (min_val <= fval <= max_val):
                        raise ValueError(
                            f"Parameter {param_name!r} value {fval} "
                            f"is out of range [{min_val}, {max_val}]"
                        )
        elif annotation is bool:
            if not isinstance(value, bool):
                raise ValueError(f"Parameter {param_name!r} must be a boolean")
        elif annotation is str:
            if not isinstance(value, str):
                raise ValueError(
                    f"Parameter {param_name!r} must be of type str, got {type(value).__name__}"
                )
            mandatory_non_empty = param_name in {
                "filename",
                "path",
                "address",
                "url",
                "query",
                "expression",
                "date",
                "name",
                "proposal_id",
                "timezone_name",
                "to",
                "command",
                "subject",
            }
            if mandatory_non_empty and not value.strip():
                raise ValueError(f"Parameter {param_name!r} cannot be empty")

            category = get_parameter_category(tool_name, param_name)
            max_len = MAX_TOOL_INPUT_CHARS.get(category, MAX_TOOL_INPUT_CHARS["default"])
            if len(value) > max_len:
                raise ValueError(
                    f"Parameter {param_name!r} exceeds maximum length of {max_len} characters"
                )
        elif annotation is list or origin is list:
            if not isinstance(value, list):
                raise ValueError(f"Parameter {param_name!r} must be a list")
            if len(value) > MAX_LIST_ITEMS:
                raise ValueError(
                    f"Parameter {param_name!r} exceeds maximum list items limit of {MAX_LIST_ITEMS}"
                )
            item_annot = args[0] if args else Any
            for idx, item in enumerate(value):
                _validate_value(
                    tool_name,
                    f"{param_name}[{idx}]",
                    item,
                    item_annot,
                    depth + 1,
                    seen,
                    is_optional=False,
                )
        elif annotation is dict or origin is dict:
            if not isinstance(value, dict):
                raise ValueError(f"Parameter {param_name!r} must be a mapping")
            if len(value) > MAX_MAPPING_KEYS:
                raise ValueError(
                    f"Parameter {param_name!r} exceeds maximum mapping keys limit "
                    f"of {MAX_MAPPING_KEYS}"
                )
            for k, v in value.items():
                if not isinstance(k, str):
                    raise ValueError(f"Parameter {param_name!r} mapping keys must be strings")
                _validate_value(
                    tool_name,
                    f"{param_name}.{k}",
                    v,
                    Any,
                    depth + 1,
                    seen,
                    is_optional=True,
                )
        else:
            if isinstance(value, str):
                mandatory_non_empty = param_name in {
                    "filename",
                    "path",
                    "address",
                    "url",
                    "query",
                    "expression",
                    "date",
                    "name",
                    "proposal_id",
                    "timezone_name",
                    "to",
                    "command",
                    "subject",
                }
                if mandatory_non_empty and not value.strip():
                    raise ValueError(f"Parameter {param_name!r} cannot be empty")
                category = get_parameter_category(tool_name, param_name)
                max_len = MAX_TOOL_INPUT_CHARS.get(category, MAX_TOOL_INPUT_CHARS["default"])
                if len(value) > max_len:
                    raise ValueError(
                        f"Parameter {param_name!r} exceeds maximum length of {max_len} characters"
                    )
            elif isinstance(value, list):
                if len(value) > MAX_LIST_ITEMS:
                    raise ValueError(
                        f"Parameter {param_name!r} exceeds maximum "
                        f"list items limit of {MAX_LIST_ITEMS}"
                    )
                for idx, item in enumerate(value):
                    _validate_value(
                        tool_name,
                        f"{param_name}[{idx}]",
                        item,
                        Any,
                        depth + 1,
                        seen,
                        is_optional=False,
                    )
            elif isinstance(value, dict):
                if len(value) > MAX_MAPPING_KEYS:
                    raise ValueError(
                        f"Parameter {param_name!r} exceeds maximum mapping keys limit "
                        f"of {MAX_MAPPING_KEYS}"
                    )
                for k, v in value.items():
                    if not isinstance(k, str):
                        raise ValueError(f"Parameter {param_name!r} mapping keys must be strings")
                    _validate_value(
                        tool_name,
                        f"{param_name}.{k}",
                        v,
                        Any,
                        depth + 1,
                        seen,
                        is_optional=True,
                    )
    finally:
        if is_container:
            seen.remove(obj_id)


def _validate_tool_arguments(
    tool_name: str,
    signature: inspect.Signature,
    hints: dict[str, Any],
    arguments: dict[str, Any],
) -> None:
    """Validate all bound arguments before tool execution."""
    for val in arguments.values():
        _check_cycles(val, set())

    try:
        serialized = json.dumps(arguments)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Tool input arguments for {tool_name} are not JSON-serializable"
        ) from exc

    if len(serialized.encode("utf-8")) > MAX_SERIALIZED_INPUT_SIZE:
        raise ValueError(f"Tool input arguments for {tool_name} exceed maximum serialized size")

    for param_name, value in arguments.items():
        parameter = signature.parameters.get(param_name)
        if parameter is None:
            continue
        annotation = hints.get(param_name, parameter.annotation)
        is_optional = _allows_none(annotation, parameter.default)
        _validate_value(
            tool_name,
            param_name,
            value,
            annotation,
            depth=0,
            seen=set(),
            is_optional=is_optional,
        )


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

        tool_name = function.__name__

        def validate_and_call(*args: Any, **kwargs: Any) -> Any:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            _validate_tool_arguments(tool_name, signature, hints, bound.arguments)
            return function(*args, **kwargs)

        validate_and_call.__name__ = function.__name__
        validate_and_call.__doc__ = function.__doc__
        validate_and_call.__signature__ = signature  # type: ignore

        REGISTRY[tool_name] = Tool(
            name=tool_name,
            function=validate_and_call,
            description=inspect.cleandoc(function.__doc__ or "").split("\n\n", 1)[0],
            schema=schema,
            risk=risk,
        )
        return validate_and_call

    return register
