"""Agent tool definitions for Plugin discovery and management."""

from __future__ import annotations

import json

from dream.plugins.manager import PluginManager

_GLOBAL_PLUGIN_MANAGER: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    """Retrieve or initialize singleton PluginManager."""
    global _GLOBAL_PLUGIN_MANAGER
    if _GLOBAL_PLUGIN_MANAGER is None:
        _GLOBAL_PLUGIN_MANAGER = PluginManager()
    return _GLOBAL_PLUGIN_MANAGER


def reset_plugin_manager() -> None:
    """Reset global PluginManager instance for isolated testing."""
    global _GLOBAL_PLUGIN_MANAGER
    _GLOBAL_PLUGIN_MANAGER = None


def plugin_list() -> str:
    """List all registered community and builtin plugins with their status."""
    mgr = get_plugin_manager()
    plugins = [p.to_dict() for p in mgr.list_plugins()]
    return json.dumps({"plugins": plugins}, ensure_ascii=False, indent=2)


def plugin_info(name: str) -> str:
    """Get detailed information, tools, and commands for a specific plugin."""
    mgr = get_plugin_manager()
    plugin = mgr.get_plugin(name)
    if not plugin:
        return json.dumps({"error": f"پلاگین با نام '{name}' یافت نشد. / Plugin not found."})

    infos = [p for p in mgr.list_plugins() if p.manifest.name == name]
    if infos:
        return json.dumps(infos[0].to_dict(), ensure_ascii=False, indent=2)
    return json.dumps({"error": "اطلاعات پلاگین در دسترس نیست."})


def plugin_enable(name: str) -> str:
    """Enable and activate a registered plugin."""
    mgr = get_plugin_manager()
    ok = mgr.enable_plugin(name)
    if ok:
        return f"پلاگین '{name}' با موفقیت فعال شد. / Plugin '{name}' enabled successfully."
    return f"خطا در فعال‌سازی پلاگین '{name}'. / Failed to enable plugin '{name}'."


def plugin_disable(name: str) -> str:
    """Disable and deactivate a registered plugin."""
    mgr = get_plugin_manager()
    ok = mgr.disable_plugin(name)
    if ok:
        return f"پلاگین '{name}' غیرفعال شد. / Plugin '{name}' disabled."
    return f"خطا در غیرفعال‌سازی پلاگین '{name}'."
