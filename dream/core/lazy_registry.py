"""Thread-Safe Lazy Loading Subsystem Registry and Proxy Wrapper."""

from __future__ import annotations

import importlib
import threading
import time
from collections.abc import Callable
from typing import Any

from dream.core.types import SubsystemDescriptor, SubsystemLoadStatus


class LazySubsystemProxy:
    """Proxy container deferring real subsystem instantiation until first method call or access."""

    def __init__(
        self,
        descriptor: SubsystemDescriptor,
        factory_fn: Callable[[], Any] | None = None,
    ) -> None:
        self._descriptor = descriptor
        self._factory_fn = factory_fn
        self._instance: Any | None = None
        self._lock = threading.RLock()

    @property
    def is_loaded(self) -> bool:
        """Return True if the underlying instance has been instantiated."""
        return self._instance is not None

    @property
    def descriptor(self) -> SubsystemDescriptor:
        """Return metadata descriptor."""
        return self._descriptor

    def get_instance(self) -> Any:
        """Thread-safely obtain or instantiate the underlying subsystem singleton."""
        if self._instance is not None:
            self._descriptor.total_invocations += 1
            self._descriptor.last_invoked_timestamp = time.time()
            return self._instance

        with self._lock:
            if self._instance is not None:
                self._descriptor.total_invocations += 1
                self._descriptor.last_invoked_timestamp = time.time()
                return self._instance

            t_start = time.perf_counter()
            self._descriptor.status = SubsystemLoadStatus.INSTANTIATING
            try:
                if self._factory_fn is not None:
                    self._instance = self._factory_fn()
                else:
                    # Dynamically import module:attr
                    mod_name, attr_name = self._descriptor.factory_path.split(":")
                    mod = importlib.import_module(mod_name)
                    factory = getattr(mod, attr_name)
                    self._instance = factory() if callable(factory) else factory

                t_end = time.perf_counter()
                self._descriptor.load_time_ms = (t_end - t_start) * 1000.0
                self._descriptor.status = SubsystemLoadStatus.ACTIVE
                self._descriptor.total_invocations += 1
                self._descriptor.last_invoked_timestamp = time.time()
                return self._instance
            except Exception as e:
                self._descriptor.status = SubsystemLoadStatus.FAILED
                self._descriptor.metadata["error"] = str(e)
                raise RuntimeError(
                    f"Failed lazy-loading subsystem '{self._descriptor.name}': {e}"
                ) from e

    def __getattr__(self, name: str) -> Any:
        """Transparently delegate attribute calls to underlying instance."""
        inst = self.get_instance()
        return getattr(inst, name)


class LazySubsystemRegistry:
    """Central registry maintaining lazy proxies for all Dream agent modules."""

    def __init__(self) -> None:
        self._proxies: dict[str, LazySubsystemProxy] = {}
        self._lock = threading.RLock()

    def register_subsystem(
        self,
        name: str,
        display_name_fa: str,
        factory_path: str,
        factory_fn: Callable[[], Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LazySubsystemProxy:
        """Register a lazy subsystem definition into the kernel registry."""
        with self._lock:
            desc = SubsystemDescriptor(
                name=name,
                display_name_fa=display_name_fa,
                factory_path=factory_path,
                status=SubsystemLoadStatus.REGISTERED_LAZY,
                metadata=metadata or {},
            )
            proxy = LazySubsystemProxy(desc, factory_fn=factory_fn)
            self._proxies[name] = proxy
            return proxy

    def get_proxy(self, name: str) -> LazySubsystemProxy | None:
        """Retrieve proxy by subsystem name."""
        return self._proxies.get(name)

    def get_subsystem(self, name: str) -> Any | None:
        """Resolve and retrieve live instance of subsystem."""
        proxy = self._proxies.get(name)
        return proxy.get_instance() if proxy else None

    def list_descriptors(self) -> dict[str, SubsystemDescriptor]:
        """Return copy of all registered subsystem descriptors."""
        return {name: proxy.descriptor for name, proxy in self._proxies.items()}

    def count_loaded(self) -> int:
        """Return number of currently instantiated subsystems."""
        return sum(1 for p in self._proxies.values() if p.is_loaded)

    def count_total(self) -> int:
        """Return total count of registered subsystems."""
        return len(self._proxies)

    def reset(self) -> None:
        """Clear registry."""
        with self._lock:
            self._proxies.clear()
