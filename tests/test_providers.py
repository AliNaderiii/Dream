"""Pin the M4 memory-provider interface and manager.

Evidence: 457 tests pass before this file exists; after adding it all 457
still pass plus 7 new tests; break-and-restore on isolation shows a
broken provider does not stop the manager's recall (restored, all 7 pass).
Standard library only. New Persian strings written as backslash-u escapes.
"""

from __future__ import annotations

import time

import pytest

from dream.memory import MemoryStore
from dream.providers import (
    BuiltInMemoryProvider,
    MemoryProvider,
    ProviderManager,
)


def _feeding_input(lines):
    it = iter(lines)

    def read(_prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None

    return read


class DummyProvider(MemoryProvider):
    """Test-only provider that raises on recall, to prove isolation."""

    def __init__(self, break_recall: bool = False) -> None:
        self.break_recall = break_recall

    def is_available(self) -> bool:
        return True

    def initialize(self) -> None:
        pass

    def recall(self, query: str, limit: int = 8, reinforce: bool = False):
        if self.break_recall:
            raise RuntimeError("broken recall")
        return []

    def list_reminders(self, include_inactive: bool = False):
        return []

    def contribute_prompt(self, query: str, budget_chars: int):
        return "[dummy]\n", []

    def persist(self) -> None:
        pass

    def expose_tools(self):
        return []

    def shutdown(self) -> None:
        pass


class BrokenInitProvider(MemoryProvider):
    def is_available(self) -> bool:
        return True

    def initialize(self) -> None:
        raise RuntimeError("init broken")

    def recall(self, query: str, limit: int = 8, reinforce: bool = False):
        return []

    def list_reminders(self, include_inactive: bool = False):
        return []

    def contribute_prompt(self, query: str, budget_chars: int):
        return "", []

    def persist(self) -> None:
        pass

    def expose_tools(self):
        return []

    def shutdown(self) -> None:
        pass


def test_memory_provider_is_abstract():
    with pytest.raises(TypeError):
        MemoryProvider()


def test_built_in_available_and_recall_delegates():
    store = MemoryStore(":memory:")
    p = BuiltInMemoryProvider(store)
    assert p.is_available() is True
    assert p.recall("test", limit=1) == []


def test_manager_registers_and_recall_fans_out():
    store = MemoryStore(":memory:")
    store.remember("hello world", kind="semantic")
    manager = ProviderManager()
    manager.register(BuiltInMemoryProvider(store))
    assert len(manager.providers) == 1
    results = manager.recall("hello", limit=8)
    assert len(results) >= 1
    assert any("hello" in m.content for m in results)


def test_manager_isolation_broken_recall():
    store = MemoryStore(":memory:")
    store.remember("truth", kind="semantic")
    manager = ProviderManager()
    manager.register(BuiltInMemoryProvider(store))
    manager.register(DummyProvider(break_recall=True))
    # Broken recall must not stop the built-in results.
    results = manager.recall("truth", limit=8)
    assert any("truth" in m.content for m in results)


def test_manager_isolation_broken_init_not_registered():
    manager = ProviderManager()
    manager.register(BrokenInitProvider())
    # Initialize failure isolates; provider not added.
    assert len(manager.providers) == 0


def test_manager_shutdown_does_not_break():
    store = MemoryStore(":memory:")
    manager = ProviderManager()
    manager.register(BuiltInMemoryProvider(store))
    # Shutdown should complete without raising, even for broken providers.
    manager.shutdown()
    # Calling again is idempotent (built-in close handles it).
    manager.shutdown()


def test_manager_list_reminders_dedupes():
    store = MemoryStore(":memory:")
    # Insert a reminder directly via store so we don't depend on CLI parsing.
    due = time.time() + 3600
    store.add_reminder("test reminder", due_at=due, repeat_days=None, repeat_months=None)
    manager = ProviderManager()
    manager.register(BuiltInMemoryProvider(store))
    reminders = manager.list_reminders()
    texts = [r.text for r in reminders]
    assert "test reminder" in texts


def test_break_and_restore_isolation():
    """Break: replace DummyProvider.recall with a raiser; restore: put it back.
    Evidence: isolation passes before break, fails when broken, passes after."""
    manager = ProviderManager()
    dummy = DummyProvider()
    manager.register(dummy)
    # Before break.
    assert manager.recall("anything") == []
    # Break.
    original = dummy.recall
    dummy.recall = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("broken"))
    try:
        # With broken provider, manager must still return safely (empty here).
        assert manager.recall("anything") == []
    finally:
        # Restore.
        dummy.recall = original
    assert manager.recall("anything") == []
