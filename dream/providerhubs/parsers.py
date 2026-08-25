"""Tool-call parser registry: family parsers plus a repairing fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from dream.providerhubs.types import PARSER_FAMILIES

_TAG_RE = re.compile(
    r"<(?:tool_call|tool_request|function_call)>\s*(.*?)\s*</(?:tool_call|tool_request|function_call)>",
    re.DOTALL | re.IGNORECASE,
)
_MISTRAL_RE = re.compile(r"\[TOOL_CALLS?\]\s*(\[.*?\]|\{.*?\})", re.DOTALL)
_LLAMA_RE = re.compile(r"<\|python_tag\|>\s*(\{.*?\})", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_UNQUOTED_KEY_RE = re.compile(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:")


class ToolCall(dict[str, Any]):
    """A parsed tool call as a plain dict for JSON-RPC results."""

    @classmethod
    def make(
        cls,
        name: str,
        arguments: dict[str, Any] | str,
        *,
        call_id: str = "",
        source: str = "native",
    ) -> ToolCall:
        parsed = arguments
        if isinstance(arguments, str):
            parsed = _loads_maybe(arguments) or {"raw": arguments}
        if not isinstance(parsed, dict):
            parsed = {"value": parsed}
        return cls(
            {
                "id": call_id,
                "name": name,
                "arguments": parsed,
                "source": source,
            }
        )


def parse_tool_calls(
    text: str,
    family: str = "generic_fallback",
    payload: Any = None,
) -> list[ToolCall]:
    """Parse tool calls from a model payload and/or raw text."""
    if family not in PARSER_FAMILIES:
        family = "generic_fallback"
    calls = _from_payload(payload)
    if calls:
        return calls
    body = text or ""
    if payload and not body:
        body = _text_from_payload(payload)
    parser = _PARSERS.get(family, parse_generic)
    return parser(body)


def parse_function_tools(text: str) -> list[ToolCall]:
    """Function/tools JSON: ``tool_calls`` arrays or a lone function object."""
    loaded = _loads_maybe(text)
    if loaded is not None:
        calls = _from_payload(loaded)
        if calls:
            return calls
    return parse_generic(text)


def parse_qwen(text: str) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for blob in _TAG_RE.findall(text):
        calls.extend(_calls_from_object(_loads_maybe(blob) or repair_json(blob), source="qwen"))
    return calls or parse_generic(text)


def parse_llama3(text: str) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for blob in _LLAMA_RE.findall(text):
        obj = _loads_maybe(blob) or repair_json(blob)
        if isinstance(obj, dict):
            name = str(obj.get("name") or obj.get("function") or "")
            args = obj.get("parameters") or obj.get("arguments") or {}
            if name:
                calls.append(ToolCall.make(name, args, source="llama3"))
    return calls or parse_generic(text)


def parse_mistral(text: str) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for blob in _MISTRAL_RE.findall(text):
        calls.extend(_calls_from_object(_loads_maybe(blob) or repair_json(blob), source="mistral"))
    return calls or parse_generic(text)


def parse_hermes(text: str) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for blob in _TAG_RE.findall(text):
        stripped = blob.strip()
        loaded = _loads_maybe(stripped) or repair_json(stripped)
        named = _calls_from_object(loaded, source="hermes") if loaded is not None else []
        if named:
            calls.extend(named)
            continue
        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        if len(lines) >= 2:
            args = _loads_maybe(lines[1]) or repair_json(lines[1]) or {}
            if isinstance(args, dict):
                calls.append(ToolCall.make(lines[0], args, source="hermes"))
    return calls or parse_generic(text)


def parse_deepseek(text: str) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for blob in _FENCE_RE.findall(text):
        calls.extend(_calls_from_object(_loads_maybe(blob) or repair_json(blob), source="deepseek"))
    marker = "tool_request"
    if marker in text.lower() and not calls:
        calls.extend(parse_generic(text))
        for call in calls:
            call["source"] = "deepseek"
    return calls or parse_generic(text)


def parse_glm(text: str) -> list[ToolCall]:
    match = re.search(r"tool call\s+([A-Za-z0-9_.-]+)", text, re.IGNORECASE)
    if match:
        after = text[match.end() :]
        args: Any = {}
        fenced = _FENCE_RE.search(after)
        if fenced:
            args = _loads_maybe(fenced.group(1)) or repair_json(fenced.group(1)) or {}
        return [ToolCall.make(match.group(1), args if isinstance(args, dict) else {}, source="glm")]
    return parse_generic(text)


def parse_generic(text: str) -> list[ToolCall]:
    """Best-effort parse of structured text, with JSON repair."""
    calls: list[ToolCall] = []
    for blob in _candidate_blobs(text):
        obj = _loads_maybe(blob)
        source = "fallback"
        if obj is None:
            obj = repair_json(blob)
            source = "repaired"
        calls.extend(_calls_from_object(obj, source=source))
        if calls:
            break
    return calls


def repair_json(fragment: str) -> Any | None:
    """Repair common local-model JSON mistakes and load the result."""
    if not fragment or not fragment.strip():
        return None
    snippet = fragment.strip()
    starts = [index for index in (snippet.find("{"), snippet.find("[")) if index >= 0]
    start = min(starts) if starts else -1
    if start < 0:
        return None
    snippet = _balance(snippet[start:])
    snippet = snippet.replace("'", '"')
    snippet = _TRAILING_COMMA_RE.sub(r"\1", snippet)
    snippet = _UNQUOTED_KEY_RE.sub(r'\1"\2":', snippet)
    try:
        return json.loads(snippet)
    except (TypeError, ValueError):
        return None


def _PARSERS_build() -> dict[str, Any]:
    return {
        "function_tools": parse_function_tools,
        "qwen": parse_qwen,
        "llama3": parse_llama3,
        "mistral": parse_mistral,
        "hermes": parse_hermes,
        "deepseek": parse_deepseek,
        "glm": parse_glm,
        "generic_fallback": parse_generic,
    }


_PARSERS = _PARSERS_build()


def _loads_maybe(value: Any) -> Any | None:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _from_payload(payload: Any) -> list[ToolCall]:
    if not isinstance(payload, dict):
        return []
    message = payload
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or choices[0]
    if not isinstance(message, dict):
        return []
    raw_calls = message.get("tool_calls") or message.get("function_call")
    return _calls_from_object(raw_calls, source="native")


def _text_from_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
    content = payload.get("content")
    return content if isinstance(content, str) else ""


def _calls_from_object(obj: Any, *, source: str) -> list[ToolCall]:
    if obj is None:
        return []
    rows = obj if isinstance(obj, list) else [obj]
    calls: list[ToolCall] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        function = row.get("function") if isinstance(row.get("function"), dict) else row
        name = str(function.get("name") or row.get("name") or "").strip()
        if not name:
            continue
        args = function.get("arguments") if "arguments" in function else row.get("arguments")
        if args is None:
            args = function.get("parameters") or row.get("parameters") or {}
        calls.append(
            ToolCall.make(
                name,
                args if args is not None else {},
                call_id=str(row.get("id") or ""),
                source=source,
            )
        )
    return calls


def _candidate_blobs(text: str) -> list[str]:
    blobs = [text]
    blobs.extend(_FENCE_RE.findall(text))
    blobs.extend(_TAG_RE.findall(text))
    return [blob for blob in blobs if blob and blob.strip()]


def _balance(snippet: str) -> str:
    depth_curly = 0
    depth_square = 0
    end = 0
    for index, char in enumerate(snippet):
        if char == "{":
            depth_curly += 1
        elif char == "}":
            depth_curly -= 1
        elif char == "[":
            depth_square += 1
        elif char == "]":
            depth_square -= 1
        end = index + 1
        if depth_curly <= 0 and depth_square <= 0 and index > 0:
            break
    return snippet[:end]
