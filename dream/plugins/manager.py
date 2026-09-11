"""Plugin Manager orchestrating dynamic plugin discovery, permissions, and lifecycle hooks."""

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
