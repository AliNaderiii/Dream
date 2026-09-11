#!/usr/bin/env python3
"""apply_pr21.py - Standalone installer for Phase 18 / PR #21:
Multi-Profile Persona Scoping & Isolated Workspace Subsystem.

This installer creates or updates the following files in the target repository:
  - dream/profiles/__init__.py
  - dream/profiles/types.py
  - dream/profiles/manager.py
  - dream/profiles/tools.py
  - dream/profiles/slash.py
  - dream/tools/toolsets.py
  - tests/test_profiles_and_personas.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROFILES_INIT_PY = r'''"""Multi-Profile & Persona Isolation subsystem for Dream Agent."""

from __future__ import annotations

from dream.profiles.manager import ProfileManager
from dream.profiles.slash import handle_profile_command
from dream.profiles.tools import (
    get_global_profile_manager,
    get_profile_tools,
    profile_create,
    profile_get_current,
    profile_list,
    profile_switch,
    reset_global_profile_manager,
)
from dream.profiles.types import Profile

__all__ = [
    "Profile",
    "ProfileManager",
    "get_global_profile_manager",
    "get_profile_tools",
    "handle_profile_command",
    "profile_create",
    "profile_get_current",
    "profile_list",
    "profile_switch",
    "reset_global_profile_manager",
]

try:
    from dream.tools import toolsets

    if hasattr(toolsets, "register_toolset") and "profiles" not in toolsets.BUILTIN_TOOLSETS:
        toolsets.register_toolset(
            "profiles",
            [
                "profile_list",
                "profile_get_current",
                "profile_switch",
                "profile_create",
            ],
            display_name="Profile Management",
            description="Scoped persona, memory spaces, and isolated profile management",
        )
except Exception:
    pass
'''

PROFILES_TYPES_PY = r'''"""Data types and configurations for Multi-Profile and Persona Isolation Subsystem."""

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
'''

PROFILES_MANAGER_PY = r'''"""Profile manager for creating, switching, and isolating personas and memory spaces."""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

from dream.profiles.types import Profile

DEFAULT_PROFILES_DIR = Path.home() / ".dream" / "profiles"

BUILTIN_PERSONAS = {
    "default": (
        "\u062f\u0633\u062a\u06cc\u0627\u0631 \u0647\u0648\u0634\u0645\u0646\u062f "
        "\u0634\u062e\u0635\u06cc \u062f\u0648\u0632\u0628\u0627\u0646\u0647 "
        "\u062f\u0631\u06cc\u0645"
    ),
    "coding": (
        "\u0645\u0647\u0646\u062f\u0633 \u0627\u0631\u0634\u062f "
        "\u0646\u0631\u0645\u200c\u0627\u0641\u0632\u0627\u0631\u060c "
        "\u0645\u0639\u0645\u0627\u0631 \u0633\u06cc\u0633\u062a\u0645 "
        "\u0648 \u0645\u062a\u062e\u0635\u0635 "
        "\u06a9\u062f\u0646\u0648\u06cc\u0633\u06cc"
    ),
    "research": (
        "\u067e\u0698\u0648\u0647\u0634\u06af\u0631 \u0639\u0644\u0645\u06cc\u060c "
        "\u062a\u062d\u0644\u06cc\u0644\u200c\u06af\u0631 \u062f\u0627\u062f\u0647 "
        "\u0648 \u0645\u062a\u062e\u0635\u0635 \u0627\u0633\u062a\u062e\u0631\u0627\u062c "
        "\u062f\u0627\u0646\u0634"
    ),
    "finance": (
        "\u0645\u0634\u0627\u0648\u0631 \u0645\u0627\u0644\u06cc\u060c "
        "\u062a\u062d\u0644\u06cc\u0644\u200c\u06af\u0631 \u0628\u0627\u0632\u0627\u0631 "
        "\u0648 \u0645\u062d\u0627\u0633\u0628\u0627\u062a "
        "\u0627\u0642\u062a\u0635\u0627\u062f\u06cc"
    ),
}


class ProfileManager:
    """Manages isolated personas, scoped settings, and storage spaces."""

    def __init__(self, root_dir: Path | str | None = None) -> None:
        self.root_dir = Path(root_dir) if root_dir else DEFAULT_PROFILES_DIR
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.root_dir / "profiles_config.json"
        self._ensure_default_profile()

    def _load_config(self) -> dict[str, Any]:
        """Load global profiles configuration state."""
        if not self.config_path.exists():
            return {"active_profile": "default"}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return {"active_profile": "default"}

    def _save_config(self, config: dict[str, Any]) -> None:
        """Persist global profiles configuration state."""
        self.config_path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _sanitize_name(self, name: str) -> str:
        """Normalize profile name to safe alphanumeric slug."""
        clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", name.strip().lower())
        return clean or "unnamed"

    def _profile_dir(self, name: str) -> Path:
        return self.root_dir / self._sanitize_name(name)

    def _profile_file(self, name: str) -> Path:
        return self._profile_dir(name) / "profile.json"

    def _ensure_default_profile(self) -> None:
        """Ensure initial default profile exists."""
        def_file = self._profile_file("default")
        if not def_file.exists():
            p_dir = self._profile_dir("default")
            p_dir.mkdir(parents=True, exist_ok=True)
            prof = Profile(
                name="default",
                display_name="Default Workspace",
                persona_prompt=BUILTIN_PERSONAS["default"],
                language="fa",
                default_model="gpt-4o",
                allowed_toolsets=[
                    "core",
                    "workspace",
                    "web",
                    "skills",
                    "scheduler",
                    "retrieval",
                    "distill",
                ],
                memory_db_path=str(p_dir / "memory.db"),
            )
            def_file.write_text(
                json.dumps(prof.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._save_config({"active_profile": "default"})

    def create_profile(
        self,
        name: str,
        display_name: str = "",
        persona_prompt: str = "",
        language: str = "fa",
        default_model: str = "gpt-4o",
        allowed_toolsets: list[str] | None = None,
        system_instructions: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Profile:
        """Create and register a new isolated profile."""
        slug = self._sanitize_name(name)
        p_dir = self._profile_dir(slug)
        p_dir.mkdir(parents=True, exist_ok=True)

        persona = persona_prompt or BUILTIN_PERSONAS.get(slug, BUILTIN_PERSONAS["default"])
        toolsets = allowed_toolsets or [
            "core",
            "workspace",
            "web",
            "skills",
            "scheduler",
            "retrieval",
            "distill",
        ]

        prof = Profile(
            name=slug,
            display_name=display_name or name,
            persona_prompt=persona,
            language=language,
            default_model=default_model,
            allowed_toolsets=toolsets,
            memory_db_path=str(p_dir / "memory.db"),
            system_instructions=system_instructions,
            metadata=metadata or {},
            created_at=time.time(),
            updated_at=time.time(),
        )

        file_p = self._profile_file(slug)
        file_p.write_text(
            json.dumps(prof.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return prof

    def get_profile(self, name: str) -> Profile | None:
        """Retrieve profile by name."""
        slug = self._sanitize_name(name)
        file_p = self._profile_file(slug)
        if not file_p.exists():
            return None
        try:
            data = json.loads(file_p.read_text(encoding="utf-8"))
            return Profile.from_dict(data)
        except Exception:
            return None

    def list_profiles(self) -> list[Profile]:
        """List all registered profiles."""
        profiles = []
        for d in sorted(self.root_dir.iterdir()):
            if d.is_dir():
                prof_file = d / "profile.json"
                if prof_file.exists():
                    try:
                        data = json.loads(prof_file.read_text(encoding="utf-8"))
                        profiles.append(Profile.from_dict(data))
                    except Exception:
                        pass
        return profiles

    def get_active_profile(self) -> Profile:
        """Return currently active profile (falls back to default)."""
        cfg = self._load_config()
        active_name = cfg.get("active_profile", "default")
        prof = self.get_profile(active_name)
        if prof:
            return prof
        return self.get_profile("default") or self.create_profile("default")

    def switch_profile(self, name: str) -> Profile:
        """Switch current active profile."""
        slug = self._sanitize_name(name)
        prof = self.get_profile(slug)
        if not prof:
            prof = self.create_profile(slug)
        self._save_config({"active_profile": slug})
        return prof

    def delete_profile(self, name: str) -> bool:
        """Delete profile directory (refuses to delete default or active profile)."""
        slug = self._sanitize_name(name)
        if slug == "default":
            return False
        cfg = self._load_config()
        if cfg.get("active_profile") == slug:
            return False

        p_dir = self._profile_dir(slug)
        if p_dir.exists():
            shutil.rmtree(p_dir, ignore_errors=True)
            return True
        return False

    def export_profile(self, name: str, output_path: Path | str) -> bool:
        """Export profile metadata and memory configuration to a JSON file."""
        prof = self.get_profile(name)
        if not prof:
            return False
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(
            json.dumps(prof.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True

    def import_profile(self, source_path: Path | str) -> Profile | None:
        """Import profile definition from a JSON file."""
        src = Path(source_path)
        if not src.exists():
            return None
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
            prof = Profile.from_dict(data)
            return self.create_profile(
                name=prof.name,
                display_name=prof.display_name,
                persona_prompt=prof.persona_prompt,
                language=prof.language,
                default_model=prof.default_model,
                allowed_toolsets=prof.allowed_toolsets,
                system_instructions=prof.system_instructions,
                metadata=prof.metadata,
            )
        except Exception:
            return None
'''

PROFILES_TOOLS_PY = r'''"""LLM Tool bindings for isolated profile inspection and persona switching."""

from __future__ import annotations

from typing import Any

from dream.profiles.manager import ProfileManager

_GLOBAL_PROFILE_MANAGER: ProfileManager | None = None


def get_global_profile_manager() -> ProfileManager:
    """Get or create singleton ProfileManager."""
    global _GLOBAL_PROFILE_MANAGER
    if _GLOBAL_PROFILE_MANAGER is None:
        _GLOBAL_PROFILE_MANAGER = ProfileManager()
    return _GLOBAL_PROFILE_MANAGER


def reset_global_profile_manager() -> None:
    """Reset singleton for testing."""
    global _GLOBAL_PROFILE_MANAGER
    _GLOBAL_PROFILE_MANAGER = None


def profile_list() -> list[dict[str, Any]]:
    """List all available workspaces and persona profiles."""
    mgr = get_global_profile_manager()
    active = mgr.get_active_profile()
    result = []
    for p in mgr.list_profiles():
        data = p.to_dict()
        data["is_active"] = p.name == active.name
        result.append(data)
    return result


def profile_get_current() -> dict[str, Any]:
    """Retrieve details of currently active workspace and persona profile."""
    mgr = get_global_profile_manager()
    p = mgr.get_active_profile()
    data = p.to_dict()
    data["is_active"] = True
    return data


def profile_switch(name: str) -> dict[str, Any]:
    """Switch active persona profile and isolated memory database."""
    mgr = get_global_profile_manager()
    p = mgr.switch_profile(name)
    data = p.to_dict()
    data["is_active"] = True
    return data


def profile_create(
    name: str,
    display_name: str = "",
    persona_prompt: str = "",
    language: str = "fa",
    default_model: str = "gpt-4o",
) -> dict[str, Any]:
    """Create a new persona profile with isolated memory workspace."""
    mgr = get_global_profile_manager()
    p = mgr.create_profile(
        name=name,
        display_name=display_name,
        persona_prompt=persona_prompt,
        language=language,
        default_model=default_model,
    )
    return p.to_dict()


def get_profile_tools() -> list[Any]:
    """Return list of profile management tool functions for agent binding."""
    return [
        profile_list,
        profile_get_current,
        profile_switch,
        profile_create,
    ]
'''

PROFILES_SLASH_PY = r'''"""Interactive slash command handler for Multi-Profile and Persona management."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.profiles.tools import get_global_profile_manager


