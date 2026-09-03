"""Dual bounded memory stores with frozen snapshot injection (MEM Stage A).

Dream already has an unbounded associative memory (:class:`dream.memory.MemoryStore`)
for retrieval.  This module adds the *other* half of a durable agent: two small,
character-bounded stores whose entire content is injected into the system prompt
as one frozen snapshot at session start — agent notes (target ``memory``) and a
user profile (target ``user``).  The design follows three rules:

* **Bounded, visibly.**  Every store carries a character budget (2,200 for
  notes, 1,375 for the profile — :data:`NOTES_CAPACITY_CHARS` and
  :data:`PROFILE_CAPACITY_CHARS`; both are constructor arguments, not magic
  numbers).  The snapshot renders a capacity header such as
  ``[67% — 1,474/2,200 chars]`` so the model can see how much room is left.
* **Overflow is an error, never a truncation.**  An ``add``/``replace`` that
  would exceed the budget raises :class:`StoreCapacityError` and the store is
  left untouched, so the agent must consolidate (``replace``/``remove``) in the
  same turn instead of silently losing a tail.  Every error message is
  bilingual (Persian first, matching the kernel's agent-facing convention)
  and says exactly that.
* **One writer per store.**  All mutations run the check-plus-mutate cycle
  as one ``BEGIN IMMEDIATE`` transaction under one re-entrant thread lock,
  and the SQLite handle is private to the store, so no caller can reach the
  mutable backend without synchronization. Threads serialize in-process on
  the lock and writers serialize across processes on SQLite's file lock
  (with ``busy_timeout`` so a concurrent writer waits instead of erroring).
  Any failure — a domain error, a constraint failure, or a keyboard
  interrupt — rolls the transaction back before it propagates, so a failed
  or interrupted write is invisible and never leaks an open transaction.
  Reads (:meth:`BoundedStore.snapshot`) take the same lock and return a
  detached immutable snapshot, budgeted at < 5 ms — the store is at most a
  few thousand characters by construction. No callback or external code
  ever runs under the lock.

Tool surface (registered by :class:`dream.agent.Dream`, not here): ``add``,
``replace``, ``remove`` with unique-substring matching.  There is no ``read``
action — the snapshot is already in the prompt and every mutation result
carries the fresh state, which keeps the tool surface minimal without hiding
information from the agent.

Substring matching goes through Dream's single Persian normalizer
(:func:`dream.memory.normalize_fa`): a stored entry written with Arabic
code points (``\\u0643\\u062a\\u0627\\u0628``, Arabic kaf + yeh) is matched
by a Farsi-spelled fragment (``\\u06a9\\u062a\\u0627\\u0628``, keheh +
Farsi yeh) and vice versa, exactly like every other retrieval path in the
kernel. Importing the function here is a re-export, not a copy — a test pins
the two import paths to one implementation.

Standard library only: ``sqlite3``, ``threading``, ``dataclasses``.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from dream.memory import normalize_fa

__all__ = [
    "AmbiguousEntryError",
    "BoundedMemory",
    "BoundedSnapshot",
    "BoundedStore",
    "BoundedStoreError",
    "ENTRY_SEPARATOR",
    "EntryNotFoundError",
    "NOTES_CAPACITY_CHARS",
    "PROFILE_CAPACITY_CHARS",
    "StoreCapacityError",
    "TARGET_MEMORY",
    "TARGET_USER",
    "normalize_fa",
]

# Store targets. ``memory`` is the agent's own notebook; ``user`` is the
# profile of the person it serves. Two targets, two tools, one module.
TARGET_MEMORY = "memory"
TARGET_USER = "user"

# Character budgets. These are the exact defaults; both are constructor
# arguments on BoundedStore/BoundedMemory so callers can resize a store in
# code without editing the kernel. Notes get more room than the profile: the
# agent consolidates its working knowledge into notes while the profile holds
# only durable facts about the user.
NOTES_CAPACITY_CHARS = 2_200
PROFILE_CAPACITY_CHARS = 1_375

# Smallest store we will construct: enough for a couple of sentences. A
# "bounded" store with a budget of zero could never hold anything and would
# only produce noise errors.
MIN_CAPACITY_CHARS = 64

# Entries are joined (and capacity-accounted) with this one-character
# separator, so the snapshot reads as one flowing block instead of a list.
ENTRY_SEPARATOR = "§"

# Default database file, relative to the working directory like
# MemoryStore's default. Overridable via environment for tests and embeds.
DEFAULT_DB_PATH = "data/dream-bounded.db"

# Cross-process writers wait up to five seconds for the SQLite write lock
# instead of failing immediately; in-process writers never see this because
# the re-entrant lock serializes them first.
_BUSY_TIMEOUT_MS = 5_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bounded_entries (
    user_id    TEXT    NOT NULL,
    target     TEXT    NOT NULL,
    pos        INTEGER NOT NULL,
    text       TEXT    NOT NULL,
    updated_at REAL    NOT NULL,
    PRIMARY KEY (user_id, target, pos)
);
"""


