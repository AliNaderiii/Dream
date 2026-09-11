"""Multi-Profile & Persona Isolation subsystem for Dream Agent."""

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
