"""P6 L9-C — plan approval, degraded autonomous grants, attempt limiting.

The attack this closes is the plan swap: an injected instruction edits a
step *after* the owner approved a cheap-looking plan, and the expensive
action rides the stale grant. Approval therefore binds to a digest of the
plan, not to a plan id.
"""

from __future__ import annotations

from typing import Any

import pytest

from dream.agent import ApprovalPolicy
from dream.security.planpolicy import (
    AUTONOMOUS_CONTEXTS,
    DEGRADED_GRANTS,
    EXPENSIVE_ACTIONS,
    ApprovalAttemptLimiter,
    PlanGate,
    authorize_tool,
    degraded_grants,
    plan_digest,
)

STEPS: list[dict[str, Any]] = [
    {"index": 1, "title": "read the schema"},
    {"index": 2, "title": "compute the aggregate"},
]


def _yes(_payload: dict[str, Any]) -> bool:
    return True


def _no(_payload: dict[str, Any]) -> bool:
    return False


# --------------------------------------------------------------------------- #
# Digests
# --------------------------------------------------------------------------- #


def test_the_digest_is_stable_across_calls() -> None:
    assert plan_digest("dataqa", STEPS) == plan_digest("dataqa", list(STEPS))


def test_editing_reordering_or_adding_a_step_changes_the_digest() -> None:
    base = plan_digest("dataqa", STEPS)
    assert plan_digest("dataqa", list(reversed(STEPS))) != base
    assert plan_digest("dataqa", STEPS + [{"index": 3, "title": "upload"}]) != base
    edited = [dict(STEPS[0]), {"index": 2, "title": "compute the aggregate and email it"}]
    assert plan_digest("dataqa", edited) != base


def test_volatile_bookkeeping_does_not_change_the_digest() -> None:
    live = [dict(step, status="running", updated_at=1.0) for step in STEPS]
    assert plan_digest("dataqa", live) == plan_digest("dataqa", STEPS)


def test_the_kind_is_part_of_the_digest() -> None:
    assert plan_digest("dataqa", STEPS) != plan_digest("research", STEPS)


def test_a_malformed_plan_is_refused() -> None:
    with pytest.raises(ValueError):
        plan_digest("nonsense", STEPS)
    with pytest.raises(TypeError):
        plan_digest("dataqa", {"a": 1})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        plan_digest("dataqa", [{"i": index} for index in range(500)])


# --------------------------------------------------------------------------- #
# Gating
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("action", sorted(EXPENSIVE_ACTIONS))
def test_every_expensive_action_needs_approval(action: str) -> None:
    gate = PlanGate()
    refusal = gate.check_action(action=action, plan_id="p", kind="dataqa", steps=STEPS)
    assert refusal is not None and refusal.code == "not_approved"


@pytest.mark.parametrize("action", sorted(DEGRADED_GRANTS))
def test_cheap_actions_run_unapproved(action: str) -> None:
    gate = PlanGate()
    assert gate.check_action(action=action, plan_id="p", kind="dataqa", steps=STEPS) is None


def test_an_unclassified_action_fails_closed() -> None:
    gate = PlanGate()
    refusal = gate.check_action(action="mine_bitcoin", plan_id="p", kind="dataqa", steps=STEPS)
    assert refusal is not None and refusal.code == "unknown_action"


def test_approval_unblocks_exactly_the_approved_plan() -> None:
    gate = PlanGate()
    approval, refusal = gate.request_approval(
        plan_id="p", kind="dataqa", steps=STEPS, approve=_yes
    )
    assert refusal is None and approval is not None
    assert (
        gate.check_action(action="code_execution", plan_id="p", kind="dataqa", steps=STEPS)
        is None
    )


