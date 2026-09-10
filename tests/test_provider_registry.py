"""Comprehensive tests for Dream's Unified Provider Registry and Multi-Provider Backends."""

from __future__ import annotations

import json
from typing import Any
from urllib.request import Request

import pytest

from dream.agent import (
    AnthropicBackend,
    BaseLLMBackend,
    Dream,
    EchoBackend,
    FallbackBackend,
    GeminiBackend,
    GoogleBackend,
    OllamaBackend,
    OpenAIBackend,
    build_backend,
)
from dream.memory import MemoryStore


class MockResponse:
    def __init__(self, data: dict[str, Any], status: int = 200) -> None:
        self._data = json.dumps(data).encode("utf-8")
        self.status = status

    def read(self, *args: Any) -> bytes:
        return self._data

    def __enter__(self) -> MockResponse:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


def test_base_backend_interface():
    assert issubclass(OpenAIBackend, BaseLLMBackend)
    assert issubclass(AnthropicBackend, BaseLLMBackend)
    assert issubclass(GeminiBackend, BaseLLMBackend)
    assert issubclass(OllamaBackend, BaseLLMBackend)
    assert issubclass(EchoBackend, BaseLLMBackend)
    assert issubclass(FallbackBackend, BaseLLMBackend)


def test_anthropic_backend_payload_and_tool_call(monkeypatch):
    captured_request: Request | None = None

    def fake_urlopen(request: Request, timeout: int | None = None):
        nonlocal captured_request
        captured_request = request
        response_data = {
            "content": [
                {"type": "text", "text": "I will check the time for you."},
                {
                    "type": "tool_use",
                    "id": "toolu_01A",
                    "name": "get_datetime",
                    "input": {},
                },
            ]
        }
        return MockResponse(response_data)

    monkeypatch.setattr("dream.agent.urlopen", fake_urlopen)

    backend = AnthropicBackend(
        model="claude-3-5-sonnet-20241022",
        api_key="sk-ant-test-key",
        reasoning_effort="low",
    )
    messages = [
        {"role": "system", "content": "You are a helpful Persian assistant."},
        {"role": "user", "content": "What time is it?"},
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_datetime",
                "description": "Returns current date and time",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    result = backend.chat(messages, tools=tools)

    assert result["content"] == "I will check the time for you."
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["id"] == "toolu_01A"
    assert result["tool_calls"][0]["name"] == "get_datetime"
    assert result["tool_calls"][0]["arguments"] == {}

    assert captured_request is not None
    assert captured_request.headers.get("X-api-key") == "sk-ant-test-key"
    assert captured_request.headers.get("Anthropic-version") == "2023-06-01"

    body = json.loads(captured_request.data.decode("utf-8"))
    assert body["system"] == "You are a helpful Persian assistant."
    assert len(body["messages"]) == 1
    assert body["messages"][0]["role"] == "user"
    assert body["thinking"] == {"type": "enabled", "budget_tokens": 1024}
    assert len(body["tools"]) == 1
    assert body["tools"][0]["name"] == "get_datetime"
    assert "input_schema" in body["tools"][0]


def test_gemini_backend_payload_and_function_call(monkeypatch):
    captured_request: Request | None = None

    def fake_urlopen(request: Request, timeout: int | None = None):
        nonlocal captured_request
        captured_request = request
        response_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Calculating 2 + 2"},
                            {
                                "functionCall": {
                                    "name": "calculate",
                                    "args": {"expression": "2+2"},
                                }
                            },
                        ]
                    }
                }
            ]
        }
        return MockResponse(response_data)

    monkeypatch.setattr("dream.agent.urlopen", fake_urlopen)

    backend = GeminiBackend(
        model="gemini-2.5-flash",
        api_key="AIzaSy-gemini-test",
        oauth=False,
    )
    messages = [
        {"role": "system", "content": "You are a math tutor."},
        {"role": "user", "content": "Calculate 2+2"},
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "Calculate math",
                "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}},
            },
        }
    ]

    result = backend.chat(messages, tools=tools)

    assert result["content"] == "Calculating 2 + 2"
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["name"] == "calculate"
    assert result["tool_calls"][0]["arguments"] == {"expression": "2+2"}

    assert captured_request is not None
    assert "key=AIzaSy-gemini-test" in captured_request.full_url
    body = json.loads(captured_request.data.decode("utf-8"))
    assert body["system_instruction"]["parts"][0]["text"] == "You are a math tutor."
    assert len(body["tools"][0]["function_declarations"]) == 1
    assert body["tools"][0]["function_declarations"][0]["name"] == "calculate"


