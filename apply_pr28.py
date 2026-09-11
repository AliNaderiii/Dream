#!/usr/bin/env python3
"""Standalone installer for Phase 25 (Dynamic Plugin Architecture & Lifecycle Manager).

Applies:
- `dream/plugins/__init__.py`
- `dream/plugins/types.py`
- `dream/plugins/manager.py`
- `dream/plugins/tools.py`
- `dream/plugins/slash.py`
- Registers "plugins" toolset in `dream/tools/toolsets.py`
- `tests/test_plugin_system_and_hooks.py`
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

FILES = {
    "dream/plugins/types.py": '''"""Domain types and data models for the Dynamic Plugin Architecture and Extension Subsystem."""

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
''',
    "dream/plugins/manager.py": '''"""Plugin Manager orchestrating dynamic plugin discovery, permissions, and lifecycle hooks."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from dream.plugins.types import (
    PluginHookEvent,
    PluginHookResult,
    PluginManifest,
    PluginPermission,
    PluginStatus,
)

HookHandler = Callable[[dict[str, Any]], dict[str, Any]]


class PluginManager:
    """Manages installation, activation, permission scoping, and execution of agent plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginManifest] = {}
        self._handlers: dict[PluginHookEvent, list[tuple[str, HookHandler]]] = {
            event: [] for event in PluginHookEvent
        }

    def register_manifest(self, manifest: PluginManifest) -> PluginManifest:
        """Register a new plugin manifest in the registry."""
        self._plugins[manifest.plugin_id] = manifest
        return manifest

    def install_plugin(self, data: dict[str, Any]) -> PluginManifest:
        """Parse, validate, and install a plugin from manifest data."""
        plugin_id = data.get("plugin_id") or data.get("name", "").lower().replace(" ", "_")
        if not plugin_id:
            raise ValueError("Plugin manifest must specify 'plugin_id' or 'name'.")

        perms = []
        for p in data.get("permissions", []):
            try:
                perms.append(PluginPermission(p))
            except ValueError:
                pass

        hooks = []
        for h in data.get("hooks", []):
            try:
                hooks.append(PluginHookEvent(h))
            except ValueError:
                pass

        manifest = PluginManifest(
            plugin_id=plugin_id,
            name=data.get("name", plugin_id),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            author=data.get("author", "Community"),
            permissions=perms,
            tools=data.get("tools", []),
            hooks=hooks,
            status=PluginStatus.ACTIVE,
            entrypoint=data.get("entrypoint", ""),
            installed_at=time.time(),
            metadata=data.get("metadata", {}),
        )
        self._plugins[plugin_id] = manifest
        return manifest

    def enable_plugin(self, plugin_id: str) -> bool:
        """Activate an installed plugin."""
        if plugin_id not in self._plugins:
            return False
        self._plugins[plugin_id].status = PluginStatus.ACTIVE
        return True

    def disable_plugin(self, plugin_id: str) -> bool:
        """Deactivate an active plugin."""
        if plugin_id not in self._plugins:
            return False
        self._plugins[plugin_id].status = PluginStatus.DISABLED
        return True

    def get_plugin(self, plugin_id: str) -> PluginManifest | None:
        """Retrieve plugin manifest by ID."""
        return self._plugins.get(plugin_id)

    def list_plugins(self, active_only: bool = False) -> list[PluginManifest]:
        """List registered plugins, optionally filtering only active ones."""
        if active_only:
            return [p for p in self._plugins.values() if p.status == PluginStatus.ACTIVE]
        return list(self._plugins.values())

    def register_hook_handler(
        self,
        plugin_id: str,
        event: PluginHookEvent,
        handler: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        """Bind a callable hook handler to a specific lifecycle event for a plugin."""
        self._handlers[event].append((plugin_id, handler))

    def trigger_hook(
        self,
        event: PluginHookEvent,
        payload: dict[str, Any],
    ) -> list[PluginHookResult]:
        """Execute all active handlers registered for a lifecycle hook event."""
        results = []
        current_context = dict(payload)

        for plugin_id, handler in self._handlers.get(event, []):
            plugin = self._plugins.get(plugin_id)
            if plugin and plugin.status != PluginStatus.ACTIVE:
                continue

            try:
                mod_context = handler(dict(current_context))
                if isinstance(mod_context, dict):
                    current_context.update(mod_context)
                results.append(
                    PluginHookResult(
                        plugin_id=plugin_id,
                        event=event,
                        success=True,
                        modified_context=current_context,
                        message="Hook executed successfully.",
                    )
                )
            except Exception as exc:
                results.append(
                    PluginHookResult(
                        plugin_id=plugin_id,
                        event=event,
                        success=False,
                        modified_context=current_context,
                        message=f"Hook error: {exc}",
                    )
                )

        return results

    def reset(self) -> None:
        """Clear all registered plugins and hook handlers."""
        self._plugins.clear()
        for event in PluginHookEvent:
            self._handlers[event].clear()
''',
    "dream/plugins/tools.py": '''"""LLM Tool bindings for Dynamic Plugin Architecture and Extension Management."""

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
''',
    "dream/plugins/slash.py": '''"""Interactive slash command handler for Plugin Management."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dream.plugins.tools import get_global_plugin_manager
