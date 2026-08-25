"""Reliability toolkit: nothing hangs forever.

Every blocked path yields a result, a controlled failure, or a clear
cancelled / timed-out / stalled signal. Resources are reaped. Lists stay
bounded. Public waits are hard-capped.

The graceful-degradation ladder lives here so owners can step
``full → reduced → offline/echo → honest error`` and log where/why in
English and Persian.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any

from dream.reliability.backpressure import (
    DEFAULT_BUFFER,
    MAX_BUFFER,
    BackpressureError,
    BoundedBuffer,
    BoundedList,
    OverflowPolicy,
)
from dream.reliability.budget import (
    Budget,
    BudgetExceeded,
    BudgetKind,
    ExhaustionAction,
    SessionBudget,
    SkipDecision,
    TurnBudget,
    attach_ledger,
    consume_ledger_turn,
)
from dream.reliability.cancel import (
    MAX_WAIT_SECONDS,
    CancelToken,
    OperationCancelled,
    adapt_agentmodes,
    adapt_research_stop,
    clamp_wait,
)
from dream.reliability.db import (
    begin_immediate,
    claim_delivery,
    connect_sqlite,
    durable_write,
    ensure_delivery_schema,
    run_transaction,
)
from dream.reliability.deadline import (
    MAX_DEADLINE_SECONDS,
    MAX_STEP_DELAY_SECONDS,
    MAX_TIMEOUT_SECONDS,
    Deadline,
    DeadlineExceeded,
    Watchdog,
    clamp_delay,
    clamp_timeout,
)
from dream.reliability.resource import (
    BACKOFF_SECONDS,
    MAX_RESTARTS,
    ResourceSupervisor,
    SupervisedWorker,
    WorkerStatus,
)
from dream.reliability.streams import (
    DEFAULT_STALL_TIMEOUT,
    HEARTBEAT_MARK,
    StreamStalledError,
    guarded_aiter,
    terminating_aiter,
)

logger = logging.getLogger("dream.reliability")

__all__ = [
    "BACKOFF_SECONDS",
    "DEFAULT_BUFFER",
    "DEFAULT_STALL_TIMEOUT",
    "HEARTBEAT_MARK",
    "MAX_BUFFER",
    "MAX_DEADLINE_SECONDS",
    "MAX_RESTARTS",
    "MAX_STEP_DELAY_SECONDS",
    "MAX_TIMEOUT_SECONDS",
    "MAX_WAIT_SECONDS",
    "BackpressureError",
    "BoundedBuffer",
    "BoundedList",
    "Budget",
    "BudgetExceeded",
    "BudgetKind",
    "CancelToken",
    "Deadline",
    "DeadlineExceeded",
    "Degradation",
    "DegradationLevel",
    "ExhaustionAction",
    "OperationCancelled",
    "OverflowPolicy",
    "ResourceSupervisor",
    "SessionBudget",
    "SkipDecision",
    "StreamStalledError",
    "SupervisedWorker",
    "TurnBudget",
    "Watchdog",
    "WorkerStatus",
    "adapt_agentmodes",
    "adapt_research_stop",
    "attach_ledger",
    "begin_immediate",
    "claim_delivery",
    "clamp_delay",
    "clamp_timeout",
    "clamp_wait",
    "connect_sqlite",
    "consume_ledger_turn",
    "durable_write",
    "ensure_delivery_schema",
    "guarded_aiter",
    "run_transaction",
    "terminating_aiter",
]


class DegradationLevel(str, Enum):
    """The four rungs. Owners step down; they never step back up silently."""

    FULL = "full"
    REDUCED = "reduced"
    OFFLINE_ECHO = "offline_echo"
    HONEST_ERROR = "honest_error"


_LADDER: tuple[DegradationLevel, ...] = (
    DegradationLevel.FULL,
    DegradationLevel.REDUCED,
    DegradationLevel.OFFLINE_ECHO,
    DegradationLevel.HONEST_ERROR,
)

# Gloss: «در حال اجرا با توان کامل.»
_FA_FULL = (
    "\u062f\u0631 \u062d\u0627\u0644 \u0627\u062c\u0631\u0627 \u0628\u0627 "
    "\u062a\u0648\u0627\u0646 \u06a9\u0627\u0645\u0644."
)
# Gloss: «به حالت کاهش‌یافته رفت: کار پرهزینه رد می‌شود.»
_FA_REDUCED = (
    "\u0628\u0647 \u062d\u0627\u0644\u062a "
    "\u06a9\u0627\u0647\u0634\u200c\u06cc\u0627\u0641\u062a\u0647 "
    "\u0631\u0641\u062a: \u06a9\u0627\u0631 "
    "\u067e\u0631\u0647\u0632\u06cc\u0646\u0647 \u0631\u062f "
    "\u0645\u06cc\u200c\u0634\u0648\u062f."
)
# Gloss: «به حالت پژواک آفلاین رفت: هیچ درخواستی به ارائه‌دهنده فرستاده نمی‌شود.»
_FA_OFFLINE = (
    "\u0628\u0647 \u062d\u0627\u0644\u062a "
    "\u067e\u0698\u0648\u0627\u06a9 \u0622\u0641\u0644\u0627\u06cc\u0646 "
    "\u0631\u0641\u062a: \u0647\u06cc\u0686 "
    "\u062f\u0631\u062e\u0648\u0627\u0633\u062a\u06cc \u0628\u0647 "
    "\u0627\u0631\u0627\u0626\u0647\u200c\u062f\u0647\u0646\u062f\u0647 "
    "\u0641\u0631\u0633\u062a\u0627\u062f\u0647 "
    "\u0646\u0645\u06cc\u200c\u0634\u0648\u062f."
)
# Gloss: «با خطای صادقانه متوقف شد: موتور نمی‌تواند ایمن ادامه دهد.»
_FA_ERROR = (
    "\u0628\u0627 \u062e\u0637\u0627\u06cc "
    "\u0635\u0627\u062f\u0642\u0627\u0646\u0647 \u0645\u062a\u0648\u0642\u0641 "
    "\u0634\u062f: \u0645\u0648\u062a\u0648\u0631 "
    "\u0646\u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u062f "
    "\u0627\u06cc\u0645\u0646 \u0627\u062f\u0627\u0645\u0647 \u062f\u0647\u062f."
)

_EN: dict[DegradationLevel, str] = {
    DegradationLevel.FULL: "Running at full capability.",
    DegradationLevel.REDUCED: (
        "Degraded to reduced mode: expensive work is skipped."
    ),
    DegradationLevel.OFFLINE_ECHO: (
        "Degraded to offline echo: no provider call will be made."
    ),
    DegradationLevel.HONEST_ERROR: (
        "Stopped with an honest error: the engine cannot continue safely."
    ),
}

_FA: dict[DegradationLevel, str] = {
    DegradationLevel.FULL: _FA_FULL,
    DegradationLevel.REDUCED: _FA_REDUCED,
    DegradationLevel.OFFLINE_ECHO: _FA_OFFLINE,
    DegradationLevel.HONEST_ERROR: _FA_ERROR,
}


class Degradation:
    """The graceful-degradation ladder, with an EN+FA log of every step."""

    def __init__(self, level: DegradationLevel = DegradationLevel.FULL) -> None:
        self.level = level
        self.history: list[dict[str, Any]] = []

    def message(self) -> dict[str, str]:
        return {"en": _EN[self.level], "fa": _FA[self.level]}

    def bilingual(self) -> str:
        text = self.message()
        return f"{text['en']}\n{text['fa']}"

    def step_down(self, reason: str, *, detail: str | None = None) -> DegradationLevel:
        """Move one rung down and log where/why in English and Persian."""
        index = _LADDER.index(self.level)
        if index + 1 < len(_LADDER):
            self.level = _LADDER[index + 1]
        entry = {
            "level": self.level.value,
            "reason": reason,
            "detail": detail,
            "at": time.time(),
            "message_en": _EN[self.level],
            "message_fa": _FA[self.level],
        }
        self.history.append(entry)
        logger.warning(
            "degraded to %s because %s (%s) / %s",
            self.level.value,
            reason,
            _EN[self.level],
            _FA[self.level],
        )
        return self.level

    def fail(self, reason: str, *, detail: str | None = None) -> DegradationLevel:
        """Jump to the honest-error rung."""
        while self.level is not DegradationLevel.HONEST_ERROR:
            self.step_down(reason, detail=detail)
        return self.level

    def snapshot(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "message": self.message(),
            "history": list(self.history),
        }
