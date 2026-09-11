"""Central Plugin Manager orchestrating discovery, dynamic loading, and lifecycle hooks."""

from __future__ import annotations

import importlib.util
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dream.plugins.base import BasePlugin, PluginContext
from dream.plugins.builtin.calendar_calc import CalendarCalcPlugin
from dream.plugins.builtin.currency import CurrencyPlugin
from dream.plugins.builtin.weather import WeatherPlugin
from dream.plugins.types import PluginInfo, PluginStatus

logger = logging.getLogger(__name__)


class PluginManager:
    """Manages plugin discovery, hot-reloading, lifecycle execution, and tool aggregation."""

    def __init__(self, workspace_root: Path | None = None) -> None:
        self.workspace_root = workspace_root or Path.cwd()
        self._lock = threading.RLock()
        self._plugins: dict[str, BasePlugin] = {}
        self._statuses: dict[str, PluginStatus] = {}
        self._error_messages: dict[str, str | None] = {}
        self._context = PluginContext(workspace_root=self.workspace_root)

        # Register standard built-in plugins
        self.register_plugin(WeatherPlugin())
        self.register_plugin(CurrencyPlugin())
        self.register_plugin(CalendarCalcPlugin())

    def register_plugin(self, plugin: BasePlugin, auto_activate: bool = True) -> bool:
        """Register an instantiated plugin into the manager."""
        name = plugin.manifest.name
        with self._lock:
            self._plugins[name] = plugin
            self._statuses[name] = PluginStatus.LOADED
            self._error_messages[name] = None

            if auto_activate and plugin.manifest.enabled_by_default:
                try:
                    success = plugin.on_load(self._context)
                    if success:
                        self._statuses[name] = PluginStatus.ACTIVE
                        logger.info(f"Plugin '{name}' loaded and activated.")
                        return True
                    self._statuses[name] = PluginStatus.ERROR
                    self._error_messages[name] = "on_load returned False"
                    return False
                except Exception as exc:
                    self._statuses[name] = PluginStatus.ERROR
                    self._error_messages[name] = str(exc)
                    logger.error(f"Error initializing plugin '{name}': {exc}", exc_info=True)
                    return False
            return True

    def enable_plugin(self, name: str) -> bool:
        """Activate a registered plugin."""
        with self._lock:
            plugin = self._plugins.get(name)
            if not plugin:
                logger.warning(f"Cannot enable unknown plugin: '{name}'")
                return False

            try:
                ok = plugin.on_load(self._context)
                if ok:
                    self._statuses[name] = PluginStatus.ACTIVE
                    self._error_messages[name] = None
                    return True
                self._statuses[name] = PluginStatus.ERROR
                self._error_messages[name] = "on_load returned False"
                return False
            except Exception as exc:
                self._statuses[name] = PluginStatus.ERROR
                self._error_messages[name] = str(exc)
                return False

    def disable_plugin(self, name: str) -> bool:
        """Deactivate an active plugin."""
        with self._lock:
            plugin = self._plugins.get(name)
            if not plugin:
                return False

            try:
                plugin.on_unload()
                self._statuses[name] = PluginStatus.DISABLED
                return True
            except Exception as exc:
                logger.error(f"Error unloading plugin '{name}': {exc}")
                self._statuses[name] = PluginStatus.ERROR
                self._error_messages[name] = str(exc)
                return False

    def get_plugin(self, name: str) -> BasePlugin | None:
        """Retrieve plugin instance by name."""
        with self._lock:
            return self._plugins.get(name)

    def list_plugins(self) -> list[PluginInfo]:
        """Return diagnostic runtime info for all registered plugins."""
        with self._lock:
            infos = []
            for name, plugin in self._plugins.items():
                status = self._statuses.get(name, PluginStatus.UNLOADED)
                err = self._error_messages.get(name)
                tools_list = [t.get("name", "") for t in plugin.register_tools()]
                commands_list = list(plugin.register_commands().keys())

                infos.append(
                    PluginInfo(
                        manifest=plugin.manifest,
                        status=status,
                        tools_registered=tools_list,
                        commands_registered=commands_list,
                        error_message=err,
                    )
                )
            return infos

    def get_all_tools(self) -> list[dict[str, Any]]:
        """Collect all tools from currently active plugins."""
        with self._lock:
            tools = []
            for name, plugin in self._plugins.items():
                if self._statuses.get(name) == PluginStatus.ACTIVE:
                    try:
                        tools.extend(plugin.register_tools())
                    except Exception as exc:
                        logger.error(f"Error collecting tools from plugin '{name}': {exc}")
            return tools

    def get_all_commands(self) -> dict[str, Callable[[str], Any]]:
        """Collect all slash commands from currently active plugins."""
        with self._lock:
            commands = {}
            for name, plugin in self._plugins.items():
                if self._statuses.get(name) == PluginStatus.ACTIVE:
                    try:
                        commands.update(plugin.register_commands())
                    except Exception as exc:
                        logger.error(f"Error collecting commands from plugin '{name}': {exc}")
            return commands

    def execute_turn_start_hooks(self, user_text: str) -> str:
        """Execute pre-turn interception hooks across active plugins."""
        current_text = user_text
        with self._lock:
            active_plugins = [
                p for name, p in self._plugins.items()
                if self._statuses.get(name) == PluginStatus.ACTIVE
            ]

        for p in active_plugins:
            try:
                modified = p.on_turn_start(current_text)
                if modified is not None:
                    current_text = modified
            except Exception as exc:
                logger.error(f"Error in on_turn_start hook of '{p.manifest.name}': {exc}")
        return current_text

    def execute_turn_end_hooks(self, agent_reply: str) -> str:
        """Execute post-turn interception hooks across active plugins."""
        current_reply = agent_reply
        with self._lock:
            active_plugins = [
                p for name, p in self._plugins.items()
                if self._statuses.get(name) == PluginStatus.ACTIVE
            ]

        for p in active_plugins:
            try:
                modified = p.on_turn_end(current_reply)
                if modified is not None:
                    current_reply = modified
            except Exception as exc:
                logger.error(f"Error in on_turn_end hook of '{p.manifest.name}': {exc}")
        return current_reply

    def discover_and_load(self, custom_dirs: list[Path] | None = None) -> int:
        """Search and load plugin scripts from workspace and user plugin paths."""
        raw_dirs = [
            self.workspace_root / "plugins",
            Path.home() / ".dream" / "plugins",
        ]
        if custom_dirs:
            raw_dirs.extend(custom_dirs)

        search_dirs: list[Path] = []
        seen: set[Path] = set()
        for d in raw_dirs:
            resolved = d.resolve()
            if resolved not in seen:
                seen.add(resolved)
                search_dirs.append(d)

        loaded_count = 0
        for sdir in search_dirs:
            if not sdir.exists() or not sdir.is_dir():
                continue

            for py_file in sdir.glob("*.py"):
                if py_file.name.startswith("__"):
                    continue
                try:
                    plugin_inst = self._load_plugin_from_file(py_file)
                    if plugin_inst:
                        self.register_plugin(plugin_inst)
                        loaded_count += 1
                except Exception as exc:
                    logger.error(f"Failed to load plugin from {py_file}: {exc}")

        return loaded_count

    def _load_plugin_from_file(self, file_path: Path) -> BasePlugin | None:
        """Dynamically load and instantiate a plugin class from a Python file."""
        module_name = f"dream_dynamic_plugin_{file_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        if not spec or not spec.loader:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Look for BasePlugin subclass in module
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BasePlugin)
                and attr is not BasePlugin
            ):
                return attr()
        return None