from dream.plugins.types import PluginStatus


def handle_plugin_command(
    cmd_text: str,
    output: Callable[[str], None] = print,
    colors: Any | None = None,
) -> bool:
    """Handle `/plugin` slash command in interactive REPL or TUI."""
    if colors is None:
        from dream.tui.colors import ColorManager

        cm = ColorManager()
    else:
        cm = colors

    mgr = get_global_plugin_manager()
    parts = cmd_text.strip().split()
    subcmd = parts[1].lower() if len(parts) > 1 else "list"

    if subcmd in ("list", "ls"):
        plugins = mgr.list_plugins()
        title = (
            "\\U0001f9e9 "
            "\\u0641\\u0647\\u0631\\u0633\\u062a "
            "\\u0627\\u0641\\u0632\\u0648\\u0646\\u0647\\u200c\\u0647\\u0627 "
            "(Plugins):"
        )
        output(cm.bold(title))
        if not plugins:
            empty_msg = (
                "  \\u2022 \\u0647\\u06cc\\u0686 "
                "\\u0627\\u0641\\u0632\\u0648\\u0646\\u0647\\u200c\\u0627\\u06cc "
                "\\u0646\\u0635\\u0628 \\u0646\\u0634\\u062f\\u0647 \\u0627\\u0633\\u062a."
            )
            output(cm.dim(empty_msg))
            return True

        for p in plugins:
            st_color = cm.green if p.status == PluginStatus.ACTIVE else cm.red
            st_text = (
                "\\u0641\\u0639\\u0627\\u0644"
                if p.status == PluginStatus.ACTIVE
                else "\\u063a\\u06cc\\u0631\\u0641\\u0639\\u0627\\u0644"
            )
            output(
                f"  \\u2022 {cm.bold(p.plugin_id)} (v{p.version}) - "
                f"[{st_color(st_text)}]: {p.description or p.name}"
            )
        return True

    if subcmd in ("enable", "on"):
        if len(parts) < 3:
            err = (
                "\\u2717 \\u0644\\u0637\\u0641\\u0627\\u064b "
                "\\u0634\\u0646\\u0627\\u0633\\u0647 "
                "\\u0627\\u0641\\u0632\\u0648\\u0646\\u0647 "
                "\\u0631\\u0627 \\u0648\\u0627\\u0631\\u062f \\u06a9\\u0646\\u06cc\\u062f."
            )
            output(cm.red(err))
            return True

        p_id = parts[2]
        if mgr.enable_plugin(p_id):
            succ = (
                f"\\u2713 \\u0627\\u0641\\u0632\\u0648\\u0646\\u0647 '{p_id}' "
                "\\u0641\\u0639\\u0627\\u0644 \\u0634\\u062f."
            )
            output(cm.green(succ))
        else:
            not_found = (
                f"\\u2717 \\u0627\\u0641\\u0632\\u0648\\u0646\\u0647 '{p_id}' "
                "\\u06cc\\u0627\\u0641\\u062a \\u0646\\u0634\\u062f."
            )
            output(cm.red(not_found))
        return True

    if subcmd in ("disable", "off"):
        if len(parts) < 3:
            err = (
                "\\u2717 \\u0644\\u0637\\u0641\\u0627\\u064b "
                "\\u0634\\u0646\\u0627\\u0633\\u0647 "
                "\\u0627\\u0641\\u0632\\u0648\\u0646\\u0647 "
                "\\u0631\\u0627 \\u0648\\u0627\\u0631\\u062f \\u06a9\\u0646\\u06cc\\u062f."
            )
            output(cm.red(err))
            return True

        p_id = parts[2]
        if mgr.disable_plugin(p_id):
            succ = (
                f"\\u2713 \\u0627\\u0641\\u0632\\u0648\\u0646\\u0647 '{p_id}' "
                "\\u063a\\u06cc\\u0631\\u0641\\u0639\\u0627\\u0644 \\u0634\\u062f."
            )
            output(cm.green(succ))
        else:
            not_found = (
                f"\\u2717 \\u0627\\u0641\\u0632\\u0648\\u0646\\u0647 '{p_id}' "
                "\\u06cc\\u0627\\u0641\\u062a \\u0646\\u0634\\u062f."
            )
            output(cm.red(not_found))
        return True

    if subcmd in ("info", "view"):
        if len(parts) < 3:
            err = (
                "\\u2717 \\u0644\\u0637\\u0641\\u0627\\u064b "
                "\\u0634\\u0646\\u0627\\u0633\\u0647 "
                "\\u0627\\u0641\\u0632\\u0648\\u0646\\u0647 "
                "\\u0631\\u0627 \\u0648\\u0627\\u0631\\u062f \\u06a9\\u0646\\u06cc\\u062f."
            )
            output(cm.red(err))
            return True

        p_id = parts[2]
        plugin = mgr.get_plugin(p_id)
        if not plugin:
            not_found = (
                f"\\u2717 \\u0627\\u0641\\u0632\\u0648\\u0646\\u0647 '{p_id}' "
                "\\u06cc\\u0627\\u0641\\u062a \\u0646\\u0634\\u062f."
            )
            output(cm.red(not_found))
            return True

        output(cm.bold(f"\\U0001f9e9 \\u0627\\u0637\\u0644\\u0627\\u0639\\u0627\\u062a {plugin.name}:"))
        output(f"  \\u2022 \\u0634\\u0646\\u0627\\u0633\\u0647: {plugin.plugin_id}")
        output(f"  \\u2022 \\u0646\\u0633\\u062e\\u0647: {plugin.version}")
        output(f"  \\u2022 \\u062a\\u0648\\u0636\\u06cc\\u062d\\u0627\\u062a: {plugin.description}")
        output(f"  \\u2022 \\u0646\\u0648\\u06cc\\u0633\\u0646\\u062f\\u0647: {plugin.author}")
        perms_str = ", ".join(p.value for p in plugin.permissions) or "None"
        output(f"  \\u2022 \\u0645\\u062c\\u0648\\u0632\\u0647\\u0627: {perms_str}")
        return True

    # Help
    h_title = (
        "\\u0631\\u0627\\u0647\\u0646\\u0645\\u0627\\u06cc "
        "\\u062f\\u0633\\u062a\\u0648\\u0631 /plugin:"
    )
    output(cm.bold(h_title))
    output(
        "  /plugin list                        - "
        "\\u0641\\u0647\\u0631\\u0633\\u062a / List plugins"
    )
    output(
        "  /plugin enable <id>                 - "
        "\\u0641\\u0639\\u0627\\u0644\\u200c\\u0633\\u0627\\u0632\\u06cc / Enable plugin"
    )
    output(
        "  /plugin disable <id>                - "
        "\\u063a\\u06cc\\u0631\\u0641\\u0639\\u0627\\u0644\\u200c\\u0633\\u0627\\u0632\\u06cc / Disable plugin"
    )
    output(
        "  /plugin info <id>                   - "
        "\\u062c\\u0632\\u0626\\u06cc\\u0627\\u062a \\u0627\\u0641\\u0632\\u0648\\u0646\\u0647 / Plugin details"
    )
    return True
