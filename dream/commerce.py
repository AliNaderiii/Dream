"""Commercial kernel: plans, pricing, and the JSON usage ledger.

S00 scope, kept deliberately small and honest:

- Seven plans: ``local`` (unlimited, free), ``guest`` (free daily quota),
  ``daily``, ``individual_monthly``, ``individual_yearly``, ``team``, and
  ``company``.
- The currency field is always IRR (Iranian rial). Only the two free plans
  carry a numeric price (0). Paid plans carry ``price=None`` and a note that
  the price is TBD after cost measurement: we will not invent numbers.
- A JSON usage ledger records one entry per consumed turn. A ledger is
  attached when ``DREAM_PLAN`` is set to anything other than ``local``, or
  when ``DREAM_LEDGER`` names a file. ``local`` never needs a ledger file.
- Fail-closed metering: when a metered plan is active and the ledger file is
  missing-parseable-but-corrupt (unreadable, invalid JSON, or malformed
  entries), a turn is refused instead of being granted for free. Corruption
  never silently turns into unlimited usage.

The module is stdlib-only, like the rest of ``dream/``.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

IRR = "IRR"

# Default ledger location when a metered plan is active and DREAM_LEDGER is
# not set. ``local`` never touches this file.
DEFAULT_LEDGER_PATH = "data/dream-ledger.json"

LEDGER_VERSION = 1

# Quota placeholders for the metered plans. These are capacity limits, not
# prices: the exact figures will be tuned after cost measurement and are kept
# in one place so the tuning is a one-line change per plan.
GUEST_DAILY_LIMIT = 20
DAILY_DAILY_LIMIT = 100
INDIVIDUAL_MONTHLY_LIMIT = 1000
INDIVIDUAL_YEARLY_LIMIT = 12000
TEAM_MONTHLY_LIMIT = 5000
COMPANY_MONTHLY_LIMIT = 20000

TBD_NOTE = "TBD after cost measurement"


@dataclass(frozen=True)
class Plan:
    """One commercial plan. ``price`` is in IRR; ``None`` means undecided."""

    id: str
    name_fa: str
    currency: str
    price: int | None
    price_note: str
    metered: bool
    daily_limit: int | None = None
    monthly_limit: int | None = None
    yearly_limit: int | None = None


PLANS: dict[str, Plan] = {
    "local": Plan(
        id="local",
        name_fa="\u0645\u062d\u0644\u06cc",
        currency=IRR,
        price=0,
        price_note="free — unlimited",
        metered=False,
    ),
    "guest": Plan(
        id="guest",
        name_fa="\u0645\u0647\u0645\u0627\u0646",
        currency=IRR,
        price=0,
        price_note="free — limited daily quota",
        metered=True,
        daily_limit=GUEST_DAILY_LIMIT,
    ),
    "daily": Plan(
        id="daily",
        name_fa="\u0631\u0648\u0632\u0627\u0646\u0647",
        currency=IRR,
        price=None,
        price_note=TBD_NOTE,
        metered=True,
        daily_limit=DAILY_DAILY_LIMIT,
    ),
    "individual_monthly": Plan(
        id="individual_monthly",
        name_fa="\u0645\u0627\u0647\u0627\u0646\u0647 \u0641\u0631\u062f\u06cc",
        currency=IRR,
        price=None,
        price_note=TBD_NOTE,
        metered=True,
        monthly_limit=INDIVIDUAL_MONTHLY_LIMIT,
    ),
    "individual_yearly": Plan(
        id="individual_yearly",
        name_fa="\u0633\u0627\u0644\u0627\u0646\u0647 \u0641\u0631\u062f\u06cc",
        currency=IRR,
        price=None,
        price_note=TBD_NOTE,
        metered=True,
        yearly_limit=INDIVIDUAL_YEARLY_LIMIT,
    ),
    "team": Plan(
        id="team",
        name_fa="\u062a\u06cc\u0645",
        currency=IRR,
        price=None,
        price_note=TBD_NOTE,
        metered=True,
        monthly_limit=TEAM_MONTHLY_LIMIT,
    ),
    "company": Plan(
        id="company",
        name_fa="\u0633\u0627\u0632\u0645\u0627\u0646",
        currency=IRR,
        price=None,
        price_note=TBD_NOTE,
        metered=True,
        monthly_limit=COMPANY_MONTHLY_LIMIT,
    ),
}


class LedgerError(RuntimeError):
    """Base class for every ledger refusal; the message is user-facing."""


class LedgerConfigurationError(LedgerError):
    """The active plan name is unknown or the ledger is misconfigured."""


class LedgerCorruptionError(LedgerError):
    """The ledger file exists but cannot be trusted (fail-closed)."""


class QuotaExceeded(LedgerError):
    """The plan's quota for the current window is exhausted."""