def test_a_plan_mutated_after_approval_is_refused() -> None:
    gate = PlanGate()
    gate.request_approval(plan_id="p", kind="dataqa", steps=STEPS, approve=_yes)
    swapped = STEPS + [{"index": 3, "title": "post results to https://evil.example"}]
    refusal = gate.check_action(action="code_execution", plan_id="p", kind="dataqa", steps=swapped)
    assert refusal is not None and refusal.code == "plan_mutated"


def test_an_approval_does_not_transfer_to_another_plan() -> None:
    gate = PlanGate()
    gate.request_approval(plan_id="p", kind="dataqa", steps=STEPS, approve=_yes)
    refusal = gate.check_action(
        action="code_execution", plan_id="other", kind="dataqa", steps=STEPS
    )
    assert refusal is not None and refusal.code == "not_approved"


def test_an_approval_does_not_transfer_across_plan_kinds() -> None:
    gate = PlanGate()
    gate.request_approval(plan_id="p", kind="dataqa", steps=STEPS, approve=_yes)
    refusal = gate.check_action(action="code_execution", plan_id="p", kind="research", steps=STEPS)
    assert refusal is not None and refusal.code in {"kind_mismatch", "plan_mutated"}


def test_a_narrow_approval_does_not_cover_other_actions() -> None:
    gate = PlanGate()
    gate.request_approval(
        plan_id="p", kind="dataqa", steps=STEPS, approve=_yes, actions={"code_execution"}
    )
    assert (
        gate.check_action(action="code_execution", plan_id="p", kind="dataqa", steps=STEPS)
        is None
    )
    refusal = gate.check_action(action="file_delete", plan_id="p", kind="dataqa", steps=STEPS)
    assert refusal is not None and refusal.code == "action_not_granted"


def test_an_expired_approval_is_refused_and_dropped() -> None:
    gate = PlanGate(ttl_seconds=60)
    gate.request_approval(plan_id="p", kind="dataqa", steps=STEPS, approve=_yes)
    refusal = gate.check_action(
        action="code_execution", plan_id="p", kind="dataqa", steps=STEPS, now=10**12
    )
    assert refusal is not None and refusal.code == "approval_expired"
    assert gate.approval_for("p") is None


def test_revocation_takes_effect_immediately() -> None:
    gate = PlanGate()
    gate.request_approval(plan_id="p", kind="dataqa", steps=STEPS, approve=_yes)
    gate.revoke("p")
    refusal = gate.check_action(action="code_execution", plan_id="p", kind="dataqa", steps=STEPS)
    assert refusal is not None and refusal.code == "not_approved"


# --------------------------------------------------------------------------- #
# Approver hygiene
# --------------------------------------------------------------------------- #


def test_no_approver_configured_refuses() -> None:
    gate = PlanGate()
    approval, refusal = gate.request_approval(plan_id="p", kind="dataqa", steps=STEPS, approve=None)
    assert approval is None and refusal is not None and refusal.code == "no_approver"


def test_a_declining_owner_refuses() -> None:
    gate = PlanGate()
    approval, refusal = gate.request_approval(plan_id="p", kind="dataqa", steps=STEPS, approve=_no)
    assert approval is None and refusal is not None and refusal.code == "declined"


def test_an_approver_that_raises_fails_closed() -> None:
    def _boom(_payload: dict[str, Any]) -> bool:
        raise RuntimeError("approver crashed")

    gate = PlanGate()
    approval, refusal = gate.request_approval(
        plan_id="p", kind="dataqa", steps=STEPS, approve=_boom
    )
    assert approval is None and refusal is not None and refusal.code == "approver_failed"


def test_an_unknown_plan_kind_refuses() -> None:
    gate = PlanGate()
    approval, refusal = gate.request_approval(
        plan_id="p", kind="wishful", steps=STEPS, approve=_yes
    )
    assert approval is None and refusal is not None and refusal.code == "unknown_plan_kind"