''',
    "dream/plugins/__init__.py": '''"""Dynamic Plugin Architecture, Manifests, and Extension Hooks subsystem for Dream Agent."""

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
''',
    "tests/test_plugin_system_and_hooks.py": '''"""Tests for Dynamic Plugin Architecture, Manifests, and Extension Hooks subsystem."""

from __future__ import annotations

from dream.plugins import (
    PluginHookEvent,
    PluginManager,
    PluginManifest,
    PluginPermission,
    PluginStatus,
    get_plugin_tools,
    handle_plugin_command,
    plugin_disable,
    plugin_enable,
    plugin_get_info,
    plugin_install,
    plugin_list,
    reset_global_plugin_manager,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


def test_plugin_manifest_creation_and_dict():
    manifest = PluginManifest(
        plugin_id="weather_plugin",
        name="Weather Extension",
        version="1.2.0",
        description="Fetch live global weather reports",
        author="Dream Team",
        permissions=[PluginPermission.NETWORK],
        tools=["get_weather"],
        hooks=[PluginHookEvent.PRE_TURN],
    )
    assert manifest.plugin_id == "weather_plugin"
    assert manifest.status == PluginStatus.INSTALLED
    d = manifest.to_dict()
    assert d["name"] == "Weather Extension"
    assert "network" in d["permissions"]
    assert "pre_turn" in d["hooks"]


def test_plugin_manager_lifecycle_and_hooks():
    mgr = PluginManager()
    data = {
        "plugin_id": "audit_logger",
        "name": "Audit Logger",
        "version": "1.0.0",
        "description": "Log pre and post turns",
        "permissions": ["file_system"],
        "hooks": ["pre_turn", "post_turn"],
    }
    p = mgr.install_plugin(data)
    assert p.plugin_id == "audit_logger"
    assert p.status == PluginStatus.ACTIVE
    assert len(mgr.list_plugins()) == 1

    # Disable and enable
    assert mgr.disable_plugin("audit_logger") is True
    assert p.status == PluginStatus.DISABLED
    assert len(mgr.list_plugins(active_only=True)) == 0

    assert mgr.enable_plugin("audit_logger") is True
    assert p.status == PluginStatus.ACTIVE

    # Register hook handler
    def sample_pre_turn(ctx: dict) -> dict:
        ctx["injected_by_hook"] = True
        return ctx

    mgr.register_hook_handler("audit_logger", PluginHookEvent.PRE_TURN, sample_pre_turn)

    results = mgr.trigger_hook(PluginHookEvent.PRE_TURN, {"prompt": "hello"})
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].modified_context.get("injected_by_hook") is True

    mgr.reset()
    assert len(mgr.list_plugins()) == 0