# Gloss: برنامه ناشناخته است؛ برای جلوگیری از مصرف بی‌حساب، این نوبت اجرا نشد.
_UNKNOWN_PLAN = (
    "\u0628\u0631\u0646\u0627\u0645\u0647 \u0646\u0627\u0634\u0646\u0627\u062e\u062a\u0647 "
    "\u0627\u0633\u062a\u061b \u0628\u0631\u0627\u06cc \u062c\u0644\u0648\u06af\u06cc\u0631\u06cc "
    "\u0627\u0632 \u0645\u0635\u0631\u0641 \u0628\u06cc\u200c\u062d\u0633\u0627\u0628\u060c "
    "\u0627\u06cc\u0646 \u0646\u0648\u0628\u062a \u0627\u062c\u0631\u0627 \u0646\u0634\u062f. "
    "\u0646\u0627\u0645 \u0628\u0631\u0646\u0627\u0645\u0647 \u0631\u0627 \u062f\u0631 "
    "DREAM_PLAN \u0628\u0631\u0631\u0633\u06cc \u06a9\u0646\u06cc\u062f."
)

# Gloss: فایل دفترچه مصرف خراب است؛ برای جلوگیری از مصرف بی‌حساب، این نوبت اجرا نشد.
_CORRUPT_LEDGER = (
    "\u0641\u0627\u06cc\u0644 \u062f\u0641\u062a\u0631\u0686\u0647 \u0645\u0635\u0631\u0641 "
    "\u062e\u0631\u0627\u0628 \u0627\u0633\u062a \u0648 \u0642\u0627\u0628\u0644 "
    "\u062e\u0648\u0627\u0646\u062f\u0646 \u0646\u06cc\u0633\u062a\u061b "
    "\u0628\u0631\u0627\u06cc \u062c\u0644\u0648\u06af\u06cc\u0631\u06cc \u0627\u0632 "
    "\u0645\u0635\u0631\u0641 \u0628\u06cc\u200c\u062d\u0633\u0627\u0628\u060c "
    "\u0627\u06cc\u0646 \u0646\u0648\u0628\u062a \u0627\u062c\u0631\u0627 \u0646\u0634\u062f. "
    "\u0641\u0627\u06cc\u0644 \u0631\u0627 \u062a\u0639\u0645\u06cc\u0631 \u06a9\u0646\u06cc\u062f "
    "\u06cc\u0627 DREAM_LEDGER \u0631\u0627 \u0628\u0647 \u06cc\u06a9 \u0641\u0627\u06cc\u0644 "
    "\u062a\u0627\u0632\u0647 \u062a\u063a\u06cc\u06cc\u0631 \u062f\u0647\u06cc\u062f."
)


def _quota_message(plan: Plan, limit: int, used: int) -> str:
    """A Persian quota sentence naming the plan and its window limit."""
    window = (
        "\u0627\u0645\u0631\u0648\u0632"
        if plan.daily_limit is not None
        else "\u0627\u06cc\u0646 \u0645\u0627\u0647"
        if plan.monthly_limit is not None
        else "\u0627\u0645\u0633\u0627\u0644"
        if plan.yearly_limit is not None
        else "\u0627\u06cc\u0646 \u062f\u0648\u0631\u0647"
    )
    # Gloss: سهمیه برنامه «مهمان» برای امروز (۲۰ نوبت) تمام شده است؛ این نوبت
    # مصرف نشد. فردا دوباره تلاش کنید یا یک برنامه پولی بخرید.
    return (
        "\u0633\u0647\u0645\u06cc\u0647 \u0628\u0631\u0646\u0627\u0645\u0647 \u00ab"
        f"{plan.name_fa}"
        "\u00bb \u0628\u0631\u0627\u06cc "
        f"{window} ({limit} \u0646\u0648\u0628\u062a) "
        "\u062a\u0645\u0627\u0645 \u0634\u062f\u0647 \u0627\u0633\u062a\u061b "
        "\u0627\u06cc\u0646 \u0646\u0648\u0628\u062a \u0645\u0635\u0631\u0641 \u0646\u0634\u062f. "
        "\u0641\u0631\u062f\u0627 \u062f\u0648\u0628\u0627\u0631\u0647 \u062a\u0644\u0627\u0634 "
        "\u06a9\u0646\u06cc\u062f \u06cc\u0627 \u06cc\u06a9 \u0628\u0631\u0646\u0627\u0645\u0647 "
        "\u067e\u0648\u0644\u06cc \u0628\u062e\u0631\u06cc\u062f."
    )


