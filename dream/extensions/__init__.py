"""Safe auto-import seam for optional domain tool modules.

Importing :mod:`dream.extensions` discovers only ``dream/<domain>/tools.py``
files located beneath the installed Dream package.  Failures are quarantined
and logged instead of affecting the core tool registry.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil
import re
import threading
from pathlib import Path

logger = logging.getLogger("dream.extensions")
_DOMAIN = re.compile(r"^[a-z][a-z0-9_]*$")
_lock = threading.RLock()
_discovered = False
errors: list[str] = []


def _record(module: str, reason: str) -> None:
    message = f"quarantined tool extension {module}: {reason}"
    errors.append(message)
    logger.error(message)


def discover_tools() -> None:
    """Import every valid immediate domain ``tools`` module exactly once."""
    global _discovered
    with _lock:
        if _discovered:
            return
        _discovered = True  # protects import cycles and concurrent startup
        package = importlib.import_module("dream")
        roots = [Path(path).resolve() for path in package.__path__]
        candidates = sorted(
            pkgutil.iter_modules(package.__path__, "dream."), key=lambda item: item.name
        )
        for info in candidates:
            domain = info.name.rsplit(".", 1)[-1]
            if not info.ispkg or not _DOMAIN.fullmatch(domain):
                continue
            module_name = f"dream.{domain}.tools"
            try:
                spec = importlib.util.find_spec(module_name)
                # A domain without a tools module is the normal case.
                if spec is None:
                    continue
                if spec.origin is None:
                    _record(module_name, "tools module has no importable file origin")
                    continue
                origin = Path(spec.origin).resolve()
                if not any(origin.is_relative_to(root) for root in roots):
                    _record(module_name, "tools module is outside dream")
                    continue
                importlib.import_module(module_name)
            except ModuleNotFoundError as exc:
                # Missing tools (or a missing immediate package) is normal. A
                # missing dependency *inside* an existing tools.py is not.
                if exc.name in {module_name, f"dream.{domain}"}:
                    continue
                _record(module_name, str(exc))
            except Exception as exc:  # no extension is allowed to break startup
                _record(module_name, str(exc))


# Tool discovery is intentionally import-triggered, not request-triggered.
discover_tools()

__all__ = ["discover_tools", "errors"]
