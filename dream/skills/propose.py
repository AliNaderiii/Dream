"""Opt-in post-task skill proposals (MEM Stage D).

Off by default.  Never fires from ``--demo``.  Rate-limited.  A proposal
is a diff that must be approved through the existing approval machinery
before anything is written; a denial discards it.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from dream.skills import edit_skill, save_skill_md
from dream.skills.registry import find_by_name
from dream.skills.store import get_ledger

_ENABLED = frozenset({"1", "true", "yes", "on"})
PROPOSAL_MIN_INTERVAL_SECONDS = 3_600
COMPLEX_TOOL_CALLS = 2
COMPLEX_MESSAGE_CHARS = 400

# Gloss: «پیشنهاد مهارت رد شد و چیزی نوشته نشد.»
_DENIED_FA = (
    "\u067e\u06cc\u0634\u0646\u0647\u0627\u062f \u0645\u0647\u0627\u0631\u062a "
    "\u0631\u062f \u0634\u062f \u0648 \u0686\u06cc\u0632\u06cc \u0646\u0648\u0634"
    "\u062a\u0647 \u0646\u0634\u062f."
)
_DENIED_EN = " Skill proposal denied; nothing was written."


@dataclass(frozen=True, slots=True)
class SkillProposal:
    """A reviewable skill create/improve that has not been written yet."""

    proposal_id: str
    name: str
    description: str
    body: str
    action: str
    created_at: float


_PENDING: dict[str, SkillProposal] = {}
_LAST_PROPOSAL_AT = 0.0
_SEQ = 0


def proposals_enabled(*, demo: bool = False) -> bool:
    if demo:
        return False
    if os.environ.get("DREAM_DEMO", "").strip().lower() in _ENABLED:
        return False
    flag = os.environ.get("DREAM_SKILL_PROPOSALS", "").strip().lower()
    return flag in _ENABLED


def is_complex_turn(message: str, tool_calls: list[dict[str, Any]]) -> bool:
    if len(tool_calls) >= COMPLEX_TOOL_CALLS:
        return True
    return len(message) >= COMPLEX_MESSAGE_CHARS


def _rate_limited() -> bool:
    if _LAST_PROPOSAL_AT <= 0:
        return False
    return (time.time() - _LAST_PROPOSAL_AT) < PROPOSAL_MIN_INTERVAL_SECONDS


def maybe_propose(
    message: str,
    tool_calls: list[dict[str, Any]],
    *,
    demo: bool = False,
) -> SkillProposal | None:
    """Return a pending proposal after a complex turn, or None."""
    global _LAST_PROPOSAL_AT, _SEQ
    if not proposals_enabled(demo=demo):
        return None
    if _rate_limited():
        return None
    if not is_complex_turn(message, tool_calls):
        return None
    # Never propose from a /learn turn — that path already writes a skill.
    if message.lstrip().lower().startswith("/learn"):
        return None
    topic = "session-procedure"
    existing = find_by_name(topic)
    action = "improve" if existing is not None else "create"
    body = (
        "## Purpose\n\n"
        "Capture a reusable procedure from a recent complex task.\n\n"
        "## Instructions\n\n"
        "1. Restate the goal in one sentence\n"
        "2. List the tools that were needed\n"
        "3. Note the approval boundary\n"
    )
    _SEQ += 1
    proposal = SkillProposal(
        proposal_id=f"prop-{_SEQ}",
        name=topic,
        description="Reusable steps from a recent complex task.",
        body=body,
        action=action,
        created_at=time.time(),
    )
    _PENDING[proposal.proposal_id] = proposal
    _LAST_PROPOSAL_AT = proposal.created_at
    try:
        with get_ledger() as ledger:
            ledger.log_use(topic, "proposed", duration_ms=0.0, source="propose")
    except Exception:
        pass
    return proposal


def get_proposal(proposal_id: str) -> SkillProposal | None:
    return _PENDING.get(proposal_id)


def list_proposals() -> list[SkillProposal]:
    """Pending proposals, oldest first — the review queue's display order."""
    return sorted(_PENDING.values(), key=lambda item: item.created_at)


def discard_proposal(proposal_id: str) -> bool:
    return _PENDING.pop(proposal_id, None) is not None


def apply_proposal(proposal_id: str) -> dict[str, Any]:
    """Write the proposal through the Stage C approved path."""
    proposal = _PENDING.pop(proposal_id, None)
    if proposal is None:
        raise ValueError("unknown or already resolved proposal")
    existing = find_by_name(proposal.name)
    if existing is not None:
        result = edit_skill(proposal.name, proposal.description, proposal.body)
        result = {**result, "status": "merged"}
    else:
        filename = save_skill_md(proposal.name, proposal.description, proposal.body)
        result = {"filename": filename, "status": "created"}
    return {
        "applied": True,
        "proposal_id": proposal_id,
        "name": proposal.name,
        **result,
    }


def reset_proposals_for_tests() -> None:
    global _LAST_PROPOSAL_AT, _SEQ
    _PENDING.clear()
    _LAST_PROPOSAL_AT = 0.0
    _SEQ = 0


def format_proposal_notice(proposal: SkillProposal) -> str:
    return (
        f"\n\n[skill proposal {proposal.proposal_id}: {proposal.action} "
        f"{proposal.name} — approve with apply_skill_proposal or deny with "
        f"discard_skill_proposal]"
    )
