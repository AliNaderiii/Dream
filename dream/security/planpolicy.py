"""Plan-approval gating for the agentic surfaces (P6, L9-C).

A research run, a data-Q&A investigation, and a ``/plan`` agent mode all
share one shape: the model proposes a *plan*, and then something
expensive happens — many model calls, a container step, a long crawl, a
write. Before P6 the plan itself was the only gate, and a plan can be
steered by injected text.

This module adds the gate that sits between the plan and the money:

* **an approved plan is a specific plan.** Approval binds to a SHA-256
  digest over the plan's ordered steps. Mutate a step after approval —
  the classic "approve a cheap plan, run an expensive one" swap — and the
  digest no longer matches, so the run refuses.
* **expensive actions need that approval.** :data:`EXPENSIVE_ACTIONS`
  names the classes that cost time, money, or blast radius. Cheap actions
  (reading a schema, listing files) run unapproved.
* **autonomous sessions get less.** In ``cron`` and ``single_query``
  contexts there is no human to ask, so the grant set is degraded to
  :data:`DEGRADED_GRANTS` and *no* approval can be minted — a scheduled
  dream may plan, but it may not spend.
* **approval attempts are rate limited.** A prompt-injection loop that
  keeps re-asking burns its budget and then gets refused.

The module **calls** :class:`dream.agent.ApprovalPolicy` for tool-level
decisions rather than reimplementing it, so the L3 floor still precedes
every gate here. Nothing in ``dream/agent.py`` is modified.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "AUTONOMOUS_CONTEXTS",
    "DEGRADED_GRANTS",
    "EXPENSIVE_ACTIONS",
    "PLAN_KINDS",
    "ApprovalAttemptLimiter",
    "PlanApproval",
    "PlanGate",
    "PlanRefusal",
    "authorize_tool",
    "degraded_grants",
    "plan_digest",
]

PLAN_KINDS: tuple[str, ...] = ("research", "dataqa", "agentmode")

#: Contexts with no human present. Approval cannot be minted in these.
AUTONOMOUS_CONTEXTS: frozenset[str] = frozenset({"cron", "single_query", "autonomous"})

#: Action classes that must not start on an unapproved plan. Each is a
#: coarse capability name, not a tool name, so a new tool inherits the gate
#: by being classified rather than by being remembered.
EXPENSIVE_ACTIONS: frozenset[str] = frozenset(
    {
        "code_execution",  # container step for generated code
        "long_run",  # multi-minute loop (research iterate, deep crawl)
        "network_fetch",  # outbound reads beyond a configured endpoint
        "bulk_model_calls",  # fan-out over sections/questions
        "file_write",  # anything durable on the owner's disk
        "file_delete",
        "shell",  # !shell and run_shell paths
        "provider_probe",  # gateway/provider round trips
        "export",  # report/bundle generation
    }
)

#: What an autonomous session may still do without a human. Deliberately
#: read-only and bounded: plan, read, summarise — never spend or mutate.
DEGRADED_GRANTS: frozenset[str] = frozenset(
    {
        "plan",
        "read_schema",
        "read_file",
        "list_files",
        "summarize",
        "status",
    }
)

_MAX_STEPS = 200
_MAX_STEP_CHARS = 2_000


@dataclass(frozen=True)
class PlanRefusal:
    """A fail-closed plan-gate refusal, in both languages."""

    code: str
    reason_en: str
    reason_fa: str
    detail: str = ""

    def message(self) -> str:
        tail = f" ({self.detail})" if self.detail else ""
        return f"{self.reason_en}{tail}\n{self.reason_fa}{tail}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "reason_en": self.reason_en,
            "reason_fa": self.reason_fa,
            "detail": self.detail,
        }


def _refuse(code: str, en: str, fa: str, detail: str = "") -> PlanRefusal:
    return PlanRefusal(code=code, reason_en=en, reason_fa=fa, detail=detail)


def plan_digest(kind: str, steps: list[Any]) -> str:
    """A stable SHA-256 over a plan's kind and ordered steps.

    The digest is what approval binds to. Reordering, adding, editing, or
    dropping a step changes it, so a post-approval mutation cannot ride a
    stale grant.
    """
    if kind not in PLAN_KINDS:
        raise ValueError(f"plan kind must be one of {PLAN_KINDS}, got {kind!r}")
    if not isinstance(steps, list):
        raise TypeError("steps must be a list")
    if len(steps) > _MAX_STEPS:
        raise ValueError(f"a plan may not exceed {_MAX_STEPS} steps")
    normalized = [_normalize_step(step) for step in steps]
    blob = json.dumps(
        {"kind": kind, "steps": normalized}, ensure_ascii=False, sort_keys=True, default=str
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _normalize_step(step: Any) -> Any:
    if isinstance(step, dict):
        return {
            str(key): _normalize_step(value)
            for key, value in sorted(step.items(), key=lambda pair: str(pair[0]))
            # Volatile bookkeeping must not change the digest, or every
            # status tick would invalidate a live approval.
            if str(key) not in {"updated_at", "created_at", "elapsed", "status"}
        }
    if isinstance(step, (list, tuple)):
        return [_normalize_step(item) for item in step]
    if isinstance(step, str):
        return step.strip()[:_MAX_STEP_CHARS]
    if step is None or isinstance(step, (bool, int, float)):
        return step
    return str(step)[:_MAX_STEP_CHARS]


def degraded_grants(context: str) -> frozenset[str]:
    """The grant set for *context* — degraded whenever no human is present."""
    if context in AUTONOMOUS_CONTEXTS:
        return DEGRADED_GRANTS
    return DEGRADED_GRANTS | EXPENSIVE_ACTIONS


# --------------------------------------------------------------------------- #
# Attempt limiting
# --------------------------------------------------------------------------- #


class ApprovalAttemptLimiter:
    """Sliding-window limiter for plan-approval attempts per subject.

    Mirrors the Stage E per-user approval throttle in shape: a refused
    attempt still costs budget, because the cost being defended against is
    the *asking*, not the granting.
    """

    def __init__(self, *, limit: int = 5, window_seconds: float = 60.0) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = int(limit)
        self.window_seconds = float(window_seconds)
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.RLock()

    def allow(self, subject: str, *, now: float | None = None) -> bool:
        """Spend one unit of *subject*'s budget; ``False`` when exhausted."""
        stamp = time.monotonic() if now is None else float(now)
        key = str(subject or "anonymous")
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            cutoff = stamp - self.window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(stamp)
            return True

    def remaining(self, subject: str, *, now: float | None = None) -> int:
        stamp = time.monotonic() if now is None else float(now)
        key = str(subject or "anonymous")
        with self._lock:
            bucket = self._hits.get(key)
            if not bucket:
                return self.limit
            cutoff = stamp - self.window_seconds
            live = sum(1 for hit in bucket if hit > cutoff)
            return max(0, self.limit - live)

    def reset(self, subject: str | None = None) -> None:
        with self._lock:
            if subject is None:
                self._hits.clear()
            else:
                self._hits.pop(str(subject), None)


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PlanApproval:
    """One human grant, bound to a specific plan digest."""

    plan_id: str
    kind: str
    digest: str
    approved_at: float
    approver: str = "owner"
    ttl_seconds: float = 900.0
    actions: frozenset[str] = field(default_factory=lambda: EXPENSIVE_ACTIONS)

    def expired(self, *, now: float | None = None) -> bool:
        stamp = time.time() if now is None else float(now)
        return stamp - self.approved_at > self.ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "kind": self.kind,
            "digest": self.digest,
            "approved_at": self.approved_at,
            "approver": self.approver,
            "ttl_seconds": self.ttl_seconds,
            "actions": sorted(self.actions),
        }


