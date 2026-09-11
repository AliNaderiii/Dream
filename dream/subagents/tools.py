"""Agent tools for spawning, monitoring, and delegating tasks to isolated subagents."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from dream.subagents.coordinator import BUILTIN_ROLES, SubagentCoordinator
from dream.subagents.manager import SubAgentManager
from dream.subagents.types import SubAgentSpec
from dream.tools.base import tool

logger = logging.getLogger(__name__)

_GLOBAL_SUBAGENT_MANAGER: SubAgentManager | None = None
_GLOBAL_SUBAGENT_COORDINATOR: SubagentCoordinator | None = None


def get_subagent_manager() -> SubAgentManager:
    """Retrieve or initialize singleton SubAgentManager."""
    global _GLOBAL_SUBAGENT_MANAGER, _GLOBAL_SUBAGENT_COORDINATOR
    if _GLOBAL_SUBAGENT_MANAGER is None:
        _GLOBAL_SUBAGENT_MANAGER = SubAgentManager()
        _GLOBAL_SUBAGENT_COORDINATOR = SubagentCoordinator(_GLOBAL_SUBAGENT_MANAGER)
    return _GLOBAL_SUBAGENT_MANAGER


def get_subagent_coordinator() -> SubagentCoordinator:
    """Retrieve or initialize singleton SubagentCoordinator."""
    global _GLOBAL_SUBAGENT_COORDINATOR
    if _GLOBAL_SUBAGENT_COORDINATOR is None:
        get_subagent_manager()
    assert _GLOBAL_SUBAGENT_COORDINATOR is not None
    return _GLOBAL_SUBAGENT_COORDINATOR


def reset_subagent_manager() -> None:
    """Reset global subagent manager and coordinator for isolated testing."""
    global _GLOBAL_SUBAGENT_MANAGER, _GLOBAL_SUBAGENT_COORDINATOR
    _GLOBAL_SUBAGENT_MANAGER = None
    _GLOBAL_SUBAGENT_COORDINATOR = None


def _run_async(coro: Any) -> Any:
    """Helper to run async subagent operations synchronously for tool dispatch."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=120.0)
    else:
        return asyncio.run(coro)


@tool(risk="guarded")
def subagent_spawn(
    task: str,
    name: str = "worker",
    role: str = "researcher",
    max_turns: int = 10,
    max_duration: int = 60,
) -> str:
    """Spawn an isolated background subagent to execute a specific sub-task.

    :param task: The concrete goal or question for the subagent.
    :param name: Short mnemonic label for the worker.
    :param role: Pre-configured role ('researcher', 'coder', 'data_analyst', 'planner', 'reviewer').
    :param max_turns: Maximum conversation turns allowed for the subagent.
    :param max_duration: Maximum runtime in seconds.
    """
    mgr = get_subagent_manager()
    role_obj = BUILTIN_ROLES.get(role.lower())
    tools = role_obj.tools if role_obj else None
    sys_prompt = role_obj.system_prompt if role_obj else ""

    spec = SubAgentSpec(
        prompt=task,
        name=name,
        system_prompt=sys_prompt,
        tools=tools,
        max_turns=max_turns,
        max_duration=max_duration,
    )
    agent = mgr.spawn(spec)
    return json.dumps(
        {
            "subagent_id": agent.id,
            "name": agent.name,
            "status": agent.status,
            "role": role,
            "message": f"Subagent '{agent.name}' spawned with ID '{agent.id}'.",
        },
        ensure_ascii=False,
        indent=2,
    )


@tool(risk="guarded")
def subagent_wait(subagent_id: str, timeout_seconds: int = 30) -> str:
    """Wait for a running subagent to complete and return its final outcome.

    :param subagent_id: ID of the subagent to wait for.
    :param timeout_seconds: Maximum seconds to wait.
    """
    mgr = get_subagent_manager()

    async def _wait():
        return await mgr.wait(subagent_id, timeout=float(timeout_seconds))

    try:
        agent = _run_async(_wait())
        if not agent:
            return json.dumps({"error": f"Subagent '{subagent_id}' not found."}, ensure_ascii=False)
        return json.dumps(
            {
                "subagent_id": agent.id,
                "name": agent.name,
                "status": agent.status,
                "turn_count": agent.turn_count,
                "token_count": agent.token_count,
                "result": agent.result,
                "error": agent.error,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"error": f"Error waiting for subagent: {exc}"}, ensure_ascii=False)


@tool(risk="guarded")
def subagent_delegate_task(
    task: str,
    role: str = "researcher",
    name: str = "delegate",
    timeout_seconds: int = 60,
) -> str:
    """Convenience tool: spawn a subagent, await its completion, and return results directly.

    :param task: The prompt or task description.
    :param role: Role ('researcher', 'coder', 'data_analyst', 'planner', 'reviewer').
    :param name: Label for the delegate.
    :param timeout_seconds: Maximum timeout in seconds.
    """
    mgr = get_subagent_manager()
    role_obj = BUILTIN_ROLES.get(role.lower())
    tools = role_obj.tools if role_obj else None
    sys_prompt = role_obj.system_prompt if role_obj else ""

    spec = SubAgentSpec(
        prompt=task,
        name=name,
        system_prompt=sys_prompt,
        tools=tools,
        max_duration=timeout_seconds,
    )
    agent = mgr.spawn(spec)

    async def _wait():
        return await mgr.wait(agent.id, timeout=float(timeout_seconds))

    try:
        finished = _run_async(_wait())
        if not finished:
            return json.dumps(
                {"error": "Subagent execution timed out or failed."},
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "status": finished.status,
                "result": finished.result,
                "turn_count": finished.turn_count,
                "token_count": finished.token_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"error": f"Subagent delegation failed: {exc}"}, ensure_ascii=False)


@tool(risk="safe")
def subagent_list() -> str:
    """List all active and retained subagents with status and token metrics."""
    mgr = get_subagent_manager()
    agents = mgr.list()
    records = [
        {
            "id": a.id,
            "name": a.name,
            "status": a.status,
            "turn_count": a.turn_count,
            "token_count": a.token_count,
            "started_at": a.started_at,
        }
        for a in agents
    ]
    return json.dumps({"subagents": records, "count": len(records)}, ensure_ascii=False, indent=2)


@tool(risk="guarded")
def subagent_terminate(subagent_id: str) -> str:
    """Stop and terminate a running subagent.

    :param subagent_id: ID of the subagent to stop.
    """
    mgr = get_subagent_manager()

    async def _cancel():
        return await mgr.cancel(subagent_id)

    try:
        agent = _run_async(_cancel())
        if agent:
            return f"Subagent '{subagent_id}' has been canceled."
        return f"Subagent '{subagent_id}' not found."
    except Exception as exc:
        return f"Error canceling subagent '{subagent_id}': {exc}"
