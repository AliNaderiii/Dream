"""Data models for Model Context Protocol (MCP) clients, servers, tools, and resources."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ServerType = Literal["stdio", "sse", "ws"]


@dataclass
class MCPTool:
    """A tool exposed by an MCP server."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_id: str = ""
    server_name: str = ""
    enabled: bool = True
    risk: str = "guarded"  # safe | guarded | dangerous

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "schema": self.input_schema,  # for bridge compatibility
            "server_id": self.server_id,
            "server_name": self.server_name,
            "enabled": self.enabled,
            "risk": self.risk,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], server_id: str = "", server_name: str = "") -> MCPTool:
        schema = data.get("inputSchema") or data.get("input_schema") or data.get("schema") or {}
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            input_schema=schema,
            server_id=server_id or str(data.get("server_id", "")),
            server_name=server_name or str(data.get("server_name", "")),
            enabled=bool(data.get("enabled", True)),
            risk=str(data.get("risk", "guarded")),
        )


@dataclass
class MCPResource:
    """A resource (file, database, doc) exposed by an MCP server."""

    uri: str
    name: str = ""
    description: str = ""
    mime_type: str = "text/plain"
    server_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mime_type": self.mime_type,
            "mimeType": self.mime_type,
            "server_id": self.server_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], server_id: str = "") -> MCPResource:
        return cls(
            uri=str(data.get("uri", "")),
            name=str(data.get("name", data.get("uri", ""))),
            description=str(data.get("description", "")),
            mime_type=str(data.get("mimeType", data.get("mime_type", "text/plain"))),
            server_id=server_id or str(data.get("server_id", "")),
        )


@dataclass
class MCPPrompt:
    """A prompt template exposed by an MCP server."""

    name: str
    description: str = ""
    arguments: list[dict[str, Any]] = field(default_factory=list)
    server_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": self.arguments,
            "server_id": self.server_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], server_id: str = "") -> MCPPrompt:
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            arguments=list(data.get("arguments", [])),
            server_id=server_id or str(data.get("server_id", "")),
        )


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server connection."""

    id: str
    name: str
    type: ServerType
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    disabled_tools: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "url": self.url,
            "headers": self.headers,
            "enabled": self.enabled,
            "disabled_tools": self.disabled_tools,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPServerConfig:
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            type=data.get("type", "stdio"),  # type: ignore
            command=data.get("command"),
            args=list(data.get("args", [])),
            env=dict(data.get("env", {})),
            url=data.get("url"),
            headers=dict(data.get("headers", {})),
            enabled=bool(data.get("enabled", True)),
            disabled_tools=list(data.get("disabled_tools", [])),
        )
