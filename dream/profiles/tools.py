"""LLM Tool bindings for isolated profile inspection and persona switching."""

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
