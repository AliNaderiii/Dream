"""LLM Agent Tools and Toolset Definitions for Dream Kernel Lifecycle."""

from __future__ import annotations

import logging
from typing import Any

from dream.core.engine import DreamKernel, get_dream_kernel

logger = logging.getLogger(__name__)

_GLOBAL_DREAM_KERNEL: DreamKernel | None = None


def get_global_dream_kernel() -> DreamKernel:
    """Retrieve or initialize global singleton DreamKernel."""
    global _GLOBAL_DREAM_KERNEL
    if _GLOBAL_DREAM_KERNEL is None:
        _GLOBAL_DREAM_KERNEL = get_dream_kernel()
    return _GLOBAL_DREAM_KERNEL


def reset_global_dream_kernel() -> None:
    """Reset global DreamKernel instance for test isolation."""
    global _GLOBAL_DREAM_KERNEL
    if _GLOBAL_DREAM_KERNEL is not None:
        _GLOBAL_DREAM_KERNEL.reset()
    _GLOBAL_DREAM_KERNEL = None


def kernel_get_status() -> dict[str, Any]:
    """Retrieve kernel lifecycle state, uptime, and lazy subsystem loading status."""
    kernel = get_global_dream_kernel()
    snap = kernel.get_snapshot()
    return {"success": True, **snap.to_dict()}


def kernel_trigger_hot_reload() -> dict[str, Any]:
    """Trigger zero-downtime hot-reload of configurations, prompt templates, and plugins."""
    kernel = get_global_dream_kernel()
    return kernel.hot_reload()


def kernel_list_subsystems() -> dict[str, Any]:
    """Inspect all registered lazy subsystems and their loading states."""
    kernel = get_global_dream_kernel()
    descriptors = kernel.registry.list_descriptors()
    return {
        "success": True,
        "total_registered": len(descriptors),
        "loaded_active_count": kernel.registry.count_loaded(),
        "subsystems": {k: v.to_dict() for k, v in descriptors.items()},
    }


def kernel_get_memory_profile() -> dict[str, Any]:
    """Retrieve cold-start benchmarks and memory footprint metrics."""
    kernel = get_global_dream_kernel()
    snap = kernel.get_snapshot()
    return {"success": True, "memory_profile": snap.memory_profile}


def kernel_reset() -> dict[str, Any]:
    """Reset kernel state and reload default lazy subsystem proxies."""
    reset_global_dream_kernel()
    return {"success": True, "message_fa": "هسته اصلی دریم با موفقیت بازنشانی شد."}


def get_kernel_tools() -> list[dict[str, Any]]:
    """Return tool manifests for LLM registration."""
    return [
        {
            "name": "kernel_get_status",
            "description": "Get runtime lifecycle state and active subsystems.",
            "parameters": {"type": "object", "properties": {}},
            "handler": kernel_get_status,
        },
        {
            "name": "kernel_trigger_hot_reload",
            "description": "Trigger zero-downtime hot reload of agent plugins and configurations.",
            "parameters": {"type": "object", "properties": {}},
            "handler": kernel_trigger_hot_reload,
        },
        {
            "name": "kernel_list_subsystems",
            "description": "List all registered lazy subsystems and inspect load status.",
            "parameters": {"type": "object", "properties": {}},
            "handler": kernel_list_subsystems,
        },
        {
            "name": "kernel_get_memory_profile",
            "description": "Inspect memory profile, lazy-load ratios, and cold-boot timing.",
            "parameters": {"type": "object", "properties": {}},
            "handler": kernel_get_memory_profile,
        },
    ]
