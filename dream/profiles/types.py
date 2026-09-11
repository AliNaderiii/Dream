"""Data types and configurations for Multi-Profile and Persona Isolation Subsystem."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Profile:
    """Isolated environment profile with its own memory scope, persona, and configuration."""

    name: str
    display_name: str = ""
    persona_prompt: str = ""
    language: str = "fa"
    default_model: str = "gpt-4o"
    allowed_toolsets: list[str] = field(
        default_factory=lambda: ["core", "workspace", "web", "skills"]
    )
    memory_db_path: str = ""
    system_instructions: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize profile configuration to dictionary."""
        return {
            "name": self.name,
            "display_name": self.display_name or self.name,
            "persona_prompt": self.persona_prompt,
            "language": self.language,
            "default_model": self.default_model,
            "allowed_toolsets": self.allowed_toolsets,
            "memory_db_path": self.memory_db_path,
            "system_instructions": self.system_instructions,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Profile:
        """Instantiate profile from dictionary."""
        return cls(
            name=data["name"],
            display_name=data.get("display_name", data["name"]),
            persona_prompt=data.get("persona_prompt", ""),
            language=data.get("language", "fa"),
            default_model=data.get("default_model", "gpt-4o"),
            allowed_toolsets=data.get("allowed_toolsets", ["core", "workspace", "web", "skills"]),
            memory_db_path=data.get("memory_db_path", ""),
            system_instructions=data.get("system_instructions", ""),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )
