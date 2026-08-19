"""Opt-in three-role council: proposer → critic → judge.

A council is exactly three child agents run as one ``SubAgentManager``
pipeline, in this fixed order:

1. **proposer** — answers the user's topic first, concretely;
2. **critic** — attacks the proposal: holes, false assumptions, risk
   (it does not rewrite the whole answer);
3. **judge** — given the topic, the proposal and the critique, picks or
   synthesises ONE final answer. The judge's result is the council winner.

Nothing here is a second runtime: the council reuses
:meth:`SubAgentManager.spawn_pipeline`, which already hands each stage's
result to the next stage's context. The council is strictly opt-in — the
demo, the default chat send path and a normal ``subagent.spawn`` never
start one.

Defaults keep the first run offline-green: every member defaults to the
``echo`` provider, ``allow_dangerous`` is always ``False``, and the tool
grant is :data:`dream.subagents.DEFAULT_TOOL_GRANT` only — a council child
never receives filesystem, shell, network or mail tools.

Quota: when a usage ledger is attached (same rule as ``Dream`` — a
``DREAM_PLAN`` other than ``local``, or ``DREAM_LEDGER`` set), the council
consumes its member turns **once**, up front, atomically, as one
``consume(amount=3)``; the unlimited local plan never touches a ledger
file. Children are built with an explicit no-op ledger, so a member turn
can never double-count against the same file. A refused council spawns
nothing and returns the ledger's Persian reply.

Privacy: each member record exposes ``leaves_machine``, resolved from the
member's own provider (``echo``/``ollama`` stay local; hosted, Aval and
BYOK members leave the machine), falling back to
:func:`dream.router.resolve_route` for anything else. ``leaves_machine_any``
is true when at least one member sends text off the machine, and the
result's English and Persian sentences state it honestly.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from dream.agent import build_backend
from dream.commerce import Ledger, LedgerError, ledger_attached
from dream.router import resolve_route
from dream.subagents import SubAgentManager, SubAgentSpec

__all__ = [
    "COUNCIL_MEMBER_COUNT",
    "COUNCIL_ROLES",
    "CRITIC_SYSTEM_PROMPT",
    "CouncilMember",
    "CouncilMemberSpec",
    "CouncilResult",
    "CouncilSpec",
    "JUDGE_SYSTEM_PROMPT",
    "PROPOSER_SYSTEM_PROMPT",
    "council_to_dict",
    "get_council",
    "member_to_dict",
    "run_council",
]

#: The fixed role order of a council, always three members.
COUNCIL_ROLES: tuple[str, str, str] = ("proposer", "critic", "judge")

#: Number of members a council runs — the number of turns a metered plan
#: consumes for the whole council (one ``consume(amount=N)`` before spawn).
COUNCIL_MEMBER_COUNT: int = len(COUNCIL_ROLES)

PROPOSER_SYSTEM_PROMPT = (
    "You are the proposer in a three-role council. "
    "Answer the topic directly. Be concrete and specific."
)

CRITIC_SYSTEM_PROMPT = (
    "You are the critic in a three-role council. "
    "Attack the previous answer: name its holes, false assumptions, and risks. "
    "Do not rewrite the whole answer."
)

JUDGE_SYSTEM_PROMPT = (
    "You are the judge in a three-role council. "
    "Given the topic, the proposal, and the critique, pick or synthesise "
    "ONE final answer. Do not narrate the process."
)

ROLE_SYSTEM_PROMPTS: dict[str, str] = {
    "proposer": PROPOSER_SYSTEM_PROMPT,
    "critic": CRITIC_SYSTEM_PROMPT,
    "judge": JUDGE_SYSTEM_PROMPT,
}

#: Providers whose members never send text off the machine.
_LOCAL_PROVIDERS = ("echo", "ollama")

#: Providers whose members always talk to a remote OpenAI-compatible host.
_LEAVING_PROVIDERS = ("openai", "aval", "avalai")

# Gloss: شورای سه‌نفره به پایان رسید؛ همهٔ اعضا به‌صورت محلی اجرا شدند و
# هیچ داده‌ای از این دستگاه خارج نشد.
_ALL_LOCAL_SENTENCE_FA = (
    "\u0634\u0648\u0631\u0627\u06cc\u0020\u0633\u0647\u200c\u0646\u0641\u0631\u0647\u0020"
    "\u0628\u0647\u0020\u067e\u0627\u06cc\u0627\u0646\u0020\u0631\u0633\u06cc\u062f\u061b\u0020"
    "\u0647\u0645\u0647\u0654\u0020\u0627\u0639\u0636\u0627\u0020\u0628\u0647\u200c\u0635\u0648\u0631\u062a\u0020"
    "\u0645\u062d\u0644\u06cc\u0020\u0627\u062c\u0631\u0627\u0020\u0634\u062f\u0646\u062f\u0020"
    "\u0648\u0020\u0647\u06cc\u0686\u0020\u062f\u0627\u062f\u0647\u200c\u0627\u06cc\u0020"
    "\u0627\u0632\u0020\u0627\u06cc\u0646\u0020\u062f\u0633\u062a\u06af\u0627\u0647\u0020"
    "\u062e\u0627\u0631\u062c\u0020\u0646\u0634\u062f\u002e"
)

# Gloss: شورای سه‌نفره به پایان رسید؛ یک یا چند عضو به سرویس ابری فرستاده شد و
# داده از این دستگاه خارج شد.
_SOME_REMOTE_SENTENCE_FA = (
    "\u0634\u0648\u0631\u0627\u06cc\u0020\u0633\u0647\u200c\u0646\u0641\u0631\u0647\u0020"
    "\u0628\u0647\u0020\u067e\u0627\u06cc\u0627\u0646\u0020\u0631\u0633\u06cc\u062f\u061b\u0020"
    "\u06cc\u06a9\u0020\u06cc\u0627\u0020\u0686\u0646\u062f\u0020\u0639\u0636\u0648\u0020"
    "\u0628\u0647\u0020\u0633\u0631\u0648\u06cc\u0633\u0020\u0627\u0628\u0631\u06cc\u0020"
    "\u0641\u0631\u0633\u062a\u0627\u062f\u0647\u0020\u0634\u062f\u0020\u0648\u0020"
    "\u062f\u0627\u062f\u0647\u0020\u0627\u0632\u0020\u0627\u06cc\u0646\u0020"
    "\u062f\u0633\u062a\u06af\u0627\u0647\u0020\u062e\u0627\u0631\u062c\u0020\u0634\u062f\u002e"
)

_REFUSAL_SENTENCE_EN = (
    "Council refused: the active plan's usage ledger denied the turns a "
    "council needs, so no member was spawned."
)


@dataclass(slots=True)
class CouncilMemberSpec:
    """Optional per-role model choice. Missing fields default to echo."""

    model_provider: str = "echo"
    model_name: str = ""


@dataclass(slots=True)
class CouncilSpec:
    """Everything the caller decides before a council exists."""

    prompt: str
    proposer: CouncilMemberSpec | None = None
    critic: CouncilMemberSpec | None = None
    judge: CouncilMemberSpec | None = None


@dataclass(frozen=True)
class CouncilMember:
    """One role of a council, serialised for the wire."""

    role: str
    subagent_id: str
    provider: str
    model: str
    leaves_machine: bool
    status: str = "idle"
    result: str | None = None


@dataclass(frozen=True)
class CouncilResult:
    """A snapshot of a council: its members and its winner."""

    council_id: str
    topic: str
    pipeline_id: str
    members: tuple[CouncilMember, ...]
    winner: str | None
    turns_consumed: int
    leaves_machine_any: bool
    sentence_en: str
    sentence_fa: str
    refusal: str | None = None


@dataclass(slots=True)
class _CouncilRecord:
    """Registry entry: static council facts plus the member roster."""

    council_id: str
    pipeline_id: str
    topic: str
    members: tuple[CouncilMember, ...]
    turns_consumed: int
    sentence_en: str
    sentence_fa: str


#: Process-local map council_id → record. The bridge process owns exactly one
#: manager, so this is enough for ``council.get`` to re-derive live statuses.
_COUNCIL_REGISTRY: dict[str, _CouncilRecord] = {}
_REGISTRY_LOCK = threading.Lock()


def _provider_of(config: CouncilMemberSpec | None) -> str:
    if config is None:
        return "echo"
    return (config.model_provider or "echo").strip().lower() or "echo"


def _leaves_machine(provider: str) -> bool:
    """Whether a member running on ``provider`` sends text off the machine.

    ``echo`` and ``ollama`` are explicitly local; ``openai`` (official hosted
    or BYOK) and the Aval endpoint are remote. Anything else falls back to
    the environment's resolved route — the honest answer for providers this
    module does not classify.
    """
    provider = (provider or "echo").strip().lower()
    if provider in _LOCAL_PROVIDERS:
        return False
    if provider in _LEAVING_PROVIDERS:
        return True
    return resolve_route().leaves_machine


def _consume_turns() -> tuple[int, str | None]:
    """Consume the council's member turns once on the attached ledger.

    The unlimited local plan consumes nothing and needs no ledger file. A
    refusal (quota exhausted, corrupt or misconfigured ledger) returns the
    ledger's Persian reply and means nothing was consumed or spawned.
    """
    if not ledger_attached():
        return 0, None
    try:
        Ledger().consume(amount=COUNCIL_MEMBER_COUNT)
    except LedgerError as exc:
        return 0, str(exc)
    return COUNCIL_MEMBER_COUNT, None


def _stage_spec(
    role: str, topic: str, config: CouncilMemberSpec | None, provider: str
) -> SubAgentSpec:
    """One pipeline stage. Tools stay at the default grant; no dangerous."""
    return SubAgentSpec(
        prompt=topic,
        name=role,
        system_prompt=ROLE_SYSTEM_PROMPTS[role],
        model_provider=provider,
        model_name=config.model_name if config is not None else "",
        tools=None,
        allow_dangerous=False,
    )


def _sentence_en(council_id: str, members: Sequence[CouncilMember]) -> str:
    base = (
        f"Council {council_id}: {len(members)} roles ran in the fixed order "
        "proposer, critic, judge. The judge's answer is the winner."
    )
    if any(m.leaves_machine for m in members):
        return base + (
            " One or more members sent text to a remote provider; "
            "data left this machine."
        )
    return base + " Every member ran locally; nothing left this machine."


def _sentence_fa(members: Sequence[CouncilMember]) -> str:
    if any(m.leaves_machine for m in members):
        return _SOME_REMOTE_SENTENCE_FA
    return _ALL_LOCAL_SENTENCE_FA


def _refused_result(topic: str, refusal: str) -> CouncilResult:
    """A council that never spawned: the ledger's Persian reply is returned."""
    return CouncilResult(
        council_id="",
        topic=topic,
        pipeline_id="",
        members=(),
        winner=None,
        turns_consumed=0,
        leaves_machine_any=False,
        sentence_en=_REFUSAL_SENTENCE_EN,
        sentence_fa=refusal,
        refusal=refusal,
    )


def run_council(manager: SubAgentManager, spec: CouncilSpec) -> CouncilResult:
    """Start one council on ``manager``; return its immediate snapshot.

    Opt-in only: this function is the only way a council starts. Providers
    are validated (and an unknown one refused) before any turn is consumed;
    the quota is then consumed once for all members; finally the three
    stages are queued on ``manager.spawn_pipeline``, which runs them in
    order and hands each result to the next stage's context. The winner is
    the judge's result once the judge completes; until then the snapshot
    reports ``winner=None`` — never a silent fake winner.
    """
    topic = (spec.prompt or "").strip()
    if not topic:
        raise ValueError("council topic must not be empty")
    configs: tuple[tuple[str, CouncilMemberSpec | None], ...] = (
        ("proposer", spec.proposer),
        ("critic", spec.critic),
        ("judge", spec.judge),
    )
    providers: dict[str, str] = {}
    for role, config in configs:
        provider = _provider_of(config)
        try:
            build_backend(provider)
        except ValueError:
            raise ValueError(
                f"council role {role!r} uses an unknown provider {provider!r}"
            ) from None
        providers[role] = provider

    turns, refusal = _consume_turns()
    if refusal is not None:
        return _refused_result(topic, refusal)

    specs = [_stage_spec(role, topic, config, providers[role]) for role, config in configs]
    pipeline_id, agents = manager.spawn_pipeline(specs, name="council")
    council_id = f"council_{secrets.token_hex(6)}"
    members = tuple(
        CouncilMember(
            role=role,
            subagent_id=agent.id,
            provider=agent.model_provider,
            model=agent.model_name,
            leaves_machine=_leaves_machine(providers[role]),
            status=agent.status,
            result=agent.result,
        )
        for (role, _config), agent in zip(configs, agents, strict=True)
    )
    sentence_en = _sentence_en(council_id, members)
    sentence_fa = _sentence_fa(members)
    with _REGISTRY_LOCK:
        _COUNCIL_REGISTRY[council_id] = _CouncilRecord(
            council_id=council_id,
            pipeline_id=pipeline_id,
            topic=topic,
            members=members,
            turns_consumed=turns,
            sentence_en=sentence_en,
            sentence_fa=sentence_fa,
        )
    return CouncilResult(
        council_id=council_id,
        topic=topic,
        pipeline_id=pipeline_id,
        members=members,
        winner=None,
        turns_consumed=turns,
        leaves_machine_any=any(m.leaves_machine for m in members),
        sentence_en=sentence_en,
        sentence_fa=sentence_fa,
    )