class BoundedStoreError(ValueError):
    """Base class for bounded-store failures. Subclasses carry details."""

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.details: dict[str, Any] = dict(details)


class StoreCapacityError(BoundedStoreError):
    """An add/replace would exceed the store's character budget.

    Nothing was written. The message tells the agent, in Persian and English,
    to consolidate with ``replace``/``remove`` and retry in the same turn.
    """


class EntryNotFoundError(BoundedStoreError):
    """A replace/remove fragment matched no entry. Nothing was written."""


class AmbiguousEntryError(BoundedStoreError):
    """A replace/remove fragment matched more than one entry.

    Unique-substring matching is the contract: the caller must send a longer
    fragment. The matching excerpts are attached so the agent can pick one.
    """


def _used_chars(entries: tuple[str, ...], separator: str) -> int:
    """Total rendered size: every entry plus the separators between them."""
    if not entries:
        return 0
    return sum(len(entry) for entry in entries) + len(separator) * (len(entries) - 1)


@dataclass(frozen=True, slots=True)
class BoundedSnapshot:
    """An immutable view of one bounded store at a point in time.

    Built under the store lock; a snapshot handed to the prompt can never be
    mutated by later writes (entries live in a tuple inside a frozen
    dataclass), which is the "frozen snapshot at session start" contract.
    """

    target: str
    capacity: int
    entries: tuple[str, ...]
    separator: str = ENTRY_SEPARATOR

    @property
    def used_chars(self) -> int:
        return _used_chars(self.entries, self.separator)

    @property
    def percent(self) -> int:
        if self.capacity <= 0:
            return 0
        return round(100 * self.used_chars / self.capacity)

    @property
    def header(self) -> str:
        """Capacity header, e.g. ``[67% — 1,474/2,200 chars]``."""
        return f"[{self.percent}% — {self.used_chars:,}/{self.capacity:,} chars]"

    @property
    def text(self) -> str:
        """The snapshot body: entries joined by the § separator."""
        return self.separator.join(self.entries)


# Persian section labels for prompt injection. Written as backslash-u escapes
# with a plain gloss, matching the synonym-table convention, so copying the
# file between editors cannot corrupt them.
# Gloss: یادداشت‌های پایدار دستیار (durable agent notes)
NOTES_LABEL = (
    "\u06cc\u0627\u062f\u062f\u0627\u0634\u062a\u200c\u0647\u0627\u06cc "
    "\u067e\u0627\u06cc\u062f\u0627\u0631 \u062f\u0633\u062a\u06cc\u0627\u0631"
)

# Gloss: پروفایل پایدار کاربر (durable user profile)
PROFILE_LABEL = (
    "\u067e\u0631\u0648\u0641\u0627\u06cc\u0644 \u067e\u0627\u06cc\u062f\u0627\u0631 "
    "\u06a9\u0627\u0631\u0628\u0631"
)

