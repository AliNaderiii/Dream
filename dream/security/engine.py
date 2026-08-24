"""Approval engine v2 (layer L2) built around the L3 floor.

Evaluation order is the contract, and it is pinned by the property test
``blocklist_precedes_approval``:

    1. floor   — the hardline blocklist, BEFORE any approval logic,
                 non-overridable by mode, context, approvers or flags;
    2. context — cron / single-query gates (default deny, no human present);
    3. mode    — smart (assessor orders the decision), manual (a human
                 decides every dangerous call — the default and the exact
                 pre-SEC behaviour), off (explicit opt-in; everything the
                 floor did not catch runs, loudly logged).

The engine never touches the network itself; the assessor it delegates to
is fail-closed on timeout, error, or any schema deviation.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from dream.security import blocklist
from dream.security.assessor import ASSESS_TIMEOUT_SECONDS, Assessment, assess
from dream.security.history import ApprovalHistory, ApprovalStoreError

__all__ = [
    "CONTEXT_MODES",
    "Decision",
    "MODES",
    "SHELL_COMMAND_TOOLS",
    "SecurityEngine",
    "default_engine",
    "reset_default_engine",
]

MODES: tuple[str, ...] = ("smart", "manual", "off")
CONTEXT_MODES: tuple[str, ...] = ("deny", "auto")
CONTEXTS: tuple[str, ...] = ("interactive", "cron", "single_query")

#: Tools whose ``command`` argument flows through the floor and assessor.
SHELL_COMMAND_TOOLS = frozenset({"run_shell"})

MODE_ENV = "DREAM_SECURITY_MODE"
OFF_OPT_IN_ENV = "DREAM_SECURITY_OFF_OPT_IN"

_CONTEXT_DENIAL_EN = {
    "cron": "dangerous tool denied: cron mode denies dangerous tools by default",
    "single_query": (
        "dangerous tool denied: single-query mode denies dangerous tools by default"
    ),
}
_CONTEXT_DENIAL_FA = (
    "\u0627\u0628\u0632\u0627\u0631 \u067e\u0631\u062e\u0637\u0631 \u0631\u062f \u0634\u062f: "
    "\u062f\u0631 "
    "\u062d\u0627\u0644\u062a \u062e\u0648\u062f\u06a9\u0627\u0631 \u0628\u062f\u0648\u0646 "
    "\u062d\u0636\u0648\u0631 "
    "\u06a9\u0627\u0631\u0628\u0631\u060c \u0627\u0628\u0632\u0627\u0631\u0647\u0627\u06cc "
    "\u067e\u0631\u062e\u0637\u0631 "
    "\u0628\u0647\u200c\u0637\u0648\u0631 \u067e\u06cc\u0634\u200c\u0641\u0631\u0636 "
    "\u0631\u062f \u0645\u06cc\u200c\u0634\u0648\u0646\u062f"
)
_OFF_ALLOW_EN = "dangerous tool allowed: approval engine is OFF (explicit opt-in)"
_OFF_ALLOW_FA = (
    "\u0627\u0628\u0632\u0627\u0631 \u067e\u0631\u062e\u0637\u0631 \u0627\u062c\u0631\u0627 "
    "\u0634\u062f: "
    "\u0645\u0648\u062a\u0648\u0631 \u062a\u0623\u06cc\u06cc\u062f "
    "\u062e\u0627\u0645\u0648\u0634 \u0627\u0633\u062a "
    "(\u0628\u0627 \u062f\u0631\u062e\u0648\u0627\u0633\u062a \u0635\u0631\u06cc\u062d "
    "\u0634\u0645\u0627)"
)


@dataclass(frozen=True)
class Decision:
    """One engine verdict: whether the call may run and exactly why."""

    allowed: bool
    reason: str
    stage: str  # "floor" | "context" | "assessor" | "approval" | "mode"


class SecurityEngine:
    """Evaluates dangerous-tool calls through floor → context → mode."""

    def __init__(
        self,
        mode: str = "manual",
        *,
        cron_mode: str = "deny",
        single_query_mode: str = "deny",
        history: ApprovalHistory | None = None,
        history_path: str | None = None,
        model_call: Callable[[str], str] | None = None,
        assess_timeout: float = ASSESS_TIMEOUT_SECONDS,
        off_opt_in: bool = False,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        if mode == "off" and not off_opt_in:
            raise ValueError(
                "off mode is an explicit opt-in: pass off_opt_in=True to accept"
                " the persistent-warning contract"
            )
        if cron_mode not in CONTEXT_MODES:
            raise ValueError(f"cron_mode must be one of {CONTEXT_MODES}, got {cron_mode!r}")
        if single_query_mode not in CONTEXT_MODES:
            raise ValueError(
                f"single_query_mode must be one of {CONTEXT_MODES}, got {single_query_mode!r}"
            )
        self.mode = mode
        self.cron_mode = cron_mode
        self.single_query_mode = single_query_mode
        self.model_call = model_call
        self.assess_timeout = assess_timeout
        self.history_broken = False
        if history is not None:
            self.history: ApprovalHistory | None = history
        else:
            try:
                self.history = ApprovalHistory(history_path) if history_path else ApprovalHistory()
            except ApprovalStoreError:
                self.history = None
                self.history_broken = True

    # -- audit trail ------------------------------------------------------ #

    def _record(self, *, verdict: str, tool: str, command: str, **fields: Any) -> None:
        if self.history is None:
            return
        self.history.record(
            verdict=verdict,
            tool=tool,
            command=command,
            mode=self.mode,
            context=str(fields.get("context", "interactive")),
            rule_class=fields.get("rule_class"),
            detail=fields.get("detail"),
        )

    # -- the contract ----------------------------------------------------- #

    def floor_check(self, tool_name: str, arguments: dict[str, Any]) -> str | None:
        """The L3 refusal text for this call, or ``None`` when unblocked.

        Runs before any mode or approver is consulted; every policy and
        every direct executor consults this first.
        """
        if tool_name not in SHELL_COMMAND_TOOLS:
            return None
        command = str(arguments.get("command", ""))
        match = blocklist.scan(command)
        if match is None:
            return None
        self._record(
            verdict="floor_blocked",
            tool=tool_name,
            command=command,
            rule_class=match.rule.rule_class,
            detail=match.rule.rule_id,
        )
        return match.refusal

    def evaluate_dangerous(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        context: str = "interactive",
        ask: Callable[[str, dict[str, Any]], bool] | None = None,
    ) -> Decision:
        """Full engine path for one dangerous-tool call (floor first)."""
        command = (
            str(arguments.get("command", "")) if tool_name in SHELL_COMMAND_TOOLS else ""
        )
        refusal = self.floor_check(tool_name, arguments)
        if refusal is not None:
            return Decision(allowed=False, reason=refusal, stage="floor")
        if context not in CONTEXTS:
            raise ValueError(f"context must be one of {CONTEXTS}, got {context!r}")
        if context in ("cron", "single_query"):
            context_mode = self.cron_mode if context == "cron" else self.single_query_mode
            if context_mode == "deny":
                self._record(verdict=f"denied_{context}", tool=tool_name, command=command,
                             context=context)
                return Decision(
                    allowed=False,
                    reason=f"{_CONTEXT_DENIAL_EN[context]}\n{_CONTEXT_DENIAL_FA}",
                    stage="context",
                )
            # ``auto``: the owner explicitly let this autonomous context run
            # dangerous tools. The floor already ran; nothing else can.
            self._record(verdict=f"allowed_{context}_auto", tool=tool_name, command=command,
                         context=context)
            return Decision(
                allowed=True,
                reason=f"dangerous tool allowed: {context} mode is set to auto",
                stage="context",
            )
        if self.mode == "off":
            self._record(verdict="allowed_off_mode", tool=tool_name, command=command,
                         context=context)
            return Decision(allowed=True, reason=f"{_OFF_ALLOW_EN}\n{_OFF_ALLOW_FA}", stage="mode")
        assessment: Assessment | None = None
        if self.mode == "smart":
            assessment = assess(command, model_call=self.model_call, timeout=self.assess_timeout)
            if assessment.verdict == "allow_once":
                self._record(
                    verdict="approved_auto_low", tool=tool_name, command=command,
                    context=context, detail=assessment.level,
                )
                return Decision(
                    allowed=True,
                    reason=(
                        f"dangerous tool auto-approved: low risk ({assessment.reason_en})"
                    ),
                    stage="assessor",
                )
            if assessment.verdict == "deny":
                self._record(
                    verdict="denied_assessor", tool=tool_name, command=command,
                    context=context, detail=assessment.source,
                )
                return Decision(
                    allowed=False,
                    reason=(
                        f"dangerous tool denied by risk assessor: {assessment.reason_en}"
                        f"\n{assessment.reason_fa}"
                    ),
                    stage="assessor",
                )
        if ask is None:
            self._record(verdict="denied_no_approver", tool=tool_name, command=command,
                         context=context)
            return Decision(
                allowed=False,
                reason="dangerous tool denied: no approver configured",
                stage="approval",
            )
        detail = assessment.level if assessment is not None else None
        approved = bool(ask(tool_name, arguments))
        if approved:
            self._record(verdict="approved_human", tool=tool_name, command=command,
                         context=context, detail=detail)
            return Decision(allowed=True, reason="dangerous tool approved", stage="approval")
        self._record(verdict="denied_by_approver", tool=tool_name, command=command,
                     context=context, detail=detail)
        return Decision(allowed=False, reason="dangerous tool denied by approver",
                        stage="approval")

    # -- transparency ------------------------------------------------------ #

    def status(self) -> dict[str, Any]:
        """Machine-readable engine state for the bridge and status surfaces."""
        return {
            "mode": self.mode,
            "cron_mode": self.cron_mode,
            "single_query_mode": self.single_query_mode,
            "off_active": self.mode == "off",
            "floor": "always-on",
            "history_path": self.history.path if self.history is not None else None,
            "history_available": self.history is not None,
        }


_default_engine: SecurityEngine | None = None


def default_engine() -> SecurityEngine:
    """The process-wide engine, configured from the environment.

    ``DREAM_SECURITY_MODE`` selects the mode (validated; invalid values
    fall back to ``manual``); ``off`` additionally requires
    ``DREAM_SECURITY_OFF_OPT_IN=1`` — the explicit opt-in.
    """
    global _default_engine
    if _default_engine is not None:
        return _default_engine
    mode = os.environ.get(MODE_ENV, "manual").strip().lower()
    if mode not in MODES:
        mode = "manual"
    off_opt_in = os.environ.get(OFF_OPT_IN_ENV, "").strip().lower() in {"1", "true", "yes"}
    if mode == "off" and not off_opt_in:
        mode = "manual"
    _default_engine = SecurityEngine(mode=mode, off_opt_in=off_opt_in)
    return _default_engine


def reset_default_engine(engine: SecurityEngine | None = None) -> None:
    """Install (or clear, with ``None``) the process-wide engine — for tests."""
    global _default_engine
    _default_engine = engine
