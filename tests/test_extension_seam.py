"""Contract and failure-boundary tests for the P0 extension seam."""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

import pytest

from dream.bridge import extensions as bridge_extensions
from dream.bridge.methods import BridgeMethods
from dream.tools import REGISTRY

FIXTURE = Path(__file__).parent / "fixtures" / "extension_seam" / "dream"


def _reset_bridge_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge_extensions.Registry, "_discovered", False)
    monkeypatch.setattr(bridge_extensions.Registry, "_discovering", False)
    monkeypatch.setattr(bridge_extensions.Registry, "_published", False)
    monkeypatch.setattr(
        bridge_extensions.Registry, "_handlers", bridge_extensions.MappingProxyType({})
    )
    monkeypatch.setattr(bridge_extensions.Registry, "errors", [])


def _install_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fixture_dream = tmp_path / "dream"
    shutil.copytree(FIXTURE, fixture_dream)
    import dream
    import dream.bridge

    monkeypatch.setattr(
        dream.bridge,
        "__path__",
        [*dream.bridge.__path__, str(fixture_dream / "bridge")],
    )
    monkeypatch.setattr(dream, "__path__", [*dream.__path__, str(fixture_dream)])
    for module in tuple(sys.modules):
        if module.startswith("dream.bridge.methods_") or module.startswith("dream.hello"):
            sys.modules.pop(module, None)
    importlib.invalidate_caches()
    _reset_bridge_registry(monkeypatch)
    return fixture_dream


def _handler_table() -> dict[str, object]:
    # Binding the real method table needs no live store; this exercises the
    # dispatcher source of truth without bringing up a sidecar process.
    methods = BridgeMethods.__new__(BridgeMethods)
    return methods._build_handler_table()


def test_fixture_method_is_present_in_real_dispatch_table(tmp_path, monkeypatch) -> None:
    fixture_dream = _install_fixture(tmp_path, monkeypatch)
    import dream.extensions as tool_extensions

    monkeypatch.setattr(tool_extensions, "_discovered", False)
    monkeypatch.setattr(tool_extensions, "errors", [])
    table = _handler_table()
    assert table["hello.greet"](name="Dream") == {"message": "hello Dream"}
    assert "hello_tool" in REGISTRY
    assert fixture_dream.exists()
    REGISTRY.pop("hello_tool", None)


def test_import_failure_is_quarantined_without_changing_builtins(tmp_path, monkeypatch) -> None:
    fixture_dream = _install_fixture(tmp_path, monkeypatch)
    (fixture_dream / "bridge" / "methods_boom.py").write_text('raise RuntimeError("boom")\n')
    table = _handler_table()
    assert "session.create" in table
    assert "hello.greet" in table
    assert any(
        "methods_boom" in error and "boom" in error
        for error in bridge_extensions.Registry.errors
    )


def test_builtin_collision_is_refused_and_builtin_remains(tmp_path, monkeypatch) -> None:
    fixture_dream = _install_fixture(tmp_path, monkeypatch)
    (fixture_dream / "bridge" / "methods_session.py").write_text(
        "def replace():\n    return {'wrong': True}\n\nHANDLERS = {'session.create': replace}\n"
    )
    table = _handler_table()
    assert table["session.create"].__self__.__class__ is BridgeMethods
    assert any(
        "session.create" in error and "built-in" in error
        for error in bridge_extensions.Registry.errors
    )
    with pytest.raises(RuntimeError, match="immutable"):
        bridge_extensions.Registry.register_bridge_methods({"later.method": lambda: None})


def test_missing_tools_modules_are_silent_on_stock_tree(monkeypatch) -> None:
    import dream.extensions as tool_extensions

    monkeypatch.setattr(tool_extensions, "_discovered", False)
    monkeypatch.setattr(tool_extensions, "errors", [])
    tool_extensions.discover_tools()
    assert tool_extensions.errors == []


def test_unsafe_and_duplicate_extension_methods_are_refused(monkeypatch) -> None:
    _reset_bridge_registry(monkeypatch)
    bridge_extensions.Registry.register_bridge_methods({"hello.greet": lambda: None})
    with pytest.raises(ValueError, match="duplicate"):
        bridge_extensions.Registry.register_bridge_methods({"hello.greet": lambda: None})
    with pytest.raises(ValueError, match="unsafe"):
        bridge_extensions.Registry.register_bridge_methods({"../escape": lambda: None})