# Agent guidance injected with the snapshots. Gloss (plain spelling):
# «دو حافظهٔ پایدار و سقف‌دار در ادامه می‌آید: یادداشت‌های دستیار و پروفایل
# کاربر — واقعیت‌هایی که باید در همهٔ نشست‌ها به یاد داشته باشی. مدخل‌ها با §
# از هم جدا می‌شوند و سطر سرصفحهٔ مانند [67% — 1,474/2,200 chars] ظرفیت
# پرشده را نشان می‌دهد. این تصویر در آغاز نشست منجمد شده است؛ برای تغییرش
# فقط از ابزارهای agent_notes و user_profile با کنش‌های add و replace و
# remove استفاده کن و در old عبارتی بفرست که تنها در یک مدخل پیدا شود.
# ابزار خواندن وجود ندارد؛ نتیجهٔ هر کنش وضعیت تازهٔ حافظه را برمی‌گرداند.
# پر شدن ظرفیت خطاست، نه کوتاه‌کردن بی‌صدا: در همان نوبت مدخل‌های نزدیک را
# با replace ادغام کن یا با remove حذف کن و بعد دوباره تلاش کن.»
BOUNDED_MEMORY_USAGE = (
    "\n\n"
    "\u062f\u0648 \u062d\u0627\u0641\u0638\u0647\u0654 \u067e\u0627\u06cc\u062f\u0627\u0631 "
    "\u0648 \u0633\u0642\u0641\u200c\u062f\u0627\u0631 \u062f\u0631 \u0627\u062f\u0627\u0645\u0647 "
    "\u0645\u06cc\u200c\u0622\u06cc\u062f: \u06cc\u0627\u062f\u062f\u0627\u0634\u062a\u200c"
    "\u0647\u0627\u06cc \u062f\u0633\u062a\u06cc\u0627\u0631 \u0648 \u067e\u0631\u0648\u0641\u0627"
    "\u06cc\u0644 \u06a9\u0627\u0631\u0628\u0631 \u2014 \u0648\u0627\u0642\u0639\u06cc\u062a"
    "\u200c\u0647\u0627\u06cc\u06cc \u06a9\u0647 \u0628\u0627\u06cc\u062f \u062f\u0631 "
    "\u0647\u0645\u0647\u0654 \u0646\u0634\u0633\u062a\u200c\u0647\u0627 \u0628\u0647 "
    "\u06cc\u0627\u062f \u062f\u0627\u0634\u062a\u0647 \u0628\u0627\u0634\u06cc. "
    "\u0645\u062f\u062e\u0644\u200c\u0647\u0627 \u0628\u0627 \u00a7 \u0627\u0632 \u0647\u0645 "
    "\u062c\u062f\u0627 \u0645\u06cc\u200c\u0634\u0648\u0646\u062f \u0648 \u0633\u0637\u0631 "
    "\u0633\u0631\u0635\u0641\u062d\u0647\u0654 \u0645\u0627\u0646\u0646\u062f "
    "[67% \u2014 1,474/2,200 chars] \u0638\u0631\u0641\u06cc\u062a \u067e\u0631\u0634\u062f"
    "\u0647 \u0631\u0627 \u0646\u0634\u0627\u0646 \u0645\u06cc\u200c\u062f\u0647\u062f. "
    "\u0627\u06cc\u0646 \u062a\u0635\u0648\u06cc\u0631 \u062f\u0631 \u0622\u063a\u0627\u0632 "
    "\u0646\u0634\u0633\u062a \u0645\u0646\u062c\u0645\u062f \u0634\u062f\u0647 \u0627\u0633"
    "\u062a\u061b \u0628\u0631\u0627\u06cc \u062a\u063a\u06cc\u06cc\u0631\u0634 \u0641\u0642"
    "\u0637 \u0627\u0632 \u0627\u0628\u0632\u0627\u0631\u0647\u0627\u06cc agent_notes "
    "\u0648 user_profile \u0628\u0627 \u06a9\u0646\u0634\u200c\u0647\u0627\u06cc add "
    "\u0648 replace \u0648 remove \u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u06a9\u0646 "
    "\u0648 \u062f\u0631 old \u0639\u0628\u0627\u0631\u062a\u06cc \u0628\u0641\u0631\u0633"
    "\u062a \u06a9\u0647 \u062a\u0646\u0647\u0627 \u062f\u0631 \u06cc\u06a9 \u0645\u062f\u062e"
    "\u0644 \u067e\u06cc\u062f\u0627 \u0634\u0648\u062f. \u0627\u0628\u0632\u0627\u0631 "
    "\u062e\u0648\u0627\u0646\u062f\u0646 \u0648\u062c\u0648\u062f \u0646\u062f\u0627\u0631"
    "\u062f\u061b \u0646\u062a\u06cc\u062c\u0647\u0654 \u0647\u0631 \u06a9\u0646\u0634 "
    "\u0648\u0636\u0639\u06cc\u062a \u062a\u0627\u0632\u0647\u0654 \u062d\u0627\u0641\u0638"
    "\u0647 \u0631\u0627 \u0628\u0631\u0645\u06cc\u200c\u06af\u0631\u062f\u0627\u0646\u062f. "
    "\u067e\u0631 \u0634\u062f\u0646 \u0638\u0631\u0641\u06cc\u062a \u062e\u0637\u0627\u0633"
    "\u062a\u060c \u0646\u0647 \u06a9\u0648\u062a\u0627\u0647\u200c\u06a9\u0631\u062f\u0646 "
    "\u0628\u06cc\u200c\u0635\u062f\u0627: \u062f\u0631 \u0647\u0645\u0627\u0646 \u0646\u0648"
    "\u0628\u062a \u0645\u062f\u062e\u0644\u200c\u0647\u0627\u06cc \u0646\u0632\u062f\u06cc\u06a9 "
    "\u0631\u0627 \u0628\u0627 replace \u0627\u062f\u063a\u0627\u0645 \u06a9\u0646 \u06cc\u0627 "
    "\u0628\u0627 remove \u062d\u0630\u0641 \u06a9\u0646 \u0648 \u0628\u0639\u062f \u062f\u0648"
    "\u0628\u0627\u0631\u0647 \u062a\u0644\u0627\u0634 \u06a9\u0646."
)

# Error message fragments. Each error is bilingual: Persian sentence(s) for
# the agent loop, then an English sentence for logs and non-Persian models.
# Glosses in the comments give the plain spelling.

# Gloss: «ظرفیت حافظه پر است: {header} — {over} نویسه بیشتر از سقف جا شده
# است. هیچ چیزی کوتاه یا ذخیره نشد؛ اول با replace یا remove مدخلی را
# ادغام یا حذف کن و در همین نوبت دوباره تلاش کن.»
_ERR_CAPACITY_FA = (
    "\u0638\u0631\u0641\u06cc\u062a \u062d\u0627\u0641\u0638\u0647 \u067e\u0631 "
    "\u0627\u0633\u062a: {header} \u2014 {over} \u0646\u0648\u06cc\u0633\u0647 "
    "\u0628\u06cc\u0634\u062a\u0631 \u0627\u0632 \u0633\u0642\u0641 \u062c\u0627 "
    "\u0634\u062f\u0647 \u0627\u0633\u062a. \u0647\u06cc\u0686 \u0686\u06cc\u0632\u06cc "
    "\u06a9\u0648\u062a\u0627\u0647 \u06cc\u0627 \u0630\u062e\u06cc\u0631\u0647 "
    "\u0646\u0634\u062f\u061b \u0627\u0648\u0644 \u0628\u0627 replace \u06cc\u0627 "
    "remove \u0645\u062f\u062e\u0644\u06cc \u0631\u0627 \u0627\u062f\u063a\u0627\u0645 "
    "\u06cc\u0627 \u062d\u0630\u0641 \u06a9\u0646 \u0648 \u062f\u0631 \u0647\u0645\u06cc\u0646 "
    "\u0646\u0648\u0628\u062a \u062f\u0648\u0628\u0627\u0631\u0647 \u062a\u0644\u0627\u0634 "
    "\u06a9\u0646."
)
_ERR_CAPACITY_EN = (
    " Store '{target}' is full: {header} — over capacity by {over} chars; nothing"
    " was truncated or stored. Consolidate with replace/remove, then retry in the"
    " same turn."
)