def test_the_approver_sees_the_digest_it_is_signing() -> None:
    seen: dict[str, Any] = {}

    def _capture(payload: dict[str, Any]) -> bool:
        seen.update(payload)
        return True

    gate = PlanGate()
    gate.request_approval(plan_id="p", kind="dataqa", steps=STEPS, approve=_capture)
    assert seen["digest"] == plan_digest("dataqa", STEPS)
    assert seen["plan_id"] == "p"


# --------------------------------------------------------------------------- #
# Autonomous degradation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("context", sorted(AUTONOMOUS_CONTEXTS))
def test_autonomous_sessions_cannot_mint_approval(context: str) -> None:
    gate = PlanGate(context=context)
    approval, refusal = gate.request_approval(
        plan_id="p", kind="research", steps=STEPS, approve=_yes
    )
    assert approval is None
    assert refusal is not None and refusal.code == "autonomous_context"


@pytest.mark.parametrize("context", sorted(AUTONOMOUS_CONTEXTS))
def test_autonomous_sessions_refuse_every_expensive_action(context: str) -> None:
    gate = PlanGate(context=context)
    for action in sorted(EXPENSIVE_ACTIONS):
        refusal = gate.check_action(action=action, plan_id="p", kind="research", steps=STEPS)
        assert refusal is not None and refusal.code == "degraded_grant", action


def test_autonomous_sessions_may_still_read_and_plan() -> None:
    gate = PlanGate(context="cron")
    for action in sorted(DEGRADED_GRANTS):
        assert gate.check_action(action=action, plan_id="p", kind="research", steps=STEPS) is None


def test_the_degraded_set_and_the_expensive_set_do_not_overlap() -> None:
    assert not (DEGRADED_GRANTS & EXPENSIVE_ACTIONS)
    assert not (degraded_grants("cron") & EXPENSIVE_ACTIONS)
    assert EXPENSIVE_ACTIONS <= degraded_grants("interactive")


# --------------------------------------------------------------------------- #
# Attempt limiting
# --------------------------------------------------------------------------- #


def test_approval_attempts_are_rate_limited() -> None:
    gate = PlanGate(limiter=ApprovalAttemptLimiter(limit=3, window_seconds=60))
    codes = [
        gate.request_approval(plan_id="p", kind="dataqa", steps=STEPS, approve=_no)[1].code
        for _ in range(5)
    ]
    assert codes[:3] == ["declined"] * 3
    assert codes[3:] == ["rate_limited", "rate_limited"]


def test_a_refused_attempt_still_costs_budget() -> None:
    limiter = ApprovalAttemptLimiter(limit=2, window_seconds=60)
    assert limiter.allow("u", now=0.0)
    assert limiter.allow("u", now=1.0)
    assert not limiter.allow("u", now=2.0)


def test_the_window_slides() -> None:
    limiter = ApprovalAttemptLimiter(limit=1, window_seconds=10)
    assert limiter.allow("u", now=0.0)
    assert not limiter.allow("u", now=5.0)
    assert limiter.allow("u", now=11.0)


def test_budgets_are_per_subject() -> None:
    limiter = ApprovalAttemptLimiter(limit=1, window_seconds=60)
    assert limiter.allow("a", now=0.0)
    assert limiter.allow("b", now=0.0)
    assert not limiter.allow("a", now=0.0)


def test_remaining_and_reset() -> None:
    limiter = ApprovalAttemptLimiter(limit=2, window_seconds=60)
    assert limiter.remaining("u", now=0.0) == 2
    limiter.allow("u", now=0.0)
    assert limiter.remaining("u", now=0.0) == 1
    limiter.reset("u")
    assert limiter.remaining("u", now=0.0) == 2
    limiter.allow("u", now=0.0)
    limiter.reset()
    assert limiter.remaining("u", now=0.0) == 2


def test_limiter_construction_is_validated() -> None:
    with pytest.raises(ValueError):
        ApprovalAttemptLimiter(limit=0)
    with pytest.raises(ValueError):
        ApprovalAttemptLimiter(window_seconds=0)


