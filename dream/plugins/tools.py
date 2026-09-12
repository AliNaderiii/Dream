"""LLM Tool bindings for Dynamic Plugin Architecture and Extension Management."""

from __future__ import annotations

import json
from typing import Any

from dream.plugins.manager import PluginManager

_GLOBAL_PLUGIN_MANAGER: PluginManager | None = None


def get_global_plugin_manager() -> PluginManager:
    """Get or create singleton PluginManager."""
    global _GLOBAL_PLUGIN_MANAGER
    if _GLOBAL_PLUGIN_MANAGER is None:
        _GLOBAL_PLUGIN_MANAGER = PluginManager()
    return _GLOBAL_PLUGIN_MANAGER


def reset_global_plugin_manager() -> None:
    """Reset singleton PluginManager instance for testing."""
    global _GLOBAL_PLUGIN_MANAGER
    _GLOBAL_PLUGIN_MANAGER = None


def plugin_list(active_only: bool = False) -> dict[str, Any]:
    """List all installed plugins and extensions in the Dream runtime."""
    mgr = get_global_plugin_manager()
    plugins = mgr.list_plugins(active_only=active_only)
    return {"success": True, "plugins": [p.to_dict() for p in plugins]}


def plugin_install(manifest_json: str) -> dict[str, Any]:
    """Install and register a new plugin from a JSON manifest string."""
    mgr = get_global_plugin_manager()
    try:
        data = json.loads(manifest_json)
        manifest = mgr.install_plugin(data)
        return {"success": True, "plugin": manifest.to_dict()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def plugin_enable(plugin_id: str) -> dict[str, Any]:
    """Enable an installed plugin by its unique identifier."""
    mgr = get_global_plugin_manager()
    success = mgr.enable_plugin(plugin_id)
    return {"success": success, "plugin_id": plugin_id}


def plugin_disable(plugin_id: str) -> dict[str, Any]:
    """Disable an active plugin by its unique identifier."""
    mgr = get_global_plugin_manager()
    success = mgr.disable_plugin(plugin_id)
    return {"success": success, "plugin_id": plugin_id}


def plugin_get_info(plugin_id: str) -> dict[str, Any]:
    """Retrieve detailed manifest metadata, permissions, and tools for a plugin."""
    mgr = get_global_plugin_manager()
    plugin = mgr.get_plugin(plugin_id)
    if plugin:
        return {"success": True, "plugin": plugin.to_dict()}
    return {"success": False, "error": f"Plugin '{plugin_id}' not found."}


def get_plugin_tools() -> list[Any]:
    """Return list of plugin management tool functions for agent registration."""
    return [
        plugin_list,
        plugin_install,
        plugin_enable,
        plugin_disable,
        plugin_get_info,
    ]


# Backward-compatibility aliases
get_plugin_manager = get_global_plugin_manager
reset_plugin_manager = reset_global_plugin_manager
plugin_info = plugin_get_info
