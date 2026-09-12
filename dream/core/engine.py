"""Master Dream Agent Kernel Coordinating Lazy Subsystem Registry and Lifecycle."""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

from dream.core.lazy_registry import LazySubsystemRegistry
from dream.core.lifecycle import KernelLifecycleManager
from dream.core.types import KernelLifecycleSnapshot


class DreamKernel:
    """Master Kernel managing lazy module loading, cold-boot performance, and system health."""

    def __init__(self) -> None:
        self.kernel_id = f"krn-{uuid.uuid4().hex[:8]}"
        self.lifecycle = KernelLifecycleManager()
        self.registry = LazySubsystemRegistry()
        self._register_default_subsystems()
        self.lifecycle.boot()

    def _register_default_subsystems(self) -> None:
        """Register the built-in catalog of Dream subsystems as lazy proxies."""
        catalog = [
            ("vision", "ادراک بینایی", "dream.vision.engine:get_vision_engine"),
            ("synthetic", "تولید داده‌های سنتتیک", "dream.synthetic.engine:get_synthetic_engine"),
            ("federation", "مش عصبی و فدراسیون", "dream.federation.engine:get_federation_engine"),
            ("dashboard", "برج مراقبت و داشبورد", "dream.dashboard.engine:get_dashboard_engine"),
            ("reactive", "موتور رویدادمحور", "dream.reactive.engine:get_reactive_engine"),
            ("rbac", "کنترل دسترسی و سهمیه", "dream.rbac.gateway:get_rbac_gateway"),
            ("duplex", "گفتگوی صوتی زنده", "dream.duplex.engine:get_duplex_engine"),
            ("refactor", "تحلیل کد و بازآرایی", "dream.refactor.engine:get_refactor_engine"),
            ("workflow", "گردش‌کار و Saga", "dream.workflow.engine:get_workflow_engine"),
            ("cache", "کش معنایی توکن", "dream.cache.semantic:get_semantic_cache"),
            ("knowledge", "گراف دانش زمان‌مند", "dream.knowledge.graph:get_knowledge_graph"),
            ("swarm", "شبکه عامل‌های Swarm", "dream.swarm.orchestrator:get_swarm_orchestrator"),
            ("debate", "مناظره و اجماع دلفی", "dream.debate.engine:get_debate_engine"),
            ("reasoning", "استدلال درختی", "dream.reasoning.tree:get_tree_reasoning_engine"),
        ]

        for name, name_fa, factory_path in catalog:
            self.registry.register_subsystem(
                name=name,
                display_name_fa=name_fa,
                factory_path=factory_path,
            )

    def get_snapshot(self) -> KernelLifecycleSnapshot:
        """Capture comprehensive kernel telemetry and loaded subsystem snapshot."""
        descriptors = self.registry.list_descriptors()
        mem_profile = {
            "pid": os.getpid(),
            "cold_start_time_ms": self.lifecycle.cold_start_time_ms,
            "lazy_subsystems_count": self.registry.count_total(),
            "loaded_subsystems_count": self.registry.count_loaded(),
            "lazy_ratio_pct": round(
                (1.0 - (self.registry.count_loaded() / max(1, self.registry.count_total()))) * 100,
                2,
            ),
        }

        return KernelLifecycleSnapshot(
            kernel_id=self.kernel_id,
            state=self.lifecycle.state,
            uptime_sec=self.lifecycle.uptime_sec,
            cold_start_time_ms=self.lifecycle.cold_start_time_ms,
            total_subsystems_registered=self.registry.count_total(),
            active_subsystems_loaded=self.registry.count_loaded(),
            subsystems=descriptors,
            memory_profile=mem_profile,
            timestamp=time.time(),
        )

    def hot_reload(self) -> dict[str, Any]:
        """Trigger zero-downtime hot reload of kernel and loaded plugins."""
        return self.lifecycle.hot_reload()

    def get_subsystem(self, name: str) -> Any | None:
        """Resolve and instantiate a lazy subsystem on-demand."""
        return self.registry.get_subsystem(name)

    def reset(self) -> None:
        """Reset kernel and registries for test isolation."""
        self.lifecycle.reset()
        self.registry.reset()
        self._register_default_subsystems()
        self.lifecycle.boot()


# Global Singleton
_GLOBAL_DREAM_KERNEL: DreamKernel | None = None


def get_dream_kernel() -> DreamKernel:
    """Retrieve global singleton DreamKernel instance."""
    global _GLOBAL_DREAM_KERNEL
    if _GLOBAL_DREAM_KERNEL is None:
        _GLOBAL_DREAM_KERNEL = DreamKernel()
    return _GLOBAL_DREAM_KERNEL