def test_gemini_backend_oauth_bearer(monkeypatch):
    captured_request: Request | None = None

    def fake_urlopen(request: Request, timeout: int | None = None):
        nonlocal captured_request
        captured_request = request
        return MockResponse({"candidates": [{"content": {"parts": [{"text": "OAuth OK"}]}}]})

    monkeypatch.setattr("dream.agent.urlopen", fake_urlopen)

    backend = GoogleBackend(
        model="gemini-2.5-pro",
        credential="oauth-access-token-123",
        oauth=True,
    )
    result = backend.chat([{"role": "user", "content": "Hello"}])
    assert result["content"] == "OAuth OK"
    assert captured_request is not None
    assert captured_request.headers.get("Authorization") == "Bearer oauth-access-token-123"
    assert "key=" not in captured_request.full_url


def test_fallback_backend_cascade_on_failure(monkeypatch):
    calls_made: list[str] = []

    class FailingBackend(BaseLLMBackend):
        def chat(self, messages, tools=None, max_retries=None):
            calls_made.append("failing")
            return {
                "content": "The provider request failed. Status 429: Rate limited.",
                "tool_calls": [],
            }

    class WorkingBackend(BaseLLMBackend):
        def chat(self, messages, tools=None, max_retries=None):
            calls_made.append("working")
            return {"content": "Hello from fallback!", "tool_calls": []}

    fallback = FallbackBackend([FailingBackend(), WorkingBackend()])
    result = fallback.chat([{"role": "user", "content": "Hi"}])

    assert result["content"] == "Hello from fallback!"
    assert calls_made == ["failing", "working"]


def test_build_backend_factory_mappings():
    # Echo
    echo = build_backend("echo")
    assert isinstance(echo, EchoBackend)

    # OpenAI
    openai_b = build_backend("openai", api_key="sk-test", model="gpt-4o")
    assert isinstance(openai_b, OpenAIBackend)
    assert openai_b.model == "gpt-4o"
    assert openai_b.base_url == "https://api.openai.com/v1"

    # Aval AI
    aval_b = build_backend("avalai", api_key="sk-aval-test")
    assert isinstance(aval_b, OpenAIBackend)
    assert aval_b.base_url == "https://api.avalai.ir/v1"

    # Anthropic / Claude
    anthropic_b = build_backend("anthropic", api_key="sk-ant", model="claude-3-5-sonnet")
    assert isinstance(anthropic_b, AnthropicBackend)
    assert anthropic_b.model == "claude-3-5-sonnet"

    # Gemini / Google
    gemini_b = build_backend("gemini", api_key="AIzaSy", model="gemini-2.5-flash")
    assert isinstance(gemini_b, GeminiBackend)
    assert gemini_b.model == "gemini-2.5-flash"

    # DeepSeek
    deepseek_b = build_backend("deepseek", api_key="sk-ds")
    assert isinstance(deepseek_b, OpenAIBackend)
    assert deepseek_b.base_url == "https://api.deepseek.com/v1"

    # Groq
    groq_b = build_backend("groq", api_key="gsk-groq")
    assert isinstance(groq_b, OpenAIBackend)
    assert groq_b.base_url == "https://api.groq.com/openai/v1"

    # Mistral
    mistral_b = build_backend("mistral", api_key="mis-key")
    assert isinstance(mistral_b, OpenAIBackend)
    assert mistral_b.base_url == "https://api.mistral.ai/v1"

    # Together
    together_b = build_backend("together", api_key="tog-key")
    assert isinstance(together_b, OpenAIBackend)
    assert together_b.base_url == "https://api.together.xyz/v1"

    # OpenRouter
    openrouter_b = build_backend("openrouter", api_key="or-key")
    assert isinstance(openrouter_b, OpenAIBackend)
    assert openrouter_b.base_url == "https://openrouter.ai/api/v1"

    # Ollama
    ollama_b = build_backend("ollama", base_url="http://localhost:11434")
    assert isinstance(ollama_b, OllamaBackend)


def test_build_backend_with_fallback_spec():
    cascade = build_backend("openai", api_key="sk-test", fallback=["groq", "echo"])
    assert isinstance(cascade, FallbackBackend)
    assert len(cascade.backends) == 3
    assert isinstance(cascade.backends[0], OpenAIBackend)
    assert isinstance(cascade.backends[1], OpenAIBackend)  # groq uses OpenAI-compat backend
    assert isinstance(cascade.backends[2], EchoBackend)


def test_build_backend_unknown_raises():
    with pytest.raises(ValueError, match="unknown backend: nonexistent"):
        build_backend("nonexistent")


def test_dream_agent_integration_with_anthropic(monkeypatch):
    def fake_urlopen(request: Request, timeout: int | None = None):
        return MockResponse({
            "content": [{"type": "text", "text": "سلام! من دریم هستم."}]
        })

    monkeypatch.setattr("dream.agent.urlopen", fake_urlopen)

    backend = AnthropicBackend(model="claude-3-5-sonnet", api_key="test-key")
    agent = Dream(store=MemoryStore(), backend=backend)
    turn = agent.run("سلام")

    assert "سلام! من دریم هستم." in turn.reply
