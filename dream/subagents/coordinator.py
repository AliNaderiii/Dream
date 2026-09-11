"""Subagent coordinator for parallel delegation, roles, and result aggregation."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from dream.subagents.types import SubAgent, SubAgentSpec


@dataclass(frozen=True)
class SubagentRole:
    """Pre-configured subagent role with specific toolsets and system directives."""

    name: str
    description: str
    system_prompt: str
    tools: tuple[str, ...]


BUILTIN_ROLES: dict[str, SubagentRole] = {
    "researcher": SubagentRole(
        name="researcher",
        description="Public internet and documentation researcher",
        system_prompt="You are a precise researcher. Search for facts and cite sources clearly.",
        tools=("search_web", "read_page", "get_datetime"),
    ),
    "coder": SubagentRole(
        name="coder",
        description="Code generator, reviewer, and workspace file reader",
        system_prompt="You are a senior software engineer. Write clean, tested code.",
        tools=("read_note", "list_notes", "calculate"),
    ),
    "data_analyst": SubagentRole(
        name="data_analyst",
        description="Statistical calculations and data inspection",
        system_prompt="You are a data scientist. Compute and explain metrics clearly.",
        tools=("calculate", "read_note", "list_notes"),
    ),
    "planner": SubagentRole(
        name="planner",
        description="Goal decomposition, task structuring, and execution planning",
        system_prompt="You are an expert project planner. Break down goals into ordered steps.",
        tools=("get_datetime", "calculate", "list_notes", "read_note"),
    ),
    "reviewer": SubagentRole(
        name="reviewer",
        description="Code and security review, quality validation, and correctness checking",
        system_prompt="You are a senior code and security reviewer. Validate accuracy and safety.",
        tools=("read_note", "list_notes", "calculate"),
    ),
}


class SubagentCoordinator:
    """High-level coordinator for managing multi-worker tasks and parallel delegations."""

    def __init__(self, manager: Any) -> None:
        self.manager = manager

    async def delegate_parallel(
        self,
        tasks: Sequence[tuple[str, str | SubagentRole]],
        *,
        timeout: float = 60.0,
        model_provider: str = "echo",
    ) -> list[SubAgent]:
        """Spawn multiple subagents in parallel and await all results.

        Args:
            tasks: List of (prompt, role_name_or_role_instance) pairs.
            timeout: Maximum wait time for all tasks.
            model_provider: LLM backend for spawned workers.

        Returns:
            List of finished SubAgent records with captured results.
        """
        specs: list[SubAgentSpec] = []
        for prompt, role_spec in tasks:
            if isinstance(role_spec, str):
                role = BUILTIN_ROLES.get(role_spec)
                tools = role.tools if role else None
                sys_prompt = role.system_prompt if role else ""
                name = role.name if role else "worker"
            else:
                tools = role_spec.tools
                sys_prompt = role_spec.system_prompt
                name = role_spec.name

            spec = SubAgentSpec(
                prompt=prompt,
                name=name,
                system_prompt=sys_prompt,
                tools=tools,
                model_provider=model_provider,
            )
            specs.append(spec)

        agents = [self.manager.spawn(s) for s in specs]

        await asyncio.gather(
            *[self.manager.wait(a.id, timeout=timeout) for a in agents],
            return_exceptions=True,
        )

        return [self.manager.get(a.id) or a for a in agents]