# Gloss: «در این حافظه هیچ مدخلی با عبارت «{old}» پیدا نشد؛ چیزی تغییر نکرد.»
_ERR_NOT_FOUND_FA = (
    "\u062f\u0631 \u0627\u06cc\u0646 \u062d\u0627\u0641\u0638\u0647 \u0647\u06cc\u0686 "
    "\u0645\u062f\u062e\u0644\u06cc \u0628\u0627 \u0639\u0628\u0627\u0631\u062a "
    "\u00ab{old}\u00bb \u067e\u06cc\u062f\u0627 \u0646\u0634\u062f\u061b \u0686\u06cc\u0632"
    "\u06cc \u062a\u063a\u06cc\u06cc\u0631 \u0646\u06a9\u0631\u062f."
)
_ERR_NOT_FOUND_EN = " No entry in store '{target}' contains {old!r}; nothing changed."

# Gloss: «این عبارت در {count} مدخل پیدا شد؛ عبارت را بلندتر کن تا تنها یک
# مدخل را هدف بگیرد. مدخل‌ها: {excerpts}»
_ERR_AMBIGUOUS_FA = (
    "\u0627\u06cc\u0646 \u0639\u0628\u0627\u0631\u062a \u062f\u0631 {count} \u0645\u062f\u062e"
    "\u0644 \u067e\u06cc\u062f\u0627 \u0634\u062f\u061b \u0639\u0628\u0627\u0631\u062a "
    "\u0631\u0627 \u0628\u0644\u0646\u062f\u062a\u0631 \u06a9\u0646 \u062a\u0627 \u062a\u0646"
    "\u0647\u0627 \u06cc\u06a9 \u0645\u062f\u062e\u0644 \u0631\u0627 \u0647\u062f\u0641 "
    "\u0628\u06af\u06cc\u0631\u062f. \u0645\u062f\u062e\u0644\u200c\u0647\u0627: {excerpts}"
)
_ERR_AMBIGUOUS_EN = (
    " Matched {count} entries in store '{target}'; send a longer substring that"
    " matches exactly one entry."
)

# Gloss: «متن مدخل خالی است؛ مدخل باید متن داشته باشد.»
_ERR_EMPTY_ADD_FA = (
    "\u0645\u062a\u0646 \u0645\u062f\u062e\u0644 \u062e\u0627\u0644\u06cc \u0627\u0633\u062a"
    "\u061b \u0645\u062f\u062e\u0644 \u0628\u0627\u06cc\u062f \u0645\u062a\u0646 \u062f\u0627"
    "\u0634\u062a\u0647 \u0628\u0627\u0634\u062f."
)

# Gloss: «عبارت old خالی است یا به هیچ نویسه‌ای نرمال نمی‌شود؛ عبارتی معتبر بفرست.»
_ERR_EMPTY_OLD_FA = (
    "\u0639\u0628\u0627\u0631\u062a old \u062e\u0627\u0644\u06cc \u0627\u0633\u062a "
    "\u06cc\u0627 \u0628\u0647 \u0647\u06cc\u0686 \u0646\u0648\u06cc\u0633\u0647\u200c\u0627"
    "\u06cc \u0646\u0631\u0645\u0627\u0644 \u0646\u0645\u06cc\u200c\u0634\u0648\u062f\u061b "
    "\u0639\u0628\u0627\u0631\u062a\u06cc \u0645\u0639\u062a\u0628\u0631 \u0628\u0641\u0631"
    "\u0633\u062a."
)
_ERR_EMPTY_OLD_EN = " The 'old' fragment is empty or normalizes to nothing."

# Excerpt length for ambiguity listings: enough to tell entries apart, never
# enough to blow up the error payload.
_EXCERPT_CHARS = 60


def _excerpt(text: str) -> str:
    """One bounded, marker-wrapped excerpt of an entry."""
    snippet = text[:_EXCERPT_CHARS]
    if len(text) > _EXCERPT_CHARS:
        snippet += "…"
    return f"«{snippet}»"