def _resolve_plan() -> Plan:
    """Resolve the active plan from ``DREAM_PLAN`` (default ``local``)."""
    name = (os.environ.get("DREAM_PLAN", "local") or "local").strip().lower()
    plan = PLANS.get(name)
    if plan is None:
        raise LedgerConfigurationError(_UNKNOWN_PLAN)
    return plan


def ledger_attached() -> bool:
    """True when a ledger is attached: metered plan or explicit path.

    ``Dream.run`` consumes a turn only when this returns true, so the
    unlimited local plan runs with no ledger file at all.
    """
    plan = (os.environ.get("DREAM_PLAN", "local") or "local").strip().lower()
    if plan != "local":
        return True
    return bool((os.environ.get("DREAM_LEDGER") or "").strip())


def active_plan() -> Plan:
    """Return the active plan, raising ``LedgerConfigurationError`` on an
    unknown name so a typo is never silently billed as another plan."""
    return _resolve_plan()


class Ledger:
    """A JSON usage ledger on disk with fail-closed reads.

    One entry is appended per consumed turn. Entries carry an ISO-8601
    timestamp; the quota window is the local calendar day, month, or year
    according to the plan. Writes are atomic (temp file + ``os.replace``) so
    a crash never leaves a torn ledger.
    """

    def __init__(self, path: str | os.PathLike[str] | None = None, plan: str | None = None) -> None:
        raw_plan = (plan or os.environ.get("DREAM_PLAN", "local") or "local").strip().lower()
        if raw_plan not in PLANS:
            raise LedgerConfigurationError(_UNKNOWN_PLAN)
        self.plan = PLANS[raw_plan]
        self.plan_id = raw_plan
        chosen = path or os.environ.get("DREAM_LEDGER") or DEFAULT_LEDGER_PATH
        self.path = Path(chosen)
        self._entries: list[dict] | None = None

    @classmethod
    def from_env(cls) -> Ledger | None:
        """Return the attached ledger, or ``None`` when none is attached."""
        if not ledger_attached():
            return None
        return cls()

    # -- loading -----------------------------------------------------------

    def _load(self) -> list[dict]:
        """Read and validate the ledger; corrupt files raise, never grant."""
        if self._entries is not None:
            return self._entries
        path = self.path
        if not path.exists():
            self._entries = []
            return self._entries
        try:
            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise LedgerCorruptionError(_CORRUPT_LEDGER) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
            raise LedgerCorruptionError(_CORRUPT_LEDGER)
        entries = payload["entries"]
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("ts"), str):
                raise LedgerCorruptionError(_CORRUPT_LEDGER)
            try:
                datetime.fromisoformat(entry["ts"])
            except ValueError as exc:
                raise LedgerCorruptionError(_CORRUPT_LEDGER) from exc
        self._entries = entries
        return entries

    # -- quota windows -----------------------------------------------------

    def _window(self, now: datetime) -> tuple[str, str]:
        """Return (window kind, key) for the plan's quota window."""
        if self.plan.daily_limit is not None:
            return "day", now.strftime("%Y-%m-%d")
        if self.plan.monthly_limit is not None:
            return "month", now.strftime("%Y-%m")
        if self.plan.yearly_limit is not None:
            return "year", now.strftime("%Y")
        # Unlimited plans (local): every entry counts, no quota applies.
        return "all", ""

    def _entry_in_window(self, entry: dict, kind: str, key: str) -> bool:
        try:
            stamp = datetime.fromisoformat(entry["ts"])
        except (KeyError, TypeError, ValueError):
            return False
        if kind == "all":
            return True
        if kind == "day":
            return stamp.strftime("%Y-%m-%d") == key
        if kind == "month":
            return stamp.strftime("%Y-%m") == key
        if kind == "year":
            return stamp.strftime("%Y") == key
        return False

    def _window_limit(self) -> int | None:
        return (
            self.plan.daily_limit
            if self.plan.daily_limit is not None
            else self.plan.monthly_limit
            if self.plan.monthly_limit is not None
            else self.plan.yearly_limit
        )

    # -- consuming ---------------------------------------------------------

    def consume(self, now: datetime | None = None) -> int:
        """Record one consumed turn.

        Returns the number of turns used in the current window after the
        record. Raises ``QuotaExceeded`` (metered plan, window exhausted)
        or ``LedgerError`` (corrupt/misconfigured, fail-closed) without
        appending anything.
        """
        stamp = now or datetime.now().astimezone()
        entries = self._load()
        kind, key = self._window(stamp)
        used = sum(1 for entry in entries if self._entry_in_window(entry, kind, key))
        limit = self._window_limit()
        if self.plan.metered and limit is not None and used >= limit:
            raise QuotaExceeded(_quota_message(self.plan, limit, used))
        entries.append({"ts": stamp.isoformat()})
        self._save(entries)
        return used + 1

    def remaining(self, now: datetime | None = None) -> int | None:
        """Turns left in the current window; ``None`` for unlimited plans."""
        info = self.usage(now)
        if info["limit"] is None:
            return None
        return max(0, info["limit"] - info["used"])

    def usage(self, now: datetime | None = None) -> dict:
        """A read-only summary of the ledger and the current window."""
        stamp = now or datetime.now().astimezone()
        entries = self._load()
        kind, key = self._window(stamp)
        used = sum(1 for entry in entries if self._entry_in_window(entry, kind, key))
        return {
            "plan": self.plan_id,
            "currency": self.plan.currency,
            "price": self.plan.price,
            "price_note": self.plan.price_note,
            "window": kind,
            "used": used,
            "limit": self._window_limit(),
        }

    # -- persistence -------------------------------------------------------

    def _save(self, entries: list[dict]) -> None:
        """Write the ledger atomically so a crash cannot tear it."""
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"version": LEDGER_VERSION, "plan": self.plan_id, "entries": entries},
            ensure_ascii=False,
            indent=2,
        )
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=".dream-ledger-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# User-facing text for the CLI (/plan, /usage, --plan, --usage)
# ---------------------------------------------------------------------------


