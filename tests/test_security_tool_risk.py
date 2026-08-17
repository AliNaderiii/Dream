"""Tool-risk enforcement (Security audit, P-11).

Verifies the ApprovalPolicy only ever lets a tool run when its registered risk
tier permits it, and that dangerous tools are refused when no approver exists.
"""

from __future__ import annotations

from dream.agent import ApprovalPolicy
from dream.tools import REGISTRY, RISKS


def _tool_of_risk(risk: str) -> str:
    for name, registered in REGISTRY.items():
        if registered.risk == risk:
            return name
    raise AssertionError(f"no {risk!r} tool registered")


def test_every_registered_risk_is_known() -> None:
    assert set(RISKS) == {"safe", "guarded", "dangerous"}
    for name, registered in REGISTRY.items():
        assert registered.risk in RISKS, f"{name} has unknown risk {registered.risk!r}"


def test_run_shell_is_dangerous() -> None:
    assert REGISTRY["run_shell"].risk == "dangerous"


def test_safe_and_guarded_tools_auto_approve() -> None:
    policy = ApprovalPolicy()
    for risk in ("safe", "guarded"):
        allowed, _reason = policy.allows(_tool_of_risk(risk), {})
        assert allowed, f"{risk} tool should auto-approve"


def test_dangerous_tool_denied_without_approver() -> None:
    policy = ApprovalPolicy()
    allowed, reason = policy.allows("run_shell", {"command": "rm -rf /"})
    assert not allowed
    assert "no approver" in reason


def test_dangerous_tool_denied_by_disapproving_approver() -> None:
    policy = ApprovalPolicy(ask=lambda _name, _args: False)
    allowed, reason = policy.allows("run_shell", {"command": "echo hi"})
    assert not allowed
    assert "denied by approver" in reason


def test_dangerous_tool_approved_by_approver() -> None:
    policy = ApprovalPolicy(ask=lambda _name, _args: True)
    allowed, reason = policy.allows("run_shell", {"command": "echo hi"})
    assert allowed
    assert "approved" in reason


def test_unknown_tool_is_denied() -> None:
    policy = ApprovalPolicy()
    allowed, reason = policy.allows("definitely_not_a_tool", {})
    assert not allowed
    assert reason == "unknown tool"


def test_subagent_grant_registry_never_falls_back_to_global() -> None:
    """A subagent with an empty grant must not resolve risk from the global registry."""
    policy = ApprovalPolicy(registry={})
    allowed, reason = policy.allows("run_shell", {"command": "whoami"})
    assert not allowed
    assert reason == "unknown tool"