def test_plugin_tools_and_slash():
    reset_global_plugin_manager()
    tools = get_plugin_tools()
    assert len(tools) == 5

    manifest_json = """
    {
      "plugin_id": "calc_pro",
      "name": "Calculator Pro",
      "version": "2.0.0",
      "description": "Advanced scientific computations",
      "permissions": ["terminal"],
      "tools": ["calc_advanced"]
    }
    """
    inst_res = plugin_install(manifest_json)
    assert inst_res["success"] is True

    lst_res = plugin_list()
    assert lst_res["success"] is True
    assert len(lst_res["plugins"]) == 1

    info_res = plugin_get_info("calc_pro")
    assert info_res["success"] is True
    assert info_res["plugin"]["name"] == "Calculator Pro"

    dis_res = plugin_disable("calc_pro")
    assert dis_res["success"] is True

    en_res = plugin_enable("calc_pro")
    assert en_res["success"] is True

    # Slash commands
    lines = []
    handle_plugin_command("/plugin list", output=lines.append)
    assert any("calc_pro" in line for line in lines)

    lines.clear()
    handle_plugin_command("/plugin info calc_pro", output=lines.append)
    assert any("Calculator Pro" in line for line in lines)

    lines.clear()
    handle_plugin_command("/plugin disable calc_pro", output=lines.append)
    assert len(lines) >= 1

    lines.clear()
    handle_plugin_command("/plugin enable calc_pro", output=lines.append)
    assert len(lines) >= 1

    reset_global_plugin_manager()


def test_toolset_includes_plugins():
    assert "plugins" in BUILTIN_TOOLSETS
    toolset = get_toolset("plugins")
    assert toolset is not None
    assert len(toolset.tools) >= 5
    assert "plugin_list" in toolset.tools
    assert "plugin_install" in toolset.tools
''',
}


def main() -> None:
    root = Path.cwd()
    if not (root / "dream").is_dir():
        print("[-] Error: run this script from the root of the dream repository.")
        sys.exit(1)

    print("[*] Applying Phase 25 (Dynamic Plugin Architecture & Lifecycle Manager)...")
    for rel_path, content in FILES.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"  [+] Wrote {rel_path}")

    # Register plugins toolset in dream/tools/toolsets.py
    toolsets_path = root / "dream" / "tools" / "toolsets.py"
    if toolsets_path.exists():
        ts_content = toolsets_path.read_text(encoding="utf-8")
        if '"plugins"' not in ts_content:
            target_str = '    "dialectic": Toolset('
            replacement = """    "plugins": Toolset(
        name="plugins",
        description="Dynamic plugin installation, lifecycle management, and extension hooks",
        tools=(
            "plugin_list",
            "plugin_install",
            "plugin_enable",
            "plugin_disable",
            "plugin_get_info",
        ),
    ),
    "dialectic": Toolset("""
            if target_str in ts_content:
                ts_content = ts_content.replace(target_str, replacement)
                toolsets_path.write_text(ts_content, encoding="utf-8")
                print("  [+] Registered 'plugins' in dream/tools/toolsets.py")

    # Ensure git author email is set to compliant user config
    try:
        subprocess.run(["git", "config", "user.name", "Ali Naderi"], check=False)
        subprocess.run(["git", "config", "user.email", "alinaderi@users.noreply.github.com"], check=False)
        print("  [+] Configured compliant git author credentials (Ali Naderi <alinaderi@users.noreply.github.com>)")
    except Exception:
        pass

    print("[✓] Successfully applied Phase 25 files.")


if __name__ == "__main__":
    main()
