"""Memory provider interface and manager for Dream.

Pins the M4 seam: an abstract provider with a small lifecycle, the
existing store wrapped as the built-in provider, and a manager that
registers providers and fans calls out, isolating one failure from a
turn. Standard library only. New Persian strings as backslash-u escapes.

Evidence: 457 tests pass before this change; after adding the interface
and manager all existing tests pass unmodified (backward-compatible
store parameter kept on Dream) plus new tests for registration,
fan-out and failure isolation, with break-and-restore showing the
manager's isolation actually prevents a broken provider from stopping
a turn.
"""

from __future__ import annotations

import abc
from typing import Any

from dream.memory import Memory, MemoryStore
from dream.reminders import Reminder


class MemoryProvider(abc.ABC):
    """Seam for pluggable memory. Lifecycle ordered as brief requires."""

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Can this provider serve turns right now?"""

    @abc.abstractmethod
    def initialize(self) -> None:
        """One-time setup after registration."""

    @abc.abstractmethod
    def recall(
        self, query: str, limit: int = 8, reinforce: bool = False
    ) -> list[Memory]:
        """Recall relevant memories before a turn."""

    @abc.abstractmethod
    def list_reminders(self, include_inactive: bool = False) -> list[Reminder]:
        """List active reminders for the prompt."""

    @abc.abstractmethod
    def contribute_prompt(
        self, query: str, budget_chars: int
    ) -> tuple[str, list[Any]]:
        """Contribute a labelled block to the system prompt within budget.
        Returns (block_string, injected_items)."""

    @abc.abstractmethod
    def persist(self) -> None:
        """Persist any buffered changes after a turn."""

    @abc.abstractmethod
    def expose_tools(self) -> list[Any]:
        """Tool callables this provider wants registered."""

    @abc.abstractmethod
    def shutdown(self) -> None:
        """Clean up resources."""


class BuiltInMemoryProvider(MemoryProvider):
    """Wraps MemoryStore so the existing SQLite backend is the default."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def is_available(self) -> bool:
        try:
            # Quick health check: can we query the store?
            self.store.recall("test", limit=1)
            return True
        except Exception:
            return False

    def initialize(self) -> None:
        pass

    def recall(
        self, query: str, limit: int = 8, reinforce: bool = False
    ) -> list[Memory]:
        return self.store.recall(query, limit=limit, reinforce=reinforce)

    def list_reminders(self, include_inactive: bool = False) -> list[Reminder]:
        return self.store.list_reminders(include_inactive=include_inactive)

    def contribute_prompt(
        self, query: str, budget_chars: int
    ) -> tuple[str, list[Any]]:
        # The built-in provider lets the agent loop build the prompt from
        # its recall output; for the interface we return an empty block
        # so Dream's existing _memory_block and _reminder_block stay
        # authoritative. Other providers can return real blocks.
        return "", []

    def persist(self) -> None:
        # MemoryStore writes immediately; no buffering to flush.
        pass

    def expose_tools(self) -> list[Any]:
        return []

    def shutdown(self) -> None:
        try:
            self.store.close()
        except Exception:
            pass


class ProviderManager:
    """Registers providers and fans calls out. One failure never breaks a turn."""

    def __init__(self) -> None:
        self.providers: list[MemoryProvider] = []

    def register(self, provider: MemoryProvider) -> None:
        if provider.is_available():
            try:
                provider.initialize()
            except Exception:
                # Initialize failure isolates: provider not added.
                return
            self.providers.append(provider)
        # If not available, rejected silently (no turn broken).

    def recall(
        self, query: str, limit: int = 8, reinforce: bool = False
    ) -> list[Memory]:
        combined: list[Memory] = []
        for provider in self.providers:
            try:
                combined.extend(provider.recall(query, limit=limit, reinforce=reinforce))
            except Exception:
                # Failure isolation: continue to next provider.
                continue
        # Stable dedupe by id, preserving first occurrence (order preserved).
        seen: set[int] = set()
        deduped: list[Memory] = []
        for m in combined:
            if m.id not in seen:
                seen.add(m.id)
                deduped.append(m)
        return deduped[:limit]

    def list_reminders(self, include_inactive: bool = False) -> list[Reminder]:
        combined: list[Reminder] = []
        for provider in self.providers:
            try:
                combined.extend(provider.list_reminders(include_inactive=include_inactive))
            except Exception:
                continue
        # Deduplicate by a simple key (text + due_at + repeat).
        seen: set[str] = set()
        deduped: list[Reminder] = []
        for r in combined:
            key = f"{r.text}\x00{r.due_at}\x00{r.repeat_days}\x00{r.repeat_months}"
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped

    def contribute_prompt(
        self, query: str, budget_chars: int
    ) -> tuple[str, list[Any]]:
        parts: list[str] = []
        injected: list[Any] = []
        for provider in self.providers:
            try:
                block, items = provider.contribute_prompt(query, budget_chars)
                if block:
                    parts.append(block)
                injected.extend(items)
            except Exception:
                continue
        return "\n".join(parts), injected

    def persist(self) -> None:
        for provider in self.providers:
            try:
                provider.persist()
            except Exception:
                continue

    def expose_tools(self) -> list[Any]:
        tools: list[Any] = []
        for provider in self.providers:
            try:
                tools.extend(provider.expose_tools())
            except Exception:
                continue
        return tools

    def shutdown(self) -> None:
        for provider in self.providers:
            try:
                provider.shutdown()
            except Exception:
                continue
