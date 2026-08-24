"""Safe, deterministic discovery for optional Dream Bridge method modules.

This module deliberately discovers only siblings of this package named
``methods_<domain>.py``.  It is not a general plugin loader and never accepts a
module path from RPC input or the environment.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil
import re
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

logger = logging.getLogger("dream.bridge.extensions")

_DOMAIN = re.compile(r"^[a-z][a-z0-9_]*$")
_METHOD = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


class Registry:
    """Build-once extension handler registry published atomically.

    ``errors`` is intentionally inspectable for health checks and tests.  An
    import failure quarantines that module; it cannot remove handlers already
    collected from an earlier module or affect core bridge handlers.
    """

    _lock = threading.RLock()
    _discovered = False
    _handlers: Mapping[str, Callable[..., Any]] = MappingProxyType({})
    errors: list[str] = []

    @classmethod
    def register_bridge_methods(cls, mapping: Mapping[str, Callable[..., Any]]) -> None:
        """Validate and add extension handlers during discovery.

        This is primarily useful to a controlled bootstrap module.  Feature
        modules should export ``HANDLERS`` so their declarations remain
        inspectable and deterministic.
        """
        with cls._lock:
            pending = dict(cls._handlers)
            for name, handler in mapping.items():
                if not isinstance(name, str) or not _METHOD.fullmatch(name):
                    raise ValueError(f"unsafe bridge extension method name: {name!r}")
                if not callable(handler):
                    raise TypeError(f"bridge extension handler {name!r} is not callable")
                if name in pending:
                    raise ValueError(f"duplicate bridge extension method: {name}")
                pending[name] = handler
            cls._handlers = MappingProxyType(pending)

    @classmethod
    def _record(cls, module: str, reason: str) -> None:
        message = f"quarantined bridge extension {module}: {reason}"
        cls.errors.append(message)
        logger.error(message)

    @classmethod
    def _discover(cls) -> None:
        # One bridge startup also activates the companion decorated-tool seam.
        from dream.extensions import discover_tools

        discover_tools()
        with cls._lock:
            if cls._discovered:
                return
            # Mark before importing: a module importing the bridge cannot
            # recursively start another discovery pass.
            cls._discovered = True
            package = importlib.import_module("dream.bridge")
            roots = [Path(path).resolve() for path in package.__path__]
            candidates = sorted(
                info.name
                for info in pkgutil.iter_modules(package.__path__, "dream.bridge.")
                if info.name.rsplit(".", 1)[-1].startswith("methods_")
            )
            for module_name in candidates:
                leaf = module_name.rsplit(".", 1)[-1]
                domain = leaf.removeprefix("methods_")
                if not _DOMAIN.fullmatch(domain):
                    cls._record(module_name, "unsafe module name")
                    continue
                try:
                    spec = importlib.util.find_spec(module_name)
                    origin = Path(spec.origin).resolve() if spec and spec.origin else None
                    if origin is None or not any(origin.is_relative_to(root) for root in roots):
                        raise ValueError("module is outside dream.bridge")
                    module = importlib.import_module(module_name)
                    handlers = getattr(module, "HANDLERS", None)
                    if not isinstance(handlers, Mapping):
                        raise TypeError("HANDLERS must be a mapping")
                    # A domain module owns exactly its own RPC namespace.
                    for method in handlers:
                        if not isinstance(method, str) or not method.startswith(f"{domain}."):
                            raise ValueError("method is outside the module domain")
                    cls.register_bridge_methods(handlers)
                except Exception as exc:  # fail closed: one module cannot stop the sidecar
                    cls._record(module_name, str(exc))

    @classmethod
    def merged_handlers(cls) -> Mapping[str, Callable[..., Any]]:
        """Return the immutable, memoized extension table."""
        cls._discover()
        return cls._handlers


# Small public alias for callers that prefer a function over the registry API.
register_bridge_methods = Registry.register_bridge_methods
