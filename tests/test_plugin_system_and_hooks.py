"""Tests for Dynamic Plugin Architecture, Manifests, and Extension Hooks subsystem."""

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