def get_council(manager: SubAgentManager, council_id: str) -> CouncilResult | None:
    """A fresh snapshot of a running or finished council, or ``None``.

    Member statuses and results are re-read from the manager, so the winner
    appears here as soon as the judge completes.
    """
    with _REGISTRY_LOCK:
        record = _COUNCIL_REGISTRY.get(council_id)
    if record is None:
        return None
    members: list[CouncilMember] = []
    for member in record.members:
        agent = manager.get(member.subagent_id)
        if agent is None:
            members.append(member)
            continue
        members.append(replace(member, status=agent.status, result=agent.result))
    roster = tuple(members)
    judge = next((m for m in roster if m.role == "judge"), None)
    winner = judge.result if judge is not None and judge.status == "completed" else None
    return CouncilResult(
        council_id=record.council_id,
        topic=record.topic,
        pipeline_id=record.pipeline_id,
        members=roster,
        winner=winner,
        turns_consumed=record.turns_consumed,
        leaves_machine_any=any(m.leaves_machine for m in roster),
        sentence_en=record.sentence_en,
        sentence_fa=record.sentence_fa,
    )


def member_to_dict(member: CouncilMember) -> dict[str, Any]:
    """Serialise one council member for the JSON-RPC wire."""
    return {
        "role": member.role,
        "subagent_id": member.subagent_id,
        "provider": member.provider,
        "model": member.model,
        "leaves_machine": member.leaves_machine,
        "status": member.status,
        "result": member.result,
    }


def council_to_dict(result: CouncilResult) -> dict[str, Any]:
    """Serialise a council snapshot for the JSON-RPC wire."""
    payload: dict[str, Any] = {
        "council_id": result.council_id,
        "pipeline_id": result.pipeline_id,
        "members": [member_to_dict(member) for member in result.members],
        "winner": result.winner,
        "turns_consumed": result.turns_consumed,
        "leaves_machine_any": result.leaves_machine_any,
        "sentence_en": result.sentence_en,
        "sentence_fa": result.sentence_fa,
    }
    if result.refusal is not None:
        payload["refusal"] = result.refusal
    return payload
