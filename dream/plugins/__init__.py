"""Dream Dynamic Plugin and Extension Subsystem."""

from dream.plugins.base import BasePlugin, PluginContext
from dream.plugins.builtin.calendar_calc import CalendarCalcPlugin
from dream.plugins.builtin.currency import CurrencyPlugin
from dream.plugins.builtin.weather import WeatherPlugin
from dream.plugins.manager import PluginManager
from dream.plugins.slash import handle_plugin_command
from dream.plugins.tools import (
    get_plugin_manager,
    plugin_disable,
    plugin_enable,
    plugin_info,
    plugin_list,
    reset_plugin_manager,
)
from dream.plugins.types import (
    PluginInfo,
    PluginManifest,
    PluginStatus,
)

__all__ = [
    "BasePlugin",
    "PluginContext",
    "PluginManager",
    "PluginManifest",
    "PluginInfo",
    "PluginStatus",
    "WeatherPlugin",
    "CurrencyPlugin",
    "CalendarCalcPlugin",
    "get_plugin_manager",
    "reset_plugin_manager",
    "plugin_list",
    "plugin_info",
    "plugin_enable",
    "plugin_disable",
    "handle_plugin_command",
]
