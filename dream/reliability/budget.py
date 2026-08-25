"""Per-turn and per-session budgets with honest bilingual exhaustion.

Budgets cover time, tokens, output size, disk, memory, and money. On
exhaustion the caller chooses to truncate, skip with a rationale, or fail
with an EN+FA message. Money is delegated to ``dream.commerce.Ledger`` —
this module calls the ledger, it does not rewrite it.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from enum import Enum
from typing import Any

__all__ = [
    "Budget",
    "BudgetExceeded",
    "BudgetKind",
    "ExhaustionAction",
    "SkipDecision",
    "SessionBudget",
    "TurnBudget",
    "attach_ledger",
    "consume_ledger_turn",
]


class BudgetKind(str, Enum):
    TIME = "time"
    TOKENS = "tokens"
    OUTPUT = "output"
    DISK = "disk"
    MEMORY = "memory"
    MONEY = "money"


class ExhaustionAction(str, Enum):
    TRUNCATE = "truncate"
    SKIP = "skip"
    FAIL = "fail"


# Gloss: «بودجهٔ زمان تمام شد.»
_FA_TIME = (
    "\u0628\u0648\u062f\u062c\u0647\u0654 \u0632\u0645\u0627\u0646 \u062a\u0645\u0627\u0645 "
    "\u0634\u062f."
)
# Gloss: «بودجهٔ توکن تمام شد.»
_FA_TOKENS = (
    "\u0628\u0648\u062f\u062c\u0647\u0654 \u062a\u0648\u06a9\u0646 \u062a\u0645\u0627\u0645 "
    "\u0634\u062f."
)
# Gloss: «بودجهٔ حجم خروجی تمام شد؛ خروجی کوتاه شد.»
_FA_OUTPUT = (
    "\u0628\u0648\u062f\u062c\u0647\u0654 \u062d\u062c\u0645 \u062e\u0631\u0648\u062c\u06cc "
    "\u062a\u0645\u0627\u0645 \u0634\u062f\u061b \u062e\u0631\u0648\u062c\u06cc "
    "\u06a9\u0648\u062a\u0627\u0647 \u0634\u062f."
)
# Gloss: «بودجهٔ دیسک تمام شد.»
_FA_DISK = (
    "\u0628\u0648\u062f\u062c\u0647\u0654 \u062f\u06cc\u0633\u06a9 \u062a\u0645\u0627\u0645 "
    "\u0634\u062f."
)
# Gloss: «بودجهٔ حافظه تمام شد.»
_FA_MEMORY = (
    "\u0628\u0648\u062f\u062c\u0647\u0654 \u062d\u0627\u0641\u0638\u0647 \u062a\u0645\u0627\u0645 "
    "\u0634\u062f."
)
# Gloss: «بودجهٔ هزینه تمام شد؛ نوبت اجرا نشد.»
_FA_MONEY = (
    "\u0628\u0648\u062f\u062c\u0647\u0654 \u0647\u0632\u06cc\u0646\u0647 \u062a\u0645\u0627\u0645 "
    "\u0634\u062f\u061b \u0646\u0648\u0628\u062a \u0627\u062c\u0631\u0627 \u0646\u0634\u062f."
)
# Gloss: «این گام رد شد چون بودجه تمام شده است.»
_FA_SKIP = (
    "\u0627\u06cc\u0646 \u06af\u0627\u0645 \u0631\u062f \u0634\u062f \u0686\u0648\u0646 "
    "\u0628\u0648\u062f\u062c\u0647 \u062a\u0645\u0627\u0645 \u0634\u062f\u0647 \u0627\u0633\u062a."
)
# Gloss: «کوتاه شد.»
_FA_TRUNCATED = "\u06a9\u0648\u062a\u0627\u0647 \u0634\u062f."
# Gloss: «اجرا نشد.»
_FA_FAILED = "\u0627\u062c\u0631\u0627 \u0646\u0634\u062f."

_FA_BY_KIND: dict[BudgetKind, str] = {
    BudgetKind.TIME: _FA_TIME,
    BudgetKind.TOKENS: _FA_TOKENS,
    BudgetKind.OUTPUT: _FA_OUTPUT,
    BudgetKind.DISK: _FA_DISK,
    BudgetKind.MEMORY: _FA_MEMORY,
    BudgetKind.MONEY: _FA_MONEY,
}

_EN_BY_KIND: dict[BudgetKind, str] = {
    BudgetKind.TIME: "Time budget exhausted",
    BudgetKind.TOKENS: "Token budget exhausted",
    BudgetKind.OUTPUT: "Output size budget exhausted; output was truncated",
    BudgetKind.DISK: "Disk budget exhausted",
    BudgetKind.MEMORY: "Memory budget exhausted",
    BudgetKind.MONEY: "Money budget exhausted; the turn was not run",
}


def _coerce_kind(kind: BudgetKind | str) -> BudgetKind:
    if isinstance(kind, BudgetKind):
        return kind
    return BudgetKind(str(kind))


def bilingual_exhaustion(
    kind: BudgetKind,
    *,
    used: float,
    limit: float,
    action: ExhaustionAction,
    owner: str = "engine",
    step: str = "step",
) -> tuple[str, str]:
    """Return ``(en, fa)`` sentences naming the exhausted budget."""
    action_en = {
        ExhaustionAction.TRUNCATE: "truncated",
        ExhaustionAction.SKIP: "skipped",
        ExhaustionAction.FAIL: "refused",
    }[action]
    action_fa = {
        ExhaustionAction.TRUNCATE: _FA_TRUNCATED,
        ExhaustionAction.SKIP: _FA_SKIP,
        ExhaustionAction.FAIL: _FA_FAILED,
    }[action]
    en = (
        f"{_EN_BY_KIND[kind]} (used {used:g} of {limit:g}) "
        f"for {owner}/{step}; this step was {action_en}."
    )
    fa = (
        f"{_FA_BY_KIND[kind]} ({used:g} \u0627\u0632 {limit:g}) "
        f"{owner}/{step}\u061b {action_fa}"
    )
    return en, fa


class BudgetExceeded(Exception):
    """A budget was exhausted. ``bilingual()`` is the user-facing text."""

    def __init__(
        self,
        message: str,
        *,
        kind: BudgetKind,
        used: float,
        limit: float,
        action: ExhaustionAction,
        message_en: str,
        message_fa: str,
        owner: str = "engine",
        step: str = "step",
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.used = used
        self.limit = limit
        self.action = action
        self.message_en = message_en
        self.message_fa = message_fa
        self.owner = owner
        self.step = step

    def bilingual(self) -> str:
        return f"{self.message_en}\n{self.message_fa}"


class SkipDecision:
    """A skipped step: nothing ran, and the rationale is honest."""

    def __init__(self, *, kind: BudgetKind, rationale_en: str, rationale_fa: str) -> None:
        self.kind = kind
        self.rationale_en = rationale_en
        self.rationale_fa = rationale_fa

    def bilingual(self) -> str:
        return f"{self.rationale_en}\n{self.rationale_fa}"


class Budget:
    """One bag of limits. Missing kinds are unlimited (``None``)."""

    def __init__(
        self,
        *,
        time_s: float | None = None,
        tokens: int | None = None,
        output_bytes: int | None = None,
        disk_bytes: int | None = None,
        memory_bytes: int | None = None,
        money: float | None = None,
        owner: str = "engine",
        step: str = "turn",
        default_action: ExhaustionAction = ExhaustionAction.FAIL,
    ) -> None:
        self.owner = owner
        self.step = step
        self.default_action = default_action
        self.started_mono = time.monotonic()
        self.limits: dict[BudgetKind, float | None] = {
            BudgetKind.TIME: time_s,
            BudgetKind.TOKENS: float(tokens) if tokens is not None else None,
            BudgetKind.OUTPUT: float(output_bytes) if output_bytes is not None else None,
            BudgetKind.DISK: float(disk_bytes) if disk_bytes is not None else None,
            BudgetKind.MEMORY: float(memory_bytes) if memory_bytes is not None else None,
            BudgetKind.MONEY: money,
        }
        self.used: dict[BudgetKind, float] = {kind: 0.0 for kind in BudgetKind}

    def remaining(self, kind: BudgetKind | str) -> float | None:
        coerced = _coerce_kind(kind)
        if coerced is BudgetKind.TIME:
            self._sync_time()
        limit = self.limits[coerced]
        if limit is None:
            return None
        return max(0.0, limit - self.used[coerced])

    def _sync_time(self) -> None:
        self.used[BudgetKind.TIME] = time.monotonic() - self.started_mono

    def _over(self, kind: BudgetKind, amount: float) -> bool:
        limit = self.limits[kind]
        if limit is None:
            return False
        return self.used[kind] + amount > limit

    def consume(
        self,
        kind: BudgetKind | str,
        amount: float,
        *,
        action: ExhaustionAction | None = None,
    ) -> float:
        """Add *amount* to *kind*. Raise or return remaining.

        Time is also sampled from the wall clock, so a long gap without an
        explicit consume still exhausts a time budget.
        """
        coerced = _coerce_kind(kind)
        if coerced is BudgetKind.TIME:
            self._sync_time()
        chosen = action or self.default_action
        quantity = max(0.0, float(amount))
        if self._over(coerced, quantity):
            self._exhaust(coerced, chosen)
        self.used[coerced] += quantity
        leftover = self.remaining(coerced)
        return leftover if leftover is not None else 0.0

    def check(self, kind: BudgetKind | str | None = None) -> None:
        """Fail if any (or the named) budget is already exhausted."""
        kinds: Iterable[BudgetKind]
        if kind is None:
            kinds = BudgetKind
        else:
            kinds = (_coerce_kind(kind),)
        if BudgetKind.TIME in kinds:
            self._sync_time()
        for item in kinds:
            limit = self.limits[item]
            if limit is not None and self.used[item] >= limit:
                self._exhaust(item, self.default_action)

    def _exhaust(self, kind: BudgetKind, action: ExhaustionAction) -> None:
        limit = self.limits[kind]
        used = self.used[kind]
        en, fa = bilingual_exhaustion(
            kind,
            used=used,
            limit=0.0 if limit is None else limit,
            action=action,
            owner=self.owner,
            step=self.step,
        )
        if action is ExhaustionAction.SKIP:
            raise BudgetExceeded(
                en,
                kind=kind,
                used=used,
                limit=0.0 if limit is None else limit,
                action=action,
                message_en=en,
                message_fa=fa,
                owner=self.owner,
                step=self.step,
            )
        if action is ExhaustionAction.TRUNCATE:
            raise BudgetExceeded(
                en,
                kind=kind,
                used=used,
                limit=0.0 if limit is None else limit,
                action=action,
                message_en=en,
                message_fa=fa,
                owner=self.owner,
                step=self.step,
            )
        raise BudgetExceeded(
            en,
            kind=kind,
            used=used,
            limit=0.0 if limit is None else limit,
            action=action,
            message_en=en,
            message_fa=fa,
            owner=self.owner,
            step=self.step,
        )

    def truncate_text(self, text: str, *, kind: BudgetKind | str = BudgetKind.OUTPUT) -> str:
        """Return *text* cut to the remaining output budget.

        Exhaustion is reported with a bilingual rationale rather than a hang.
        """
        coerced = _coerce_kind(kind)
        limit = self.limits[coerced]
        if limit is None:
            self.used[coerced] += float(len(text.encode("utf-8")))
            return text
        already = int(self.used[coerced])
        leftover = max(0, int(limit) - already)
        encoded = text.encode("utf-8")
        if len(encoded) <= leftover:
            self.used[coerced] += float(len(encoded))
            return text
        cut = encoded[:leftover].decode("utf-8", errors="ignore")
        self.used[coerced] = float(limit)
        return cut

    def skip_if_exhausted(
        self, kind: BudgetKind | str, *, rationale: str | None = None
    ) -> SkipDecision | None:
        """Return a skip decision when *kind* is exhausted, else ``None``."""
        coerced = _coerce_kind(kind)
        if coerced is BudgetKind.TIME:
            self._sync_time()
        leftover = self.remaining(coerced)
        if leftover is None or leftover > 0:
            return None
        en, fa = bilingual_exhaustion(
            coerced,
            used=self.used[coerced],
            limit=self.limits[coerced] or 0.0,
            action=ExhaustionAction.SKIP,
            owner=self.owner,
            step=self.step,
        )
        if rationale:
            en = f"{en} {rationale}"
        return SkipDecision(kind=coerced, rationale_en=en, rationale_fa=fa)

    def snapshot(self) -> dict[str, Any]:
        if self.limits[BudgetKind.TIME] is not None:
            self._sync_time()
        return {
            "owner": self.owner,
            "step": self.step,
            "used": {kind.value: self.used[kind] for kind in BudgetKind},
            "limits": {
                kind.value: self.limits[kind] for kind in BudgetKind
            },
        }


class TurnBudget(Budget):
    """Budget for a single user turn."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("step", "turn")
        super().__init__(**kwargs)


