"""Dynamic Plugin Architecture, Manifests, and Extension Hooks subsystem for Dream Agent."""

from __future__ import annotations

from dream.plugins.manager import PluginManager
from dream.plugins.slash import handle_plugin_command
from dream.plugins.tools import (
    get_global_plugin_manager,
    get_plugin_tools,
    plugin_disable,
    plugin_enable,
    plugin_get_info,
    plugin_install,
    plugin_list,
    reset_global_plugin_manager,
)
from dream.plugins.types import (
    PluginHookEvent,
    PluginHookResult,
    PluginManifest,
    PluginPermission,
    PluginStatus,
)

__all__ = [
    "PluginHookEvent",
    "PluginHookResult",
    "PluginManager",
    "PluginManifest",
    "PluginPermission",
    "PluginStatus",
    "get_global_plugin_manager",
    "get_plugin_tools",
    "handle_plugin_command",
    "plugin_disable",
    "plugin_enable",
    "plugin_get_info",
    "plugin_install",
    "plugin_list",
    "reset_global_plugin_manager",
]

try:
    from dream.tools import toolsets

    if hasattr(toolsets, "register_toolset") and "plugins" not in toolsets.BUILTIN_TOOLSETS:
        toolsets.register_toolset(
            "plugins",
            [
                "plugin_list",
                "plugin_install",
                "plugin_enable",
                "plugin_disable",
                "plugin_get_info",
            ],
            description="Dynamic plugin installation, lifecycle management, and extension hooks",
        )
except Exception:
    pass