def handle_profile_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/profile` slash command in interactive REPL or TUI."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors

    mgr = get_global_profile_manager()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "list"

    if subcmd in ("list", "ls"):
        profiles = mgr.list_profiles()
        active = mgr.get_active_profile()
        title = (
            "\U0001f464 "
            "\u067e\u0631\u0648\u0641\u0627\u06cc\u0644\u200c\u0647\u0627\u06cc "
            "\u0641\u0639\u0627\u0644 "
            f"({len(profiles)} \u0645\u0648\u0631\u062f):"
        )
        output(cm.bold(title))
        for p in profiles:
            is_active = p.name == active.name
            marker = cm.green("\u2713 ") if is_active else "  "
            active_badge = cm.green(" [\u0641\u0639\u0627\u0644]") if is_active else ""
            disp = p.display_name or p.name
            output(f"{marker}\u2022 {cm.cyan(p.name):<12} ({disp}){active_badge}")
            if p.persona_prompt:
                preview = (
                    p.persona_prompt[:50] + "..."
                    if len(p.persona_prompt) > 50
                    else p.persona_prompt
                )
                output(f"    {cm.dim(preview)}")
        return True

    if subcmd in ("switch", "use", "set"):
        if len(parts) < 3:
            msg = (
                "\u2717 \u0644\u0637\u0641\u0627\u064b "
                "\u0646\u0627\u0645 "
                "\u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
                "\u0631\u0627 "
                "\u0645\u0634\u062e\u0635 "
                "\u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(msg))
            return True
        target_name = parts[2]
        prof = mgr.switch_profile(target_name)
        succ = (
            f"\u2713 \u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
            f"\u0641\u0639\u0627\u0644 \u0628\u0647 '{prof.name}' "
            f"({prof.display_name}) "
            "\u062a\u063a\u06cc\u06cc\u0631 "
            "\u06cc\u0627\u0641\u062a."
        )
        output(cm.green(succ))
        return True

    if subcmd in ("info", "current", "show"):
        active = mgr.get_active_profile()
        info_title = (
            "\U0001f464 "
            "\u0627\u0637\u0644\u0627\u0639\u0627\u062a "
            "\u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
            f"\u0641\u0639\u0627\u0644 ({active.name}):"
        )
        output(cm.bold(info_title))
        disp_name = cm.cyan(active.display_name)
        output(f"  \u2022 \u0646\u0627\u0645 \u0646\u0645\u0627\u06cc\u0634\u06cc: {disp_name}")
        model_lbl = "\u0645\u062f\u0644 \u067e\u06cc\u0634\u200c\u0641\u0631\u0636"
        output(f"  \u2022 {model_lbl}: {active.default_model}")
        output(f"  \u2022 \u0632\u0628\u0627\u0646: {active.language}")
        output(f"  \u2022 \u067e\u0631\u0633\u0648\u0646\u0627: {cm.dim(active.persona_prompt)}")
        toolsets_str = ", ".join(active.allowed_toolsets)
        output(
            f"  \u2022 \u0627\u0628\u0632\u0627\u0631\u0647\u0627\u06cc "
            f"\u0645\u062c\u0627\u0632: {toolsets_str}"
        )
        return True

    if subcmd == "create":
        if len(parts) < 3:
            msg = (
                "\u2717 \u0646\u0627\u0645 "
                "\u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
                "\u0644\u0627\u0632\u0645 \u0627\u0633\u062a. "
                "\u0645\u062b\u0627\u0644: /profile create coding"
            )
            output(cm.red(msg))
            return True
        name = parts[2]
        persona = " ".join(parts[3:]) if len(parts) > 3 else ""
        prof = mgr.create_profile(name=name, persona_prompt=persona)
        created_msg = (
            f"\u2713 \u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
            f"'{prof.name}' "
            "\u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a "
            "\u0627\u06cc\u062c\u0627\u062f "
            "\u0634\u062f."
        )
        output(cm.green(created_msg))
        return True

    if subcmd in ("delete", "rm"):
        if len(parts) < 3:
            msg = (
                "\u2717 \u0646\u0627\u0645 "
                "\u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
                "\u0631\u0627 \u0648\u0627\u0631\u062f "
                "\u06a9\u0646\u06cc\u062f."
            )
            output(cm.red(msg))
            return True
        target_name = parts[2]
        if mgr.delete_profile(target_name):
            succ_del = (
                f"\u2713 \u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
                f"'{target_name}' \u062d\u0630\u0641 \u0634\u062f."
            )
            output(cm.green(succ_del))
        else:
            del_err = (
                f"\u2717 \u062d\u0630\u0641 "
                f"\u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
                f"'{target_name}' "
                "\u0627\u0645\u06a9\u0627\u0646\u200c\u067e\u0630\u06cc\u0631 "
                "\u0646\u06cc\u0633\u062a "
                "(\u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
                "\u067e\u06cc\u0634\u200c\u0641\u0631\u0636 "
                "\u06cc\u0627 \u0641\u0639\u0627\u0644 "
                "\u0642\u0627\u0628\u0644 "
                "\u062d\u0630\u0641 "
                "\u0646\u06cc\u0633\u062a)."
            )
            output(cm.red(del_err))
        return True

    # Help
    help_title = (
        "\u0631\u0627\u0647\u0646\u0645\u0627\u06cc "
        "\u062f\u0633\u062a\u0648\u0631 /profile:"
    )
    output(cm.bold(help_title))
    output(
        "  /profile list                       - "
        "\u0646\u0645\u0627\u06cc\u0634 \u0641\u0647\u0631\u0633\u062a "
        "\u067e\u0631\u0648\u0641\u0627\u06cc\u0644\u200c\u0647\u0627 / List profiles"
    )
    output(
        "  /profile switch <name>              - "
        "\u062a\u063a\u06cc\u06cc\u0631 \u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
        "\u0641\u0639\u0627\u0644 / Switch profile"
    )
    output(
        "  /profile create <name> [persona]    - "
        "\u0627\u06cc\u062c\u0627\u062f \u067e\u0631\u0648\u0641\u0627\u06cc\u0644 "
        "\u062c\u062f\u06cc\u062f / Create profile"
    )
    output(
        "  /profile info                       - "
        "\u0646\u0645\u0627\u06cc\u0634 \u062c\u0632\u0626\u06cc\u0627\u062a "
        "\u067e\u0631\u0648\u0641\u0627\u06cc\u0644 \u0641\u0639\u0627\u0644 / Profile details"
    )
    output(
        "  /profile delete <name>              - "
        "\u062d\u0630\u0641 \u067e\u0631\u0648\u0641\u0627\u06cc\u0644 / Delete profile"
    )
    return True
'''

TESTS_PROFILES_PY = r'''"""Tests for Multi-Profile & Persona Isolation subsystem."""

import tempfile
from pathlib import Path

from dream.profiles import (
    ProfileManager,
    get_profile_tools,
    handle_profile_command,
    profile_create,
    profile_get_current,
    profile_list,
    profile_switch,
    reset_global_profile_manager,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


def test_profile_manager_defaults():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = ProfileManager(root_dir=tmpdir)
        active = mgr.get_active_profile()
        assert active.name == "default"
        assert "default" in [p.name for p in mgr.list_profiles()]


def test_profile_create_and_switch():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = ProfileManager(root_dir=tmpdir)
        prof = mgr.create_profile(
            name="coding_expert",
            display_name="Senior Architect",
            persona_prompt="Write high quality Python code",
            default_model="claude-3-5-sonnet",
        )
        assert prof.name == "coding_expert"
        assert prof.display_name == "Senior Architect"

        mgr.switch_profile("coding_expert")
        active = mgr.get_active_profile()
        assert active.name == "coding_expert"
        assert active.persona_prompt == "Write high quality Python code"


def test_profile_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr1 = ProfileManager(root_dir=tmpdir)
        mgr1.create_profile("researcher", display_name="AI Scientist")
        mgr1.switch_profile("researcher")

        mgr2 = ProfileManager(root_dir=tmpdir)
        active = mgr2.get_active_profile()
        assert active.name == "researcher"
        assert active.display_name == "AI Scientist"


def test_profile_deletion_safety():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = ProfileManager(root_dir=tmpdir)
        mgr.create_profile("temp_p")

        # Cannot delete default
        assert mgr.delete_profile("default") is False

        # Cannot delete currently active
        mgr.switch_profile("temp_p")
        assert mgr.delete_profile("temp_p") is False

        # Switch away and then delete
        mgr.switch_profile("default")
        assert mgr.delete_profile("temp_p") is True
        assert mgr.get_profile("temp_p") is None


def test_profile_export_and_import():
    with tempfile.TemporaryDirectory() as tmpdir:
        p_dir = Path(tmpdir) / "profiles"
        mgr = ProfileManager(root_dir=p_dir)
        mgr.create_profile(
            "finance_bot",
            display_name="Financial Analyst",
            persona_prompt="Analyze markets",
        )

        export_path = Path(tmpdir) / "finance.json"
        assert mgr.export_profile("finance_bot", export_path) is True
        assert export_path.exists()

        p_dir2 = Path(tmpdir) / "profiles2"
        mgr2 = ProfileManager(root_dir=p_dir2)
        imported = mgr2.import_profile(export_path)
        assert imported is not None
        assert imported.name == "finance_bot"
        assert imported.display_name == "Financial Analyst"


def test_profile_tools_and_slash():
    reset_global_profile_manager()
    tools = get_profile_tools()
    assert len(tools) == 4

    p_created = profile_create("test_persona", persona_prompt="Test Prompt")
    assert p_created["name"] == "test_persona"

    p_switched = profile_switch("test_persona")
    assert p_switched["name"] == "test_persona"
    assert p_switched["is_active"] is True

    curr = profile_get_current()
    assert curr["name"] == "test_persona"

    all_profs = profile_list()
    assert any(p["name"] == "test_persona" for p in all_profs)

    # Slash command tests
    lines = []
    handle_profile_command("/profile list", output=lines.append)
    assert any("test_persona" in line for line in lines)

    lines.clear()
    handle_profile_command("/profile info", output=lines.append)
    assert any("test_persona" in line for line in lines)

    reset_global_profile_manager()


def test_toolset_includes_profiles():
    assert "profiles" in BUILTIN_TOOLSETS
    toolset = get_toolset("profiles")
    assert toolset is not None
    assert len(toolset.tools) >= 4
    assert "profile_list" in toolset.tools
    assert "profile_switch" in toolset.tools
'''


def main() -> None:
    repo_dir = Path(__file__).resolve().parent / "dream-repo"
    if not repo_dir.exists():
        repo_dir = Path.cwd()

    print(f"Applying Phase 18 (PR #21) changes to repo at: {repo_dir}")

    profiles_dir = repo_dir / "dream" / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)

    (profiles_dir / "__init__.py").write_text(PROFILES_INIT_PY, encoding="utf-8")
    print("  ✓ Created dream/profiles/__init__.py")

    (profiles_dir / "types.py").write_text(PROFILES_TYPES_PY, encoding="utf-8")
    print("  ✓ Created dream/profiles/types.py")

    (profiles_dir / "manager.py").write_text(PROFILES_MANAGER_PY, encoding="utf-8")
    print("  ✓ Created dream/profiles/manager.py")

    (profiles_dir / "tools.py").write_text(PROFILES_TOOLS_PY, encoding="utf-8")
    print("  ✓ Created dream/profiles/tools.py")

    (profiles_dir / "slash.py").write_text(PROFILES_SLASH_PY, encoding="utf-8")
    print("  ✓ Created dream/profiles/slash.py")

    # Update dream/tools/toolsets.py if needed
    toolsets_py = repo_dir / "dream" / "tools" / "toolsets.py"
    if toolsets_py.exists():
        content = toolsets_py.read_text(encoding="utf-8")
        if '"profiles":' not in content:
            new_entry = (
                '    "profiles": [\n'
                '        "profile_list",\n'
                '        "profile_get_current",\n'
                '        "profile_switch",\n'
                '        "profile_create",\n'
                '    ],\n'
            )
            content = content.replace(
                '    "distill": [\n',
                new_entry + '    "distill": [\n',
            )
            toolsets_py.write_text(content, encoding="utf-8")
            print("  ✓ Updated dream/tools/toolsets.py with 'profiles' toolset")

    tests_dir = repo_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_profiles_and_personas.py").write_text(TESTS_PROFILES_PY, encoding="utf-8")
    print("  ✓ Created tests/test_profiles_and_personas.py")

    print("\nPhase 18 (PR #21) application complete! Run pytest to verify:")
    print("  pytest tests/test_profiles_and_personas.py")


if __name__ == "__main__":
    main()
