"""Contract tests for the P0 add-only extension seam."""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

from dream.bridge import extensions as bridge_extensions
from dream.tools import REGISTRY

FIXTURE = Path(__file__).parent / "fixtures" / "extension_seam" / "dream"


def test_fixture_bridge_method_and_tool_are_discovered(tmp_path, monkeypatch) -> None:
    """A new domain file is dispatchable and its decorated tool reaches REGISTRY."""
    fixture_dream = tmp_path / "dream"
    shutil.copytree(FIXTURE, fixture_dream)

    import dream
    import dream.bridge
    import dream.extensions as tool_extensions

    monkeypatch.setattr(dream.bridge, "__path__", [*dream.bridge.__path__, str(fixture_dream / "bridge")])
    monkeypatch.setattr(dream, "__path__", [*dream.__path__, str(fixture_dream)])
    monkeypatch.setattr(bridge_extensions.Registry, "_discovered", False)
    monkeypatch.setattr(bridge_extensions.Registry, "_handlers", bridge_extensions.MappingProxyType({}))
    monkeypatch.setattr(tool_extensions, "_discovered", False)
    sys.modules.pop("dream.bridge.methods_hello", None)
    sys.modules.pop("dream.hello", None)
    sys.modules.pop("dream.hello.tools", None)
    try:
        assert bridge_extensions.Registry.merged_handlers()["hello.greet"](name="Dream") == {
            "message": "hello Dream"
        }
        tool_extensions.discover_tools()
        assert "hello_tool" in REGISTRY
    finally:
        sys.modules.pop("dream.bridge.methods_hello", None)
        sys.modules.pop("dream.hello.tools", None)
        sys.modules.pop("dream.hello", None)
        REGISTRY.pop("hello_tool", None)


def test_invalid_or_colliding_extension_methods_are_refused(monkeypatch) -> None:
    """Validation rejects unsafe names and leaves the published table unchanged."""
    monkeypatch.setattr(bridge_extensions.Registry, "_handlers", bridge_extensions.MappingProxyType({}))
    try:
        bridge_extensions.Registry.register_bridge_methods({"hello.greet": lambda: None})
        before = bridge_extensions.Registry.merged_handlers()
        try:
            bridge_extensions.Registry.register_bridge_methods({"../escape": lambda: None})
        except ValueError:
            pass
        else:  # pragma: no cover - keeps the security assertion explicit
            raise AssertionError("unsafe method was accepted")
        assert bridge_extensions.Registry.merged_handlers() == before
    finally:
        monkeypatch.undo()
        importlib.invalidate_caches()
