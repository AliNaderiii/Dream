"""Tool approval policy and the per-instance bound tool set.

The :class:`ApprovalPolicy` is the single decision point for every tool
invocation. Evaluation order is a contract (SEC Stage B): the L3
security floor runs BEFORE any approval logic and cannot be overridden
by modes, autonomous contexts, approvers, or auto-approve
(``--yolo``-style) grants.

The :data:`INSTANCE_BOUND_TOOL_NAMES` set names the tools Dream
registers as per-instance closures bound to the owning agent's stores
(memory, reminders, bounded stores). A child agent rebinds the
memory/reminder names to its own ephemeral store in its own
``__init__``; the bounded-store names only exist when a parent
attached :class:`BoundedMemory`, so a child can never rebind them.
The subagent builder uses this set to refuse grants that would hand a
child a parent-bound closure verbatim.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from dream.tools import REGISTRY

# Tools Dream registers as per-instance closures bound to the owning
# agent's stores (memory, reminders, bounded stores). A child agent rebinds
# the memory/reminder names to its own ephemeral store in its own
# ``__init__``; the bounded-store names only exist when a parent attached
# ``BoundedMemory``, so a child can never rebind them. The subagent builder
# uses this set to refuse grants that would hand a child a parent-bound
# closure verbatim (MEM Stage A: agent_notes/user_profile must never reach
# a parent's bounded stores from inside a subagent).
INSTANCE_BOUND_TOOL_NAMES = frozenset(
    {
        "remember_fact",
        "search_memory",
        "forget_memory",
        "create_reminder",
        "cancel_reminder",
        "agent_notes",
        "user_profile",
    }
)


@dataclass(slots=True)
class ApprovalPolicy:
    """Approval rules based exclusively on each registered tool's real risk.

    Evaluation order is a contract (SEC Stage B): the L3 security floor runs
    BEFORE any approval logic and cannot be overridden by modes, autonomous
    contexts, approvers, or auto-approve (``--yolo``-style) grants.
    """

    auto_approve: set[str] = field(default_factory=lambda: {"safe", "guarded"})
    always_ask: set[str] = field(default_factory=lambda: {"dangerous"})
    ask: Callable[[str, dict[str, Any]], bool] | None = None
    registry: Mapping[str, Any] | None = None
    """Private tool table to resolve risk from; ``None`` uses the global one.

    A subagent dispatches against its own grant, so its policy must judge risk
    from the same mapping. Reading the global registry here would let a name
    the subagent was never granted resolve to a real risk tier.
    """
    context: str = "interactive"
    """Execution context for autonomous runs: ``interactive``, ``cron`` or
    ``single_query``. Autonomous contexts deny dangerous tools by default."""
    security: Any = None
    """SecurityEngine to evaluate dangerous calls; ``None`` uses the
    process-wide default engine."""
    scope: str = "admin"
    """SEC Stage E (G-01): the linked user's permission scope —
    ``chat_only | safe_tools | guarded_tools | admin``. Tools above the
    scope's ceiling are refused; the floor still precedes the gate."""
    attempt_limiter: Callable[[str, dict[str, Any]], bool] | None = None
    """SEC Stage E (G-02): optional per-user approval-attempt throttle.
    Called for dangerous tools that passed floor and scope; ``False``
    refuses with a rate-limit denial."""

    #: The risk ceiling each scope may reach (G-01). Class-level constant —
    #: not a dataclass field.
    _SCOPE_CEILING = {
        "chat_only": frozenset(),
        "safe_tools": frozenset({"safe"}),
        "guarded_tools": frozenset({"safe", "guarded"}),
        "admin": frozenset({"safe", "guarded", "dangerous"}),
    }

    def allows(self, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
        """Decide whether *tool_name* may run with *arguments*.

        The function returns ``(allowed, reason)``; a ``False`` reason is
        safe to surface to the user (it is a denial message, not a
        credential or internal error).
        """
        from dream.security.engine import default_engine

        registered = (REGISTRY if self.registry is None else self.registry).get(tool_name)
        if registered is None:
            return False, "unknown tool"
        risk = registered.risk
        engine = self.security if self.security is not None else default_engine()
        ceiling = self._SCOPE_CEILING.get(self.scope, frozenset())
        if risk == "dangerous":
            # Contract: the L3 floor precedes EVERY approval-layer gate —
            # scope, throttles, contexts and modes alike.
            refusal = engine.floor_check(tool_name, arguments)
            if refusal is not None:
                return False, refusal
            if "dangerous" not in ceiling:
                return (
                    False,
                    f"dangerous tool denied: scope {self.scope!r} does not allow it",
                )
            if self.attempt_limiter is not None and not self.attempt_limiter(
                tool_name, arguments
            ):
                return False, "dangerous tool denied: too many approval attempts"
            if risk in self.always_ask or self.context != "interactive":
                # Floor -> autonomous-context gate -> mode, in that order,
                # all inside the engine; nothing below can override the floor.
                decision = engine.evaluate_dangerous(
                    tool_name, arguments, context=self.context, ask=self.ask
                )
                return decision.allowed, decision.reason
            return True, "dangerous tool auto-approved"
        if risk not in ceiling:
            return False, f"{risk} tool denied: scope {self.scope!r} does not allow it"
        if risk in self.always_ask:
            if self.ask is None:
                return False, f"{risk} tool denied: no approver configured"
            return (
                (True, f"{risk} tool approved")
                if self.ask(tool_name, arguments)
                else (False, f"{risk} tool denied by approver")
            )
        if risk in self.auto_approve:
            return True, f"{risk} tool auto-approved"
        return False, f"{risk} tool denied by policy"
