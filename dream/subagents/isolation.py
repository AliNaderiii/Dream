"""Child agent store and tool registry isolation."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from dream.agent import INSTANCE_BOUND_TOOL_NAMES, ApprovalPolicy, Dream, build_backend
from dream.commerce import Ledger
from dream.memory import MemoryStore
from dream.subagents.constants import DEFAULT_TOOL_GRANT, REGISTRY_LOCK
from dream.subagents.types import SubAgentSpec
from dream.tools import REGISTRY, Tool


def build_child_tools(
    store: MemoryStore,
    granted: Iterable[str] | None,
    *,
    allow_dangerous: bool = False,
    backend: Any | None = None,
    ledger: Ledger | None = None,
) -> tuple[Dream, dict[str, Tool]]:
    """Build a child Dream instance and its private tool table without side effects."""
    names = list(DEFAULT_TOOL_GRANT if granted is None else granted)
    with REGISTRY_LOCK:
        snapshot = dict(REGISTRY)
        try:
            child = Dream(store=store, backend=backend)
            captured = dict(REGISTRY)
        finally:
            REGISTRY.clear()
            REGISTRY.update(snapshot)

    child.ledger = ledger
    child._ledger_refusal = None
    table: dict[str, Tool] = {}
    for name in names:
        registered = captured.get(name)
        if registered is None:
            continue
        if registered.risk == "dangerous" and not allow_dangerous:
            continue
        if (
            name in INSTANCE_BOUND_TOOL_NAMES
            and name in snapshot
            and registered is snapshot[name]
        ):
            continue
        table[name] = registered

    child.approval_policy = ApprovalPolicy(registry=table)
    return child, table


def _build_backend(spec: SubAgentSpec) -> Any:
    """Instantiate the provider backend for a subagent spec."""
    backend = build_backend(spec.model_provider or "echo")
    if spec.model_name and hasattr(backend, "model"):
        backend.model = spec.model_name
    return backend