class BoundedStore:
    """One bounded, ordered, character-budgeted store behind SQLite.

    Thread safety mirrors :class:`dream.memory.MemoryStore` and extends it:
    the SQLite handle is **private** (``_conn``, opened with
    ``check_same_thread=False``) and every access to it — read or write —
    runs under one re-entrant lock, so callers can never reach the mutable
    backend without synchronization. Every write (``add`` / ``replace`` /
    ``remove``) is one ``BEGIN IMMEDIATE`` … ``COMMIT`` transaction inside
    that lock (:meth:`_locked_write`): the capacity/match check and the
    mutation are one atomic unit, a second writer — in this process or
    another — cannot slip a write between check and mutation, and any
    exception (including a keyboard interrupt) rolls the transaction back
    before it propagates. Reads (:meth:`snapshot`) take the same lock and
    build a detached, immutable :class:`BoundedSnapshot` (a fresh tuple of
    immutable strings) budgeted at < 5 ms. No callback or external code
    ever runs under the lock, so the lock can never be held across
    user-controlled execution.
    """

    def __init__(
        self,
        target: str,
        capacity: int,
        path: str = ":memory:",
        user: str | None = None,
        separator: str = ENTRY_SEPARATOR,
    ) -> None:
        if target not in (TARGET_MEMORY, TARGET_USER):
            raise ValueError(
                f"target must be {TARGET_MEMORY!r} or {TARGET_USER!r}, got {target!r}"
            )
        if not isinstance(capacity, int) or isinstance(capacity, bool):
            raise ValueError("capacity must be an int")
        if capacity < MIN_CAPACITY_CHARS:
            raise ValueError(
                f"capacity must be at least {MIN_CAPACITY_CHARS} chars, got {capacity}"
            )
        if not separator:
            raise ValueError("separator must not be empty")
        self.target = target
        self.capacity = capacity
        self.separator = separator
        self.path = str(path)
        self.user_id = user if user is not None else os.environ.get("DREAM_USER", "local")
        if not isinstance(self.user_id, str) or not self.user_id:
            raise ValueError("user must be a non-empty string")
        self._lock = threading.RLock()
        if self.path != ":memory:":
            parent = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(parent, exist_ok=True)
        # Private on purpose: a public handle would let a caller run SQL
        # outside the lock and corrupt the capacity invariant.
        self._conn = sqlite3.connect(
            self.path, check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Release the private handle under the lock. Idempotent."""
        with self._lock:
            self._conn.close()

    def __enter__(self) -> BoundedStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- synchronization boundaries ----------------------------------------

    @contextlib.contextmanager
    def _locked_write(self) -> Iterator[None]:
        """Run one write as one atomic ``BEGIN IMMEDIATE`` … ``COMMIT`` unit.

        Holds the store lock for the whole unit (and only for it), so
        in-process writers serialize on the lock and cross-process writers
        on SQLite's file lock (``busy_timeout`` absorbs the wait). On any
        exception — a domain error, a constraint failure, or a keyboard
        interrupt — the transaction is rolled back before the exception
        propagates, so the connection never carries a leaked write
        transaction and a failed write is invisible. ``BaseException`` (not
        just ``Exception``) is caught because a Ctrl-C inside the unit must
        roll back too: otherwise the leaked ``BEGIN IMMEDIATE`` bricks every
        later write with "cannot start a transaction within a transaction".
        The rollback is gated on ``in_transaction`` instead of swallowing an
        expected no-op ``OperationalError``; a rollback that fails for a real
        reason propagates instead of being hidden.
        """
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                if self._conn.in_transaction:
                    self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    # -- reads -------------------------------------------------------------

    def _entries_locked(self) -> tuple[str, ...]:
        """Rows in display order. Must run with the store lock held."""
        rows = self._conn.execute(
            "SELECT text FROM bounded_entries WHERE user_id = ? AND target = ?"
            " ORDER BY pos",
            (self.user_id, self.target),
        ).fetchall()
        return tuple(str(row["text"]) for row in rows)

    def snapshot(self) -> BoundedSnapshot:
        """Build the frozen snapshot. Bounded by the capacity budget (< 5 ms).

        Runs under the store lock and returns a **detached** snapshot: a
        fresh tuple of immutable strings inside a frozen dataclass, so a
        snapshot handed to one thread can never be altered by a later write
        (or by a caller, which the frozen dataclass refuses) and never
        exposes the store's live state.
        """
        with self._lock:
            return BoundedSnapshot(
                target=self.target,
                capacity=self.capacity,
                entries=self._entries_locked(),
                separator=self.separator,
            )

    # -- writes ------------------------------------------------------------

    def add(self, text: str) -> BoundedSnapshot:
        """Append one entry; raise :class:`StoreCapacityError` on overflow.

        Synchronization boundary: the row-position check, capacity check,
        insert, and commit run as one ``BEGIN IMMEDIATE`` transaction under
        the store lock (:meth:`_locked_write`), so a concurrent add — in
        this process or another — is serialized completely before or after
        this one: no overflow, no lost row, no duplicated row. Duplicate
        *values* are allowed and appended like any other entry; there is no
        value-level deduplication in the contract. The returned snapshot is
        built under the lock after the commit.
        """
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        entry = text.strip()
        if not entry:
            raise BoundedStoreError(_ERR_EMPTY_ADD_FA + " Entry text must not be empty.")
        with self._locked_write():
            entries = self._entries_locked()
            used = _used_chars(entries, self.separator)
            needed = len(entry) + (len(self.separator) if entries else 0)
            if used + needed > self.capacity:
                raise self._capacity_error(used + needed - self.capacity)
            next_pos = 1
            if entries:
                row = self._conn.execute(
                    "SELECT MAX(pos) AS p FROM bounded_entries"
                    " WHERE user_id = ? AND target = ?",
                    (self.user_id, self.target),
                ).fetchone()
                next_pos = int(row["p"]) + 1
            self._conn.execute(
                "INSERT INTO bounded_entries (user_id, target, pos, text, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (self.user_id, self.target, next_pos, entry, time.time()),
            )
        return self.snapshot()

    def _match_locked(self, old: str) -> tuple[int, str]:
        """Resolve a unique-substring fragment to ``(pos, entry)``.

        Must run with the store lock held (and, for ``replace``/``remove``,
        inside the write transaction, so the match and the mutation are one
        atomic unit — a concurrent writer cannot change what the fragment
        matches between check and update). Matching is normalized: the
        fragment and every entry pass through :func:`normalize_fa` first, so
        Arabic and Farsi spellings of the same word are interchangeable.
        Zero matches and multiple matches are both errors — the caller must
        disambiguate, the store must not guess.
        """
        if not isinstance(old, str) or not old.strip():
            raise BoundedStoreError(
                _ERR_EMPTY_OLD_FA + _ERR_EMPTY_OLD_EN, target=self.target
            )
        needle = normalize_fa(old).strip()
        if not needle:
            raise BoundedStoreError(
                _ERR_EMPTY_OLD_FA + _ERR_EMPTY_OLD_EN, target=self.target
            )
        rows = self._conn.execute(
            "SELECT pos, text FROM bounded_entries WHERE user_id = ? AND target = ?"
            " ORDER BY pos",
            (self.user_id, self.target),
        ).fetchall()
        matches = [
            (int(row["pos"]), str(row["text"]))
            for row in rows
            if needle in normalize_fa(str(row["text"]))
        ]
        if not matches:
            raise EntryNotFoundError(
                _ERR_NOT_FOUND_FA.format(old=old.strip())
                + _ERR_NOT_FOUND_EN.format(target=self.target, old=old.strip()),
                target=self.target,
                old=old.strip(),
            )
        if len(matches) > 1:
            excerpts = " | ".join(_excerpt(text) for _, text in matches)
            raise AmbiguousEntryError(
                _ERR_AMBIGUOUS_FA.format(count=len(matches), excerpts=excerpts)
                + _ERR_AMBIGUOUS_EN.format(count=len(matches), target=self.target),
                target=self.target,
                old=old.strip(),
                matches=[text for _, text in matches],
            )
        return matches[0]

    def _capacity_error(self, over_by: int) -> StoreCapacityError:
        # ``snapshot`` re-enters the RLock (same thread — safe) and may run
        # inside the open write transaction; no write has happened yet, so
        # the header reflects exactly the committed state the caller sees.
        snapshot = self.snapshot()
        message = (
            _ERR_CAPACITY_FA.format(header=snapshot.header, over=over_by)
            + _ERR_CAPACITY_EN.format(
                target=self.target, header=snapshot.header, over=over_by
            )
        )
        return StoreCapacityError(
            message,
            target=self.target,
            header=snapshot.header,
            over_by=over_by,
            used_chars=snapshot.used_chars,
            capacity=self.capacity,
        )

    def replace(self, old: str, new: str) -> BoundedSnapshot:
        """Replace the single entry containing ``old`` (normalized substring).

        Synchronization boundary: the unique-substring match, the capacity
        check, and the update run as one ``BEGIN IMMEDIATE`` transaction
        under the store lock (:meth:`_locked_write`). A concurrent add or
        replace therefore cannot change what ``old`` matches between the
        check and the update (no lost update, no torn replacement), and a
        capacity overflow or a non-unique match rolls everything back.

        Raises :class:`EntryNotFoundError` / :class:`AmbiguousEntryError` when
        the fragment is not unique, and :class:`StoreCapacityError` when the
        replacement would overflow — in every failure case the store is
        unchanged.
        """
        if not isinstance(new, str):
            raise ValueError("new must be a string")
        entry = new.strip()
        if not entry:
            raise BoundedStoreError(_ERR_EMPTY_ADD_FA + " Entry text must not be empty.")
        with self._locked_write():
            pos, current = self._match_locked(old)
            entries = self._entries_locked()
            used = _used_chars(entries, self.separator)
            delta = len(entry) - len(current)
            if used + delta > self.capacity:
                raise self._capacity_error(used + delta - self.capacity)
            self._conn.execute(
                "UPDATE bounded_entries SET text = ?, updated_at = ?"
                " WHERE user_id = ? AND target = ? AND pos = ?",
                (entry, time.time(), self.user_id, self.target, pos),
            )
        return self.snapshot()

    def remove(self, old: str) -> BoundedSnapshot:
        """Remove the single entry containing ``old`` (normalized substring).

        The match and the delete are one ``BEGIN IMMEDIATE`` transaction
        under the store lock (:meth:`_locked_write`), so a concurrent writer
        cannot change what the fragment matches between check and delete,
        and a non-unique or missing match leaves the store untouched.
        """
        with self._locked_write():
            pos, _current = self._match_locked(old)
            self._conn.execute(
                "DELETE FROM bounded_entries"
                " WHERE user_id = ? AND target = ? AND pos = ?",
                (self.user_id, self.target, pos),
            )
        return self.snapshot()


class BoundedMemory:
    """The dual-store pair: agent notes plus user profile, one file.

    Both stores share nothing but the SQLite file (each opens its own
    connection), so a slow writer on one store never blocks the other for
    longer than SQLite's own lock granularity, while the file stays in
    Dream's data directory next to ``dream.db``.
    """

    def __init__(
        self,
        path: str = ":memory:",
        user: str | None = None,
        notes_capacity: int = NOTES_CAPACITY_CHARS,
        profile_capacity: int = PROFILE_CAPACITY_CHARS,
    ) -> None:
        self.path = str(path)
        self.notes = BoundedStore(
            TARGET_MEMORY, notes_capacity, path=path, user=user
        )
        self.profile = BoundedStore(
            TARGET_USER, profile_capacity, path=path, user=user
        )

    @classmethod
    def from_env(cls, user: str | None = None) -> BoundedMemory:
        """Open the default dual store under Dream's data directory."""
        return cls(os.environ.get("DREAM_BOUNDED_DB", DEFAULT_DB_PATH), user=user)

    def snapshots(self) -> dict[str, BoundedSnapshot]:
        """Frozen snapshots of both stores, keyed by target.

        Consistency boundary: each per-store snapshot is atomic under that
        store's lock, but the two stores take their locks in sequence (notes
        first), so the pair is *individually* consistent — not a single
        global instant. The session-start contract only ever needs the
        per-store form, so no cross-store transaction is added.
        """
        return {
            TARGET_MEMORY: self.notes.snapshot(),
            TARGET_USER: self.profile.snapshot(),
        }

    def store(self, target: str) -> BoundedStore:
        """Resolve a target name to its store; unknown names are an error."""
        if target == TARGET_MEMORY:
            return self.notes
        if target == TARGET_USER:
            return self.profile
        raise ValueError(f"unknown bounded store target: {target!r}")

    def close(self) -> None:
        self.notes.close()
        self.profile.close()

    def __enter__(self) -> BoundedMemory:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
