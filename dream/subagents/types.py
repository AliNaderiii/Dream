"""Subagent specifications, observable state dataclasses, and serialization."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from dream.subagents.constants import (
    DEFAULT_MAX_DURATION,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MAX_TURNS,
    MAX_CONTEXT_CHARS,
    MAX_DURATION_CAP,
    MAX_NAME_CHARS,
    MAX_PROMPT_CHARS,
    MAX_SYSTEM_PROMPT_CHARS,
    MAX_TOKENS_CAP,
    MAX_TOOL_GRANTS,
    MAX_TOOL_NAME_CHARS,
    MAX_TURNS_CAP,
    TERMINAL_STATUSES,
    _truncate,
)

SubAgentStatus = Literal[
    "idle", "running", "paused", "completed", "failed", "cancelled", "timeout"
]




class _LimitReached(Exception):
    """Raised inside the loop when a budget is exhausted."""

    def __init__(self, which: str) -> None:
        super().__init__(which)
        self.which = which


class _Stopped(Exception):
    """Raised inside the loop when the parent asked the child to stop."""


@dataclass(slots=True)
class LogEntry:
    """One line of a subagent's execution log."""

    ts: float
    level: str
    message: str
    seq: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "level": self.level,
            "message": self.message,
            "seq": self.seq,
        }


@dataclass(slots=True)
class SubAgentSpec:
    """Everything the parent decides before a child exists."""

    prompt: str
    name: str = ""
    context: str = ""
    system_prompt: str = ""
    model_provider: str = "echo"
    model_name: str = ""
    tools: Sequence[str] | None = None
    max_turns: int = DEFAULT_MAX_TURNS
    max_tokens: int = DEFAULT_MAX_TOKENS
    max_duration: float = DEFAULT_MAX_DURATION
    parent_session_id: str | None = None
    allow_dangerous: bool = False

    def __post_init__(self) -> None:
        self.prompt = (self.prompt or "").strip()
        if not self.prompt:
            raise ValueError("subagent prompt must not be empty")
        if len(self.prompt) > MAX_PROMPT_CHARS:
            raise ValueError(
                f"subagent prompt must be at most {MAX_PROMPT_CHARS} characters"
            )
        if len(self.system_prompt or "") > MAX_SYSTEM_PROMPT_CHARS:
            raise ValueError(
                f"system_prompt must be at most {MAX_SYSTEM_PROMPT_CHARS} characters"
            )
        self.context = _truncate(self.context or "", MAX_CONTEXT_CHARS)
        self.name = _truncate((self.name or "").strip(), MAX_NAME_CHARS) or "subagent"
        if self.tools is not None:
            if len(self.tools) > MAX_TOOL_GRANTS:
                raise ValueError(f"tools must list at most {MAX_TOOL_GRANTS} names")
            for tool_name in self.tools:
                if len(tool_name) > MAX_TOOL_NAME_CHARS:
                    raise ValueError(
                        f"tool names must be at most {MAX_TOOL_NAME_CHARS} characters"
                    )
        self.max_turns = max(1, int(self.max_turns))
        if self.max_turns > MAX_TURNS_CAP:
            raise ValueError(f"max_turns must be at most {MAX_TURNS_CAP}")
        self.max_tokens = max(1, int(self.max_tokens))
        if self.max_tokens > MAX_TOKENS_CAP:
            raise ValueError(f"max_tokens must be at most {MAX_TOKENS_CAP}")
        self.max_duration = max(0.05, float(self.max_duration))
        if self.max_duration > MAX_DURATION_CAP:
            raise ValueError(
                f"max_duration must be at most {MAX_DURATION_CAP} seconds"
            )


@dataclass(slots=True)
class SubAgent:
    """Observable state of one child agent."""

    id: str
    name: str
    parent_session_id: str | None
    model_provider: str
    model_name: str
    system_prompt: str
    tools: list[str]
    prompt: str
    context: str
    status: str = "idle"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    max_turns: int = DEFAULT_MAX_TURNS
    max_tokens: int = DEFAULT_MAX_TOKENS
    max_duration: float = DEFAULT_MAX_DURATION
    turn_count: int = 0
    token_count: int = 0
    result: str | None = None
    error: str | None = None
    pipeline_id: str | None = None
    pipeline_index: int | None = None
    limit_hit: str | None = None
    log: list[LogEntry] = field(default_factory=list)
    log_dropped: int = 0
    log_seq: int = 0
    paused_seconds: float = 0.0
    paused_at: float | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def elapsed(self, now: float | None = None) -> float:
        """Seconds of active run time, frozen once terminal."""
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else (now or time.time())
        paused = self.paused_seconds
        if self.paused_at is not None and self.finished_at is None:
            paused += max(0.0, end - self.paused_at)
        return max(0.0, end - self.started_at - paused)

    def progress(self, now: float | None = None) -> float:
        """Fraction of the tightest budget consumed, clamped to [0, 1]."""
        if self.is_terminal:
            return 1.0
        ratios = (
            self.turn_count / self.max_turns,
            self.token_count / self.max_tokens,
            self.elapsed(now) / self.max_duration,
        )
        return min(1.0, max(0.0, max(ratios)))


def subagent_to_dict(agent: SubAgent, *, include_log: bool = True) -> dict[str, Any]:
    """Serialise a subagent for the JSON-RPC wire."""
    payload: dict[str, Any] = {
        "subagent_id": agent.id,
        "id": agent.id,
        "name": agent.name,
        "parent_session_id": agent.parent_session_id,
        "model_provider": agent.model_provider,
        "model_name": agent.model_name,
        "system_prompt": agent.system_prompt,
        "tools": list(agent.tools),
        "prompt": agent.prompt,
        "context": agent.context,
        "status": agent.status,
        "created_at": agent.created_at,
        "started_at": agent.started_at,
        "finished_at": agent.finished_at,
        "max_turns": agent.max_turns,
        "max_tokens": agent.max_tokens,
        "max_duration": agent.max_duration,
        "turn_count": agent.turn_count,
        "token_count": agent.token_count,
        "result": agent.result,
        "error": agent.error,
        "pipeline_id": agent.pipeline_id,
        "pipeline_index": agent.pipeline_index,
        "limit_hit": agent.limit_hit,
        "log_dropped": agent.log_dropped,
        "elapsed": agent.elapsed(),
        "progress": agent.progress(),
    }
    if include_log:
        payload["log"] = [entry.to_dict() for entry in agent.log]
    return payload
