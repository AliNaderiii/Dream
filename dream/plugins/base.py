"""Abstract base class and lifecycle interface for Dream plugins."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dream.plugins.types import PluginManifest


@dataclass
class PluginContext:
    """Execution context provided to a plugin upon activation."""

    workspace_root: Path
    config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class BasePlugin:
    """Base class that all Dream community and builtin plugins inherit from."""

    def __init__(self, manifest: PluginManifest) -> None:
        self.manifest = manifest
        self.context: PluginContext | None = None
        self.is_active = False

    def on_load(self, context: PluginContext) -> bool:
        """Invoked when the plugin is loaded into the PluginManager."""
        self.context = context
        self.is_active = True
        return True

    def on_unload(self) -> None:
        """Invoked when the plugin is disabled or unloaded."""
        self.is_active = False
        self.context = None

    def on_turn_start(self, user_text: str) -> str | None:
        """Hook executed before an agent turn begins. Can return modified input text."""
        return None

    def on_turn_end(self, agent_reply: str) -> str | None:
        """Hook executed after an agent turn completes. Can return modified reply."""
        return None

    def register_tools(self) -> list[dict[str, Any]]:
        """Return a list of tool definitions contributed by this plugin."""
        return []

    def register_commands(self) -> dict[str, Callable[[str], Any]]:
        """Return a mapping of slash command names to their handler functions."""
        return {}
