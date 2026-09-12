"""Dream Agent Kernel Core, Lifecycle Manager & Lazy Subsystem Registry."""

from __future__ import annotations

from dream.core.engine import DreamKernel, get_dream_kernel
from dream.core.lazy_registry import LazySubsystemProxy, LazySubsystemRegistry
from dream.core.lifecycle import KernelLifecycleManager
from dream.core.slash import handle_kernel_command
from dream.core.tools import (
    get_global_dream_kernel,
    get_kernel_tools,
    kernel_get_memory_profile,
    kernel_get_status,
    kernel_list_subsystems,
    kernel_reset,
    kernel_trigger_hot_reload,
    reset_global_dream_kernel,
)
from dream.core.types import (
    KernelLifecycleSnapshot,
    KernelState,
    SubsystemDescriptor,
    SubsystemLoadStatus,
)

__all__ = [
    "DreamKernel",
    "KernelLifecycleManager",
    "KernelLifecycleSnapshot",
    "KernelState",
    "LazySubsystemProxy",
    "LazySubsystemRegistry",
    "SubsystemDescriptor",
    "SubsystemLoadStatus",
    "get_dream_kernel",
    "get_global_dream_kernel",
    "get_kernel_tools",
    "handle_kernel_command",
    "kernel_get_memory_profile",
    "kernel_get_status",
    "kernel_list_subsystems",
    "kernel_reset",
    "kernel_trigger_hot_reload",
    "reset_global_dream_kernel",
]
