"""Data models for Agent Client Protocol (ACP) server, client, and external agents."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ACPSession:
    """An active or persisted ACP conversation session."""

    id: str
    title: str = "New Session"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": len(self.messages),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ACPSession:
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "New Session")),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            metadata=dict(data.get("metadata", {})),
            messages=list(data.get("messages", [])),
        )


@dataclass
class ACPMessage:
    """A message payload in the ACP protocol."""

    role: str  # user | assistant | system | tool
    content: str
    name: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "name": self.name,
            "tool_calls": self.tool_calls,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ACPMessage:
        return cls(
            role=str(data.get("role", "user")),
            content=str(data.get("content", "")),
            name=data.get("name"),
            tool_calls=list(data.get("tool_calls", [])),
            timestamp=float(data.get("timestamp", time.time())),
        )


@dataclass
class ACPAgentConfig:
    """Configuration for an external ACP agent (e.g. Codex, Gemini CLI, Claude Code)."""

    id: str
    name: str
    endpoint: str
    token: str | None = None
    label: str = ""
    description: str = ""
    model: str | None = None
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "endpoint": self.endpoint,
            "token": "[REDACTED]" if self.token else None,
            "label": self.label or self.name,
            "description": self.description,
            "model": self.model,
            "enabled": self.enabled,
        }

    def to_full_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "endpoint": self.endpoint,
            "token": self.token,
            "label": self.label or self.name,
            "description": self.description,
            "model": self.model,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ACPAgentConfig:
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            endpoint=str(data.get("endpoint", "")),
            token=data.get("token"),
            label=str(data.get("label", data.get("name", ""))),
            description=str(data.get("description", "")),
            model=data.get("model"),
            enabled=bool(data.get("enabled", True)),
        )
