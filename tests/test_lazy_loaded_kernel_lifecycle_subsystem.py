"""Comprehensive unit and integration test suite for Lazy-Loaded Kernel Lifecycle."""

from __future__ import annotations

import pytest

from dream.core.engine import DreamKernel
from dream.core.lazy_registry import LazySubsystemProxy
from dream.core.lifecycle import KernelLifecycleManager
from dream.core.slash import handle_kernel_command
from dream.core.tools import (
    get_kernel_tools,
    kernel_get_memory_profile,
    kernel_get_status,
    kernel_list_subsystems,
    kernel_reset,
    kernel_trigger_hot_reload,
    reset_global_dream_kernel,
)
from dream.core.types import (
    KernelState,
    SubsystemDescriptor,
    SubsystemLoadStatus,
)
from dream.tools.toolsets import get_toolset


@pytest.fixture(autouse=True)
def cleanup_kernel() -> None:
    reset_global_dream_kernel()
    yield
    reset_global_dream_kernel()


def test_toolset_includes_kernel() -> None:
    """Verify kernel toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("kernel")
    assert ts is not None
    assert ts.name == "kernel"
    assert "kernel_get_status" in ts.tools
    assert "kernel_trigger_hot_reload" in ts.tools
    assert "kernel_list_subsystems" in ts.tools
    assert "kernel_get_memory_profile" in ts.tools


def test_lazy_subsystem_proxy_deferred_loading() -> None:
    """Test that lazy proxy defers instantiation until first access."""
    instantiated_count = 0

    def mock_factory() -> dict[str, str]:
        nonlocal instantiated_count
        instantiated_count += 1
        return {"service": "mock_active"}

    desc = SubsystemDescriptor(
        name="mock_subsystem",
        display_name_fa="زیرسیستم ماک",
        factory_path="mock.path:factory",
        status=SubsystemLoadStatus.REGISTERED_LAZY,
    )

    proxy = LazySubsystemProxy(descriptor=desc, factory_fn=mock_factory)

    assert proxy.is_loaded is False
    assert instantiated_count == 0
    assert proxy.descriptor.status == SubsystemLoadStatus.REGISTERED_LAZY

    # Access instance
    instance = proxy.get_instance()
    assert proxy.is_loaded is True
    assert instantiated_count == 1
    assert instance["service"] == "mock_active"
    assert proxy.descriptor.status == SubsystemLoadStatus.ACTIVE
    assert proxy.descriptor.total_invocations == 1

    # Subsequent access does not re-instantiate
    proxy.get_instance()
    assert instantiated_count == 1
    assert proxy.descriptor.total_invocations == 2


def test_kernel_lifecycle_transitions_and_hooks() -> None:
    """Test lifecycle state transitions and hook executions."""
    lifecycle = KernelLifecycleManager()

    hook_called = {"start": False, "reload": False, "shutdown": False}

    lifecycle.register_hook("on_start", lambda: hook_called.update({"start": True}))
    lifecycle.register_hook("on_reload", lambda: hook_called.update({"reload": True}))
    lifecycle.register_hook("on_shutdown", lambda: hook_called.update({"shutdown": True}))

    # Boot
    cold_time = lifecycle.boot()
    assert lifecycle.state == KernelState.RUNNING
    assert cold_time >= 0.0
    assert hook_called["start"] is True

    # Pause & Resume
    lifecycle.pause()
    assert lifecycle.state == KernelState.PAUSED
    lifecycle.resume()
    assert lifecycle.state == KernelState.RUNNING

    # Hot reload
    res = lifecycle.hot_reload()
    assert res["success"] is True
    assert hook_called["reload"] is True
    assert lifecycle.state == KernelState.RUNNING

    # Shutdown
    lifecycle.shutdown()
    assert lifecycle.state == KernelState.SHUTDOWN
    assert hook_called["shutdown"] is True


def test_dream_kernel_registry_and_lazy_ratio() -> None:
    """Test master DreamKernel lazy loading ratio and snapshot telemetry."""
    kernel = DreamKernel()

    snap = kernel.get_snapshot()
    assert snap.state == KernelState.RUNNING
    assert snap.total_subsystems_registered >= 10
    assert snap.active_subsystems_loaded == 0  # Zero overhead cold boot!
    assert snap.memory_profile["lazy_ratio_pct"] == 100.0

    # Resolve one lazy subsystem
    vision_engine = kernel.get_subsystem("vision")
    assert vision_engine is not None

    snap_after = kernel.get_snapshot()
    assert snap_after.active_subsystems_loaded == 1
    assert snap_after.subsystems["vision"].status == "active"


def test_kernel_tools_and_slash_commands() -> None:
    """Test LLM tools and slash command dispatcher."""
    tools = get_kernel_tools()
    assert len(tools) >= 4

    # 1. Tool: status
    res_st = kernel_get_status()
    assert res_st["success"] is True
    assert res_st["state"] == "running"

    # 2. Tool: reload
    res_rl = kernel_trigger_hot_reload()
    assert res_rl["success"] is True

    # 3. Tool: list
    res_ls = kernel_list_subsystems()
    assert res_ls["success"] is True
    assert "vision" in res_ls["subsystems"]

    # 4. Tool: profile
    res_pf = kernel_get_memory_profile()
    assert res_pf["success"] is True
    assert "pid" in res_pf["memory_profile"]

    # 5. Slash commands
    s_help = handle_kernel_command("")
    assert "راهنمای دستورات هسته اجرایی" in s_help

    s_status = handle_kernel_command("status")
    assert "وضعیت هسته مرکزی دریم" in s_status

    s_reload = handle_kernel_command("reload")
    assert "بارگذاری مجدد گرم" in s_reload or "Hot-Reload" in s_reload

    s_subs = handle_kernel_command("subsystems")
    assert "زیرسیستم‌های هسته دریم" in s_subs

    s_prof = handle_kernel_command("profile")
    assert "پروفایل عملکردی" in s_prof

    s_res = handle_kernel_command("reset")
    assert "بازنشانی شد" in s_res

    # Tool reset
    t_res = kernel_reset()
    assert t_res["success"] is True