class PlanGate:
    """Approval state for plans, and the check every expensive action runs."""

    def __init__(
        self,
        *,
        context: str = "interactive",
        limiter: ApprovalAttemptLimiter | None = None,
        ttl_seconds: float = 900.0,
    ) -> None:
        self.context = str(context or "interactive")
        self.limiter = limiter or ApprovalAttemptLimiter()
        self.ttl_seconds = float(ttl_seconds)
        self._approvals: dict[str, PlanApproval] = {}
        self._lock = threading.RLock()

    # -- minting ---------------------------------------------------------- #

    def request_approval(
        self,
        *,
        plan_id: str,
        kind: str,
        steps: list[Any],
        approve: Any = None,
        subject: str | None = None,
        actions: frozenset[str] | set[str] | None = None,
    ) -> tuple[PlanApproval | None, PlanRefusal | None]:
        """Ask for approval of one plan. Returns ``(approval, refusal)``.

        Fail-closed in every ambiguous case: an autonomous context, a
        missing approver, an exhausted attempt budget, a malformed plan, or
        an approver that raises all produce a refusal and no grant.
        """
        if kind not in PLAN_KINDS:
            return None, _refuse(
                "unknown_plan_kind",
                f"approval refused: {kind!r} is not a known plan kind",
                f"تأیید رد شد: {kind!r} نوع نقشهٔ شناخته‌شده‌ای نیست",
            )
        if self.context in AUTONOMOUS_CONTEXTS:
            return None, _refuse(
                "autonomous_context",
                "approval refused: an autonomous session has no owner present to approve; "
                "it runs with a degraded grant set",
                "تأیید رد شد: در جلسهٔ خودکار مالکی برای تأیید حاضر نیست؛ "
                "این جلسه با مجموعهٔ اختیارات کاهش‌یافته اجرا می‌شود",
            )
        if not self.limiter.allow(subject or plan_id):
            return None, _refuse(
                "rate_limited",
                "approval refused: too many approval attempts; wait before asking again",
                "تأیید رد شد: تلاش‌های تأیید بیش از حد است؛ پیش از درخواست دوباره صبر کنید",
            )
        try:
            digest = plan_digest(kind, steps)
        except (TypeError, ValueError) as exc:
            return None, _refuse(
                "malformed_plan",
                "approval refused: the plan could not be fingerprinted",
                "تأیید رد شد: اثر انگشت نقشه ساخته نشد",
                detail=str(exc)[:100],
            )
        if approve is None:
            return None, _refuse(
                "no_approver",
                "approval refused: no approver is configured for this session",
                "تأیید رد شد: برای این جلسه تأییدکننده‌ای تنظیم نشده است",
            )
        try:
            granted = bool(approve({"plan_id": plan_id, "kind": kind, "digest": digest}))
        except Exception as exc:  # approver is caller-supplied: never trust it
            return None, _refuse(
                "approver_failed",
                "approval refused: the approver did not answer cleanly",
                "تأیید رد شد: تأییدکننده پاسخ درستی نداد",
                detail=type(exc).__name__,
            )
        if not granted:
            return None, _refuse(
                "declined",
                "approval refused: the owner declined this plan",
                "تأیید رد شد: مالک این نقشه را نپذیرفت",
            )
        approval = PlanApproval(
            plan_id=str(plan_id),
            kind=kind,
            digest=digest,
            approved_at=time.time(),
            ttl_seconds=self.ttl_seconds,
            actions=frozenset(actions) if actions else EXPENSIVE_ACTIONS,
        )
        with self._lock:
            self._approvals[str(plan_id)] = approval
        return approval, None

    def revoke(self, plan_id: str) -> None:
        with self._lock:
            self._approvals.pop(str(plan_id), None)

    def approval_for(self, plan_id: str) -> PlanApproval | None:
        with self._lock:
            return self._approvals.get(str(plan_id))

    # -- enforcement ------------------------------------------------------ #

    def check_action(
        self,
        *,
        action: str,
        plan_id: str,
        kind: str,
        steps: list[Any],
        now: float | None = None,
    ) -> PlanRefusal | None:
        """``None`` when this action may run, otherwise the refusal.

        Cheap actions pass without approval. Expensive ones require a live
        approval whose digest still matches the plan being executed.
        """
        name = str(action or "")
        if name not in EXPENSIVE_ACTIONS:
            if name in DEGRADED_GRANTS:
                return None
            return _refuse(
                "unknown_action",
                f"refused: {name!r} is not a classified action, so Dream cannot judge its cost",
                f"رد شد: {name!r} کنش دسته‌بندی‌شده نیست، پس هزینهٔ آن قابل داوری نیست",
            )
        if self.context in AUTONOMOUS_CONTEXTS:
            return _refuse(
                "degraded_grant",
                f"refused: {name!r} is outside the degraded grant set an autonomous "
                "session runs with",
                f"رد شد: {name!r} بیرون از مجموعهٔ اختیارات کاهش‌یافتهٔ جلسهٔ خودکار است",
            )
        approval = self.approval_for(plan_id)
        if approval is None:
            return _refuse(
                "not_approved",
                f"refused: {name!r} is an expensive action and this plan is not approved",
                f"رد شد: {name!r} کنشی پرهزینه است و این نقشه تأیید نشده است",
            )
        if approval.expired(now=now):
            self.revoke(plan_id)
            return _refuse(
                "approval_expired",
                "refused: the approval for this plan has expired; ask again",
                "رد شد: تأیید این نقشه منقضی شده است؛ دوباره درخواست کنید",
            )
        if approval.kind != kind:
            return _refuse(
                "kind_mismatch",
                "refused: the approval was granted for a different plan kind",
                "رد شد: تأیید برای نوع دیگری از نقشه صادر شده بود",
            )
        try:
            current = plan_digest(kind, steps)
        except (TypeError, ValueError) as exc:
            return _refuse(
                "malformed_plan",
                "refused: the plan could not be fingerprinted at execution time",
                "رد شد: هنگام اجرا اثر انگشت نقشه ساخته نشد",
                detail=str(exc)[:100],
            )
        if current != approval.digest:
            return _refuse(
                "plan_mutated",
                "refused: the plan changed after it was approved; approve the new plan",
                "رد شد: نقشه پس از تأیید تغییر کرده است؛ نقشهٔ تازه را تأیید کنید",
            )
        if name not in approval.actions:
            return _refuse(
                "action_not_granted",
                f"refused: the approval does not cover {name!r}",
                f"رد شد: تأیید صادرشده شامل {name!r} نیست",
            )
        return None


