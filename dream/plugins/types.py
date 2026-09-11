"""Domain types and data models for the Dynamic Plugin Architecture and Extension Subsystem."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PluginPermission(str, Enum):
    """Scoped permissions requested by a plugin."""

    NETWORK = "network"
    FILE_SYSTEM = "file_system"
    TERMINAL = "terminal"
    SECRETS = "secrets"
    MODEL = "model"
    SYSTEM = "system"


class PluginStatus(str, Enum):
    """Lifecycle runtime state of an installed plugin."""

    INSTALLED = "installed"
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class PluginHookEvent(str, Enum):
    """Standard lifecycle hooks that plugins can bind to."""

    ON_STARTUP = "on_startup"
    ON_SHUTDOWN = "on_shutdown"
    PRE_TURN = "pre_turn"
    POST_TURN = "post_turn"
    PRE_TOOL_CALL = "pre_tool_call"
    POST_TOOL_CALL = "post_tool_call"


@dataclass(slots=True)
class PluginManifest:
    """Descriptor and manifest defining plugin capabilities, permissions, and tools."""

    plugin_id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    permissions: list[PluginPermission] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    hooks: list[PluginHookEvent] = field(default_factory=list)
    status: PluginStatus = PluginStatus.INSTALLED
    entrypoint: str = ""
    installed_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize plugin manifest to dictionary."""
        s_val = (
            self.status.value
            if isinstance(self.status, PluginStatus)
            else self.status
        )
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "permissions": [
                p.value if isinstance(p, PluginPermission) else p
                for p in self.permissions
            ],
            "tools": self.tools,
            "hooks": [
                h.value if isinstance(h, PluginHookEvent) else h
                for h in self.hooks
            ],
            "status": s_val,
            "entrypoint": self.entrypoint,
            "installed_at": self.installed_at,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class PluginHookResult:
    """Execution result of a triggered plugin hook."""

    plugin_id: str
    event: PluginHookEvent
    success: bool
    modified_context: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize hook result to dictionary."""
        e_val = (
            self.event.value
            if isinstance(self.event, PluginHookEvent)
            else self.event
        )
        return {
            "plugin_id": self.plugin_id,
            "event": e_val,
            "success": self.success,
            "modified_context": self.modified_context,
            "message": self.message,
        }
