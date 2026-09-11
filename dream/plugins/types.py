"""Data models and type definitions for the Dynamic Plugin Subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class PluginStatus(str, Enum):
    """Lifecycle and operational status of a plugin."""

    UNLOADED = "unloaded"
    LOADED = "loaded"
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class PluginManifest:
    """Metadata manifest describing a Dream plugin."""

    name: str
    version: str
    author: str
    description_en: str
    description_fa: str
    permissions: list[str] = field(default_factory=lambda: ["tools", "commands"])
    enabled_by_default: bool = True
    min_dream_version: str = "0.4.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize manifest to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description_en": self.description_en,
            "description_fa": self.description_fa,
            "permissions": self.permissions,
            "enabled_by_default": self.enabled_by_default,
            "min_dream_version": self.min_dream_version,
            "metadata": self.metadata,
        }


@dataclass
class PluginInfo:
    """Runtime diagnostic status and metadata of a registered plugin."""

    manifest: PluginManifest
    status: PluginStatus
    tools_registered: list[str] = field(default_factory=list)
    commands_registered: list[str] = field(default_factory=list)
    error_message: str | None = None
    loaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Serialize plugin status to dictionary."""
        return {
            "name": self.manifest.name,
            "version": self.manifest.version,
            "author": self.manifest.author,
            "description": f"{self.manifest.description_fa} | {self.manifest.description_en}",
            "status": self.status.value,
            "tools": self.tools_registered,
            "commands": self.commands_registered,
            "error_message": self.error_message,
            "loaded_at": self.loaded_at.isoformat(),
        }