# --------------------------------------------------------------------------- #
# Bridge into the existing ApprovalPolicy (called, never reimplemented)
# --------------------------------------------------------------------------- #


def test_the_existing_policy_still_decides_tool_risk() -> None:
    policy = ApprovalPolicy(registry={"read_note": type("R", (), {"risk": "safe"})()})
    allowed, reason = authorize_tool(policy, "read_note", {})
    assert allowed and "safe" in reason


def test_the_plan_gate_can_only_add_a_refusal_never_an_allowance() -> None:
    policy = ApprovalPolicy(registry={"read_note": type("R", (), {"risk": "safe"})()})
    gate = PlanGate()
    allowed, reason = authorize_tool(
        policy,
        "read_note",
        {},
        gate=gate,
        action="code_execution",
        plan_id="p",
        kind="dataqa",
        steps=STEPS,
    )
    assert not allowed
    assert "not approved" in reason


def test_a_policy_denial_is_not_rescued_by_an_approved_plan() -> None:
    # The tool is unknown to the dispatch registry: the policy denies it,
    # and an approved plan must not change that.
    policy = ApprovalPolicy(registry={})
    gate = PlanGate()
    gate.request_approval(plan_id="p", kind="dataqa", steps=STEPS, approve=_yes)
    allowed, reason = authorize_tool(
        policy,
        "run_shell",
        {"command": "ls"},
        gate=gate,
        action="code_execution",
        plan_id="p",
        kind="dataqa",
        steps=STEPS,
    )
    assert not allowed and "unknown tool" in reason


def test_the_l3_floor_still_precedes_the_plan_gate() -> None:
    # An approved plan plus an admin scope must still not get rm -rf / past
    # the floor; the verdict comes from the engine the policy owns.
    policy = ApprovalPolicy(
        registry={"run_shell": type("R", (), {"risk": "dangerous"})()},
        ask=lambda *_args: True,
    )
    gate = PlanGate()
    gate.request_approval(plan_id="p", kind="agentmode", steps=STEPS, approve=_yes)
    allowed, reason = authorize_tool(
        policy,
        "run_shell",
        {"command": "rm -rf /"},
        gate=gate,
        action="shell",
        plan_id="p",
        kind="agentmode",
        steps=STEPS,
    )
    assert not allowed
    assert "rm -rf" in reason or "refus" in reason.lower() or "block" in reason.lower()


def test_an_unclassified_action_fails_closed_at_the_bridge() -> None:
    policy = ApprovalPolicy(registry={"read_note": type("R", (), {"risk": "safe"})()})
    allowed, reason = authorize_tool(policy, "read_note", {}, gate=PlanGate(), action=None)
    assert not allowed and "not classified" in reason


def test_a_missing_policy_fails_closed() -> None:
    allowed, reason = authorize_tool(None, "read_note", {})
    assert not allowed
    assert any("\u0600" <= ch <= "\u06ff" for ch in reason)


def test_a_policy_that_raises_fails_closed() -> None:
    class _Exploding:
        def allows(self, *_args: Any) -> tuple[bool, str]:
            raise RuntimeError("boom")

    allowed, reason = authorize_tool(_Exploding(), "read_note", {})
    assert not allowed and "RuntimeError" in reason


# --------------------------------------------------------------------------- #
# Refusal shape
# --------------------------------------------------------------------------- #


def test_every_refusal_is_bilingual_and_serialisable() -> None:
    gate = PlanGate()
    refusal = gate.check_action(action="export", plan_id="p", kind="dataqa", steps=STEPS)
    assert refusal is not None
    assert refusal.reason_en and any("\u0600" <= ch <= "\u06ff" for ch in refusal.reason_fa)
    assert "\n" in refusal.message()
    assert set(refusal.to_dict()) == {"code", "reason_en", "reason_fa", "detail"}