class SessionBudget(Budget):
    """Budget for a whole session (many turns)."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("step", "session")
        super().__init__(**kwargs)


def attach_ledger(budget: Budget, ledger: Any) -> None:
    """Copy the ledger's remaining turns into the money/token slot.

    Calls ``ledger.remaining()`` / ``ledger.usage()``. Does not rewrite the
    commerce module.
    """
    remaining = ledger.remaining()
    usage = ledger.usage()
    if remaining is None:
        budget.limits[BudgetKind.MONEY] = None
        return
    limit = usage.get("limit")
    used = usage.get("used", 0)
    if limit is not None:
        budget.limits[BudgetKind.MONEY] = float(limit)
        budget.used[BudgetKind.MONEY] = float(used)


def consume_ledger_turn(ledger: Any, *, amount: int = 1) -> int:
    """Call ``ledger.consume`` and map a quota refusal to :class:`BudgetExceeded`."""
    from dream.commerce import LedgerError, QuotaExceeded

    try:
        return int(ledger.consume(amount=amount))
    except QuotaExceeded as exc:
        en, fa = bilingual_exhaustion(
            BudgetKind.MONEY,
            used=0.0,
            limit=0.0,
            action=ExhaustionAction.FAIL,
            owner="commerce",
            step="ledger",
        )
        raise BudgetExceeded(
            str(exc),
            kind=BudgetKind.MONEY,
            used=0.0,
            limit=0.0,
            action=ExhaustionAction.FAIL,
            message_en=f"{en} {exc}",
            message_fa=f"{fa} {exc}",
            owner="commerce",
            step="ledger",
        ) from exc
    except LedgerError as exc:
        en, fa = bilingual_exhaustion(
            BudgetKind.MONEY,
            used=0.0,
            limit=0.0,
            action=ExhaustionAction.FAIL,
            owner="commerce",
            step="ledger",
        )
        raise BudgetExceeded(
            str(exc),
            kind=BudgetKind.MONEY,
            used=0.0,
            limit=0.0,
            action=ExhaustionAction.FAIL,
            message_en=f"{en} {exc}",
            message_fa=f"{fa} {exc}",
            owner="commerce",
            step="ledger",
        ) from exc