# --------------------------------------------------------------------------- #
# Tool-level bridge into the existing approval engine
# --------------------------------------------------------------------------- #


def authorize_tool(
    policy: Any,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    gate: PlanGate | None = None,
    action: str | None = None,
    plan_id: str | None = None,
    kind: str | None = None,
    steps: list[Any] | None = None,
) -> tuple[bool, str]:
    """Plan gate first, then the existing :class:`ApprovalPolicy`.

    The tool-level verdict is produced by *policy* — this function never
    re-implements risk tiers, scopes, or the L3 floor; it calls the engine
    that owns them. The plan gate is an additional refusal, never a way to
    turn a policy denial into an allowance.
    """
    if policy is None or not hasattr(policy, "allows"):
        return False, (
            "refused: no approval policy is configured\n"
            "رد شد: سیاست تأییدی تنظیم نشده است"
        )
    if gate is not None:
        if action is None:
            return False, (
                "refused: the action was not classified, so the plan gate fails closed\n"
                "رد شد: کنش دسته‌بندی نشد، پس دروازهٔ نقشه بسته می‌ماند"
            )
        refusal = gate.check_action(
            action=action,
            plan_id=str(plan_id or ""),
            kind=str(kind or "agentmode"),
            steps=list(steps or []),
        )
        if refusal is not None:
            return False, refusal.message()
    try:
        allowed, reason = policy.allows(str(tool_name), dict(arguments or {}))
    except Exception as exc:
        return False, (
            f"refused: the approval policy raised {type(exc).__name__}\n"
            f"رد شد: سیاست تأیید خطای {type(exc).__name__} داد"
        )
    return bool(allowed), str(reason)
