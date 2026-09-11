"""Comprehensive test suite for the Dream Dynamic Plugin Subsystem."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from dream.plugins.base import BasePlugin
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
from dream.plugins.types import PluginManifest, PluginStatus


class SampleEchoPlugin(BasePlugin):
    """Test plugin that registers a tool and modifies turn input/output."""

    def __init__(self) -> None:
        manifest = PluginManifest(
            name="echo_test_plugin",
            version="0.1.0",
            author="Tester",
            description_en="Test echo plugin",
            description_fa="پلاگین تست اکو",
        )
        super().__init__(manifest)

    def register_tools(self) -> list[dict]:
        return [
            {
                "name": "sample_echo",
                "description": "Echoes back input",
                "handler": lambda text: f"echoed:{text}",
            }
        ]

    def register_commands(self) -> dict:
        return {
            "echo_cmd": lambda args: f"cmd_out:{args}",
        }

    def on_turn_start(self, user_text: str) -> str | None:
        return f"[PROCESSED] {user_text}"

    def on_turn_end(self, agent_reply: str) -> str | None:
        return f"{agent_reply} [ECHO_STAMP]"


def test_plugin_manifest_and_info_serialization():
    """Verify manifest and plugin info serialization to dictionary."""
    manifest = PluginManifest(
        name="test_plugin",
        version="1.0.0",
        author="Ali",
        description_en="A test plugin",
        description_fa="پلاگین تستی",
    )
    d = manifest.to_dict()
    assert d["name"] == "test_plugin"
    assert d["version"] == "1.0.0"
    assert d["author"] == "Ali"


def test_plugin_manager_lifecycle_and_hooks(tmp_path):
    """Verify plugin registration, turn hooks execution, and tool aggregation."""
    mgr = PluginManager(workspace_root=tmp_path)
    plugin = SampleEchoPlugin()
    ok = mgr.register_plugin(plugin)
    assert ok is True

    # Check active status
    status = mgr._statuses.get("echo_test_plugin")
    assert status == PluginStatus.ACTIVE

    # Test tool collection
    tools = mgr.get_all_tools()
    tool_names = [t.get("name") for t in tools]
    assert "sample_echo" in tool_names

    # Test command collection
    commands = mgr.get_all_commands()
    assert "echo_cmd" in commands
    assert commands["echo_cmd"]("hello") == "cmd_out:hello"

    # Test turn hooks
    inp = mgr.execute_turn_start_hooks("Salam")
    assert inp == "[PROCESSED] Salam"

    out = mgr.execute_turn_end_hooks("Reply text")
    assert out == "Reply text [ECHO_STAMP]"

    # Disable plugin
    disabled = mgr.disable_plugin("echo_test_plugin")
    assert disabled is True
    assert mgr._statuses["echo_test_plugin"] == PluginStatus.DISABLED

    # Ensure disabled plugin tools are not collected
    tools_after = mgr.get_all_tools()
    assert "sample_echo" not in [t.get("name") for t in tools_after]

    # Re-enable
    enabled = mgr.enable_plugin("echo_test_plugin")
    assert enabled is True
    assert mgr._statuses["echo_test_plugin"] == PluginStatus.ACTIVE


def test_builtin_weather_plugin():
    """Verify built-in WeatherPlugin execution and Iranian city geocoding."""
    weather = WeatherPlugin()
    assert weather.manifest.name == "weather_plugin"

    # Test Tehran weather lookup
    mock_payload = {
        "current_weather": {
            "temperature": 26.5,
            "windspeed": 14.0,
            "time": "2026-09-11T12:00",
        }
    }
    with patch("urllib.request.urlopen") as mock_open:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_open.return_value.__enter__.return_value = mock_resp

        res_json = weather.get_weather("تهران")
        data = json.loads(res_json)
        assert data["city"] == "تهران"
        assert data["temperature_celsius"] == 26.5
        assert "تهران" in data["summary_fa"]


def test_builtin_currency_plugin():
    """Verify built-in CurrencyPlugin financial conversions."""
    currency = CurrencyPlugin()
    assert currency.manifest.name == "currency_plugin"

    # Convert 100 USD to Toman
    res_json = currency.convert_currency(100.0, "USD", "Toman")
    data = json.loads(res_json)
    assert data["amount"] == 100.0
    assert data["converted_amount"] == 6_000_000.0
    assert "Toman" in data["summary_fa"] or "تومان" in data["summary_fa"]

    # Convert Toman to USD
    res_json2 = currency.convert_currency(60_000.0, "تومان", "دلار")
    data2 = json.loads(res_json2)
    assert data2["converted_amount"] == 1.0


def test_builtin_calendar_calc_plugin():
    """Verify built-in CalendarCalcPlugin Jalali date arithmetic."""
    calc = CalendarCalcPlugin()
    assert calc.manifest.name == "calendar_calc_plugin"

    # Add 10 days to 1403/06/20 -> 1403/06/30 (Shahrivar has 31 days)
    res_json = calc.calculate_jalali_date("1403/06/20", 10)
    data = json.loads(res_json)
    assert data["result_date"] == "1403/06/30"

    # Add 15 days to 1403/06/20 -> 1403/07/04 (rolls over into Mehr)
    res_json2 = calc.calculate_jalali_date("1403/06/20", 15)
    data2 = json.loads(res_json2)
    assert data2["result_date"] == "1403/07/04"


def test_dynamic_plugin_file_discovery(tmp_path):
    """Verify PluginManager loads external plugin Python files."""
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    plugin_code = """
from dream.plugins.base import BasePlugin
from dream.plugins.types import PluginManifest

class DynamicExtPlugin(BasePlugin):
    def __init__(self):
        manifest = PluginManifest(
            name="dynamic_ext",
            version="1.0.0",
            author="Dynamic",
            description_en="Dynamic plugin",
            description_fa="پلاگین داینامیک",
        )
        super().__init__(manifest)

    def register_tools(self):
        return [{"name": "dynamic_tool", "description": "tool"}]
"""
    (plugins_dir / "my_plugin.py").write_text(plugin_code, encoding="utf-8")

    mgr = PluginManager(workspace_root=tmp_path)
    count = mgr.discover_and_load([plugins_dir])
    assert count == 1
    assert "dynamic_ext" in [p.manifest.name for p in mgr.list_plugins()]


def test_plugin_tools_and_slash_commands():
    """Verify tool wrappers and slash command handling."""
    reset_plugin_manager()
    _ = get_plugin_manager()

    # Tool: plugin_list
    list_json = plugin_list()
    data = json.loads(list_json)
    assert "plugins" in data
    assert len(data["plugins"]) >= 3  # Builtins present

    # Tool: plugin_info
    info_json = plugin_info("weather_plugin")
    info_data = json.loads(info_json)
    assert info_data["name"] == "weather_plugin"

    # Tool: disable and enable
    dis_res = plugin_disable("currency_plugin")
    assert "غیرفعال شد" in dis_res
    en_res = plugin_enable("currency_plugin")
    assert "فعال شد" in en_res

    # Slash command /plugins
    outputs = []
    handle_plugin_command("", output=outputs.append)
    assert any("پلاگین‌های نصب‌شده" in line for line in outputs)

    # Slash command /plugin disable
    outputs.clear()
    handle_plugin_command("disable weather_plugin", output=outputs.append)
    assert any("غیرفعال شد" in line for line in outputs)
