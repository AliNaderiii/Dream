"""Parser battery over real-shaped family outputs and repaired fallback text."""

from __future__ import annotations

from dream.providerhubs.parsers import parse_tool_calls, repair_json


def test_function_tools_from_chat_payload() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "search",
                                "arguments": '{"q": "tehran weather"}',
                            },
                        }
                    ],
                }
            }
        ]
    }
    calls = parse_tool_calls("", "function_tools", payload)
    assert calls[0]["name"] == "search"
    assert calls[0]["arguments"]["q"] == "tehran weather"
    assert calls[0]["source"] == "native"


def test_qwen_tagged_json() -> None:
    text = '<tool_call>\n{"name": "search", "arguments": {"q": "tehran"}}\n</tool_call>'
    calls = parse_tool_calls(text, "qwen")
    assert calls[0]["name"] == "search"
    assert calls[0]["arguments"] == {"q": "tehran"}


def test_llama3_python_tag() -> None:
    text = '<|python_tag|>{"name": "search", "parameters": {"q": "tehran"}}'
    calls = parse_tool_calls(text, "llama3")
    assert calls[0]["name"] == "search"
    assert calls[0]["arguments"]["q"] == "tehran"


def test_mistral_tool_calls_prefix() -> None:
    text = '[TOOL_CALLS] [{"name": "search", "arguments": {"q": "tehran"}}]'
    calls = parse_tool_calls(text, "mistral")
    assert len(calls) == 1
    assert calls[0]["name"] == "search"


def test_hermes_name_then_json() -> None:
    text = '<tool_call>\nsearch\n{"q": "tehran"}\n</tool_call>'
    calls = parse_tool_calls(text, "hermes")
    assert calls[0]["name"] == "search"
    assert calls[0]["arguments"]["q"] == "tehran"


def test_deepseek_fenced_json() -> None:
    text = 'tool_request\n```json\n{"name": "search", "arguments": {"q": "tehran"}}\n```'
    calls = parse_tool_calls(text, "deepseek")
    assert calls[0]["name"] == "search"


def test_glm_tool_call_line() -> None:
    text = 'tool call search\n```json\n{"q": "tehran"}\n```'
    calls = parse_tool_calls(text, "glm")
    assert calls[0]["name"] == "search"
    assert calls[0]["arguments"]["q"] == "tehran"


def test_generic_fallback_repairs_malformed_json() -> None:
    text = "I will call a tool now\n{name: 'search', arguments: {q: 'tehran',}}"
    calls = parse_tool_calls(text, "generic_fallback")
    assert calls[0]["name"] == "search"
    assert calls[0]["arguments"]["q"] == "tehran"
    assert calls[0]["source"] == "repaired"


def test_repair_json_strips_trailing_commas() -> None:
    assert repair_json('{"name": "search",}') == {"name": "search"}


def test_unknown_family_uses_fallback() -> None:
    text = '{"name": "remember", "arguments": {"fact": "tea"}}'
    calls = parse_tool_calls(text, "not-a-family")
    assert calls[0]["name"] == "remember"