def current_plan_text() -> str:
    """One honest paragraph describing the active plan and its price."""
    try:
        plan = _resolve_plan()
    except LedgerError as exc:
        return str(exc)
    price = "0 (free plan)" if plan.price == 0 else plan.price_note
    quota: str
    if plan.daily_limit is not None:
        quota = f"{plan.daily_limit} turns per day"
    elif plan.monthly_limit is not None:
        quota = f"{plan.monthly_limit} turns per month"
    elif plan.yearly_limit is not None:
        quota = f"{plan.yearly_limit} turns per year"
    else:
        quota = "unlimited"
    return (
        f"Plan: {plan.id} ({plan.name_fa})\n"
        f"Currency: {plan.currency}\n"
        f"Price: {price}\n"
        f"Quota: {quota}"
    )


def usage_text() -> str:
    """Describe current ledger usage, or that no ledger is attached."""
    ledger = Ledger.from_env()
    if ledger is None:
        return (
            "No usage ledger attached (plan: local) — usage is not metered "
            "and no ledger file is required."
        )
    try:
        info = ledger.usage()
    except LedgerError as exc:
        return str(exc)
    if info["limit"] is None:
        return f"Plan: {info['plan']} — unlimited; no quota applies."
    remaining = max(0, info["limit"] - info["used"])
    return (
        f"Plan: {info['plan']} — {info['used']} of {info['limit']} turns used "
        f"in this {info['window']} (remaining: {remaining})."
    )
