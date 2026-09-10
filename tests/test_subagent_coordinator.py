"""Tests for SubagentCoordinator and pre-configured Subagent Roles."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from dream.subagents import (
    BUILTIN_ROLES,
    SubagentCoordinator,
    SubAgentManager,
    SubagentRole,
)


def test_builtin_roles_specs() -> None:
    assert "researcher" in BUILTIN_ROLES
    assert "coder" in BUILTIN_ROLES
    assert "data_analyst" in BUILTIN_ROLES

    researcher = BUILTIN_ROLES["researcher"]
    assert "search_web" in researcher.tools
    assert "read_page" in researcher.tools
    assert researcher.system_prompt != ""

    coder = BUILTIN_ROLES["coder"]
    assert "read_note" in coder.tools
    assert "calculate" in coder.tools


def test_coordinator_parallel_delegation(monkeypatch: pytest.MonkeyPatch) -> None:
    class MockBackend:
        def __init__(self) -> None:
            self.calls: list[list[dict[str, Any]]] = []

        def chat(
            self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
        ) -> dict[str, Any]:
            del tools
            self.calls.append(messages)
            user_msg = next((m["content"] for m in messages if m.get("role") == "user"), "")
            return {"content": f"Answer for: {user_msg}", "tool_calls": []}

    backend = MockBackend()
    monkeypatch.setattr("dream.subagents._build_backend", lambda _spec: backend)

    async def scenario() -> list[Any]:
        manager = SubAgentManager()
        coordinator = SubagentCoordinator(manager)

        tasks = [
            ("Research LLMs", "researcher"),
            ("Write Fibonacci in Python", "coder"),
            ("Calculate summary statistics", "data_analyst"),
        ]

        results = await coordinator.delegate_parallel(tasks, timeout=5.0)
        return results

    results = asyncio.run(scenario())
    assert len(results) == 3
    for sub in results:
        assert sub.status == "completed"
        assert sub.result is not None
        assert "Answer for:" in sub.result


def test_coordinator_custom_role(monkeypatch: pytest.MonkeyPatch) -> None:
    class CustomBackend:
        def chat(
            self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
        ) -> dict[str, Any]:
            del tools
            return {"content": "Custom task completed", "tool_calls": []}

    monkeypatch.setattr("dream.subagents._build_backend", lambda _spec: CustomBackend())

    async def scenario() -> list[Any]:
        manager = SubAgentManager()
        coordinator = SubagentCoordinator(manager)

        custom_role = SubagentRole(
            name="security_auditor",
            description="Audits codebase for vulnerabilities",
            system_prompt="You are a security auditor.",
            tools=("read_note", "list_notes"),
        )

        tasks = [("Scan dependencies", custom_role)]
        return await coordinator.delegate_parallel(tasks, timeout=5.0)

    results = asyncio.run(scenario())
    assert len(results) == 1
    assert results[0].name == "security_auditor"
    assert results[0].status == "completed"
    assert results[0].result == "Custom task completed"
