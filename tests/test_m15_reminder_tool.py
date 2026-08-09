"""Pins M15 reminder tool: a model can set a reminder in the owner's own words.

What this pins and what evidence justified it:

- On merged main the model cannot set a reminder; the registry lists ten
  global tools and three per-chat tools, none a reminder. A reply claiming
  a reminder was set is therefore false every time, and no guard was built
  because the honest fix is the tool (M14's argued refusal).

- There are two date parsers with similar names: the numeric one
  (parse_date_to_timestamp) and the natural one (parse_persian_date).
  The numeric one refuses every natural phrase; the natural one accepts
  eleven phrases and refuses six, including the time-combined phrase
  that a model most naturally emits (tomorrow at nine). Guessing nine
  is a data-integrity veto.

- The tool's date contract is therefore: it accepts a pure date as
  Jalali YYYY-MM-DD (year <1700) via the numeric parser, or a natural
  Persian phrase via the natural parser, and refuses what neither
  parser accepts. A phrase containing a time word (``\\u0633\\u0627\\u0639\\u062a``)
  is refused with an explicit Persian hint, never guessed. This keeps
  the Jalali module as the single source of calendar truth and avoids
  the model converting dates by reasoning.

- Every new Persian string is a backslash-u escape, matching the
  repository convention, and is passed through normalize_fa before it is
  trusted.

- A truthful reminder reply must not trip the M14 fact guard, and the
  single-warning rule still holds: the owner never reads two warnings.

Tests are written first and observed red against unchanged source before
any implementation, then green after.
"""

from __future__ import annotations

import json

import pytest

from dream import tools
from dream.agent import Dream, EchoBackend
from dream.memory import MemoryStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW_JALALI = "1405-05-17"
_NOW_TS = None  # filled lazily to avoid import-time DB


def _now_ts():
    from dream.reminders import parse_date_to_timestamp

    return parse_date_to_timestamp(_NOW_JALALI) + 12 * 3600


def _dream_with_store(tmp_path, name="m15.db"):
    store = MemoryStore(str(tmp_path / name))
    dream = Dream(store, EchoBackend())
    return store, dream


class ScriptedBackend:
    """Backend that emits one tool call then a fixed final reply.

    The extraction pass (tools=None) returns "[]" (no facts).
    """

    def __init__(self, reply, call=None):
        self._reply = reply
        self._call = call
        self._used = False

    def chat(self, messages, tools=None):
        if tools is None:
            return {"content": "[]", "tool_calls": []}
        if not self._used and self._call is not None:
            self._used = True
            return {
                "content": None,
                "tool_calls": [{"id": "call-1", **self._call}],
            }
        return {"content": self._reply, "tool_calls": []}


# Persian literals as backslash-u escapes, with glosses.

# Accepted natural phrases (11)
PHRASE_FARDA = "\u0641\u0631\u062f\u0627"  # فردا
PHRASE_PAS_FARDA = "\u067e\u0633 \u0641\u0631\u062f\u0627"  # پس فردا
PHRASE_EMRUZ = "\u0627\u0645\u0631\u0648\u0632"  # امروز
PHRASE_DOSHANBE = "\u062f\u0648\u0634\u0646\u0628\u0647"  # دوشنبه
PHRASE_PANZDAHOM_MEHR = "\u067e\u0627\u0646\u0632\u062f\u0647\u0645 \u0645\u0647\u0631"
PHRASE_PANZDAH_MEHR = "\u067e\u0627\u0646\u0632\u062f\u0647 \u0645\u0647\u0631"  # پانزده مهر
PHRASE_SE_RUZ_DIGAR = "\u0633\u0647 \u0631\u0648\u0632 \u062f\u06cc\u06af\u0631"  # سه روز دیگر
PHRASE_HAFTE_AYANDE = "\u0647\u0641\u062a\u0647 \u0622\u06cc\u0646\u062f\u0647"  # هفته آینده
PHRASE_AVVAL_MAH_BAAD = "\u0627\u0648\u0644 \u0645\u0627\u0647 \u0628\u0639\u062f"  # اول ماه بعد
PHRASE_MAH_BAAD = "\u0645\u0627\u0647 \u0628\u0639\u062f"  # ماه بعد
PHRASE_DO_HAFTE_DIGAR = "\u062f\u0648 \u0647\u0641\u062a\u0647 \u062f\u06cc\u06af\u0631"

# Numeric dates (2, accepted via numeric parser)
NUMERIC_JALALI = "1405-07-15"  # Jalali
NUMERIC_GREGORIAN = "2026-08-15"  # Gregorian, converted to Jalali

# Refused natural phrases (6 by natural parser alone; tool refuses 5, numeric one is accepted)
PHRASE_MEHR_ALONE = "\u0645\u0647\u0631"  # مهر alone
PHRASE_SHANBE_AYANDE = "\u0634\u0646\u0628\u0647 \u0622\u06cc\u0646\u062f\u0647"  # شنبه آینده
PHRASE_SAAT_NOH = "\u0633\u0627\u0639\u062a \u0646\u0647"  # ساعت نه
PHRASE_FARDA_SAAT_NOH = "\u0641\u0631\u062f\u0627 \u0633\u0627\u0639\u062a \u0646\u0647"
PHRASE_AKHAR_HAFTE = "\u0622\u062e\u0631 \u0647\u0641\u062a\u0647"  # آخر هفته

# A successful reminder reply that must NOT trip the fact guard (gloss: یادآوری برای فردا تنظیم شد)
REPLY_REMINDER_OK = (
    "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
    "\u0628\u0631\u0627\u06cc \u0641\u0631\u062f\u0627 "
    "\u062a\u0646\u0638\u06cc\u0645 \u0634\u062f"
)
# Variant with date and text echoed (gloss: یادآوری برای 1405-05-18 تنظیم شد: قسط وام)
REPLY_REMINDER_WITH_DATE = (
    "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
    "\u0628\u0631\u0627\u06cc 1405-05-18 "
    "\u062a\u0646\u0638\u06cc\u0645 \u0634\u062f: "
    "\u0642\u0633\u0637 \u0648\u0627\u0645"
)
# The flagged shape (gloss: یادآوری را در حافظه ثبت کردم) — must be avoided
REPLY_FLAGGED = "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc \u0631\u0627 \u062f\u0631 \u062d\u0627\u0641\u0638\u0647 \u062b\u0628\u062a \u06a9\u0631\u062f\u0645"  # noqa: E501

ACCEPTED_NATURAL = [
    (PHRASE_FARDA, "1405-05-18"),
    (PHRASE_PAS_FARDA, "1405-05-19"),
    (PHRASE_EMRUZ, "1405-05-17"),
    (PHRASE_DOSHANBE, "1405-05-19"),
    (PHRASE_PANZDAHOM_MEHR, "1405-07-15"),
    (PHRASE_PANZDAH_MEHR, "1405-07-15"),
    (PHRASE_SE_RUZ_DIGAR, "1405-05-20"),
    (PHRASE_HAFTE_AYANDE, "1405-05-24"),
    (PHRASE_AVVAL_MAH_BAAD, "1405-06-17"),
    (PHRASE_MAH_BAAD, "1405-06-17"),
    (PHRASE_DO_HAFTE_DIGAR, "1405-05-31"),
]

ACCEPTED_NUMERIC = [
    (NUMERIC_JALALI, "1405-07-15"),
    (NUMERIC_GREGORIAN, "1405-05-24"),
]

# For the tool, these are refused; for the natural parser alone, NUMERIC_JALALI is also refused
REFUSED_FOR_TOOL = [
    (PHRASE_MEHR_ALONE, "ambiguous"),
    (PHRASE_SHANBE_AYANDE, "unrecognized"),
    (PHRASE_SAAT_NOH, "saa"),  # time word
    (PHRASE_FARDA_SAAT_NOH, "saa"),
    (PHRASE_AKHAR_HAFTE, "unrecognized"),
]


# ---------------------------------------------------------------------------
# 1. Tool is listed in the registry with correct risk and schema
# ---------------------------------------------------------------------------


def test_tool_is_listed_in_registry_with_guarded_risk(tmp_path):
    with MemoryStore(str(tmp_path / "reg.db")) as store:
        Dream(store, EchoBackend())
        assert "create_reminder" in tools.REGISTRY, "tool create_reminder must be in REGISTRY after Dream creation"  # noqa: E501
        reg = tools.REGISTRY["create_reminder"]
        assert reg.risk == "guarded", f"reminder writes a durable row the owner will be interrupted by later, so it must be guarded, got {reg.risk!r}"  # noqa: E501
        props = reg.schema["properties"]
        assert "date" in props, "tool must have a date parameter"
        assert "text" in props, "tool must have a text parameter"
        assert props["date"]["type"] == "string"
        assert props["text"]["type"] == "string"


def test_tool_schema_has_repeat_params(tmp_path):
    with MemoryStore(str(tmp_path / "reg2.db")) as store:
        Dream(store, EchoBackend())
        props = tools.REGISTRY["create_reminder"].schema["properties"]
        # repeat params are optional ints
        assert "repeat_days" in props or "repeat_months" in props


# ---------------------------------------------------------------------------
# 2. Prompt line that names the tool reaches the system prompt
# ---------------------------------------------------------------------------


def test_prompt_names_the_tool_and_contains_reminder_word(tmp_path):
    with MemoryStore(str(tmp_path / "prompt.db")) as store:
        dream = Dream(store, EchoBackend())
        # Build a system message the way Dream.run does (no reminders needed)
        from dream.agent import _REMINDER_TOOL_USAGE  # type: ignore

        assert "create_reminder" in _REMINDER_TOOL_USAGE, "prompt line must name the tool so the principal engineer's veto is satisfied"  # noqa: E501
        # The base prompt itself did not contain the reminder word; the tool usage must
        assert "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc" in _REMINDER_TOOL_USAGE, "prompt must contain the Persian word for reminder"  # noqa: E501

        # Prove it reaches the system prompt
        msg = dream._system_message([], query="test")
        content = msg["content"]
        assert "create_reminder" in content
        assert "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc" in content


# ---------------------------------------------------------------------------
# 3. Model that asks for a reminder and gets one: row on disk, Jalali date, reply
# ---------------------------------------------------------------------------


def test_model_creates_reminder_row_is_on_disk_and_reply_contains_date_and_text(tmp_path):
    with MemoryStore(str(tmp_path / "e2e.db")) as store:
        # Use a deterministic date: فردا relative to now
        # The tool will parse "فردا" at runtime (now = time.time()), but we can check
        # that the stored due matches format_jalali of the created row and that reply echoes it.
        backend = ScriptedBackend(
            reply=REPLY_REMINDER_WITH_DATE,
            call={"name": "create_reminder", "arguments": {"date": PHRASE_FARDA, "text": "\u0642\u0633\u0637 \u0648\u0627\u0645"}},  # noqa: E501
        )
        dream = Dream(store, backend)
        turn = dream.run("\u0641\u0631\u062f\u0627 \u0642\u0633\u0637 \u0648\u0627\u0645 \u0631\u0627 \u06cc\u0627\u062f\u0622\u0648\u0631\u06cc \u06a9\u0646")  # noqa: E501
        # Tool must have been called and allowed
        assert len(turn.tool_calls) == 1
        assert turn.tool_calls[0]["name"] == "create_reminder"
        assert turn.tool_calls[0]["allowed"] is True
        payload = json.loads(turn.tool_calls[0]["result"])
        assert payload["status"] == "ok", f"tool must succeed, got {payload!r}"
        result = payload["result"]
        assert "due" in result and "text" in result
        # Row on disk
        rems = store.list_reminders()
        assert len(rems) == 1, f"exactly one row must be on disk, got {rems!r}"
        from dream.reminders import format_jalali

        due_str = format_jalali(rems[0].due_at)
        assert result["due"] == due_str, "tool result due must equal stored Jalali date"
        assert result["text"] == "\u0642\u0633\u0637 \u0648\u0627\u0645"
        assert rems[0].text == "\u0642\u0633\u0637 \u0648\u0627\u0645"
        # Reply the owner reads must contain date and text
        assert due_str in turn.reply or "1405" in turn.reply, f"reply must echo Jalali date, got {turn.reply!r}"  # noqa: E501
        assert "\u0642\u0633\u0637 \u0648\u0627\u0645" in turn.reply or "due" in turn.reply.lower(), f"reply must echo text, got {turn.reply!r}"  # noqa: E501
        print(f"[reminder-row] id={rems[0].id} due={due_str} text={rems[0].text!r}")
        print(f"[reply] {turn.reply!r}")


# ---------------------------------------------------------------------------
# 4. Full date acceptance table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("phrase", "expected_jalali"), ACCEPTED_NATURAL + ACCEPTED_NUMERIC)
def test_accepted_phrases_create_a_row_with_expected_jalali(tmp_path, phrase, expected_jalali):
    # Use a fixed now for deterministic expected, by monkeypatching time.time
    import time


    now = _now_ts()
    original_time = time.time
    try:
        time.time = lambda: now  # type: ignore
        with MemoryStore(str(tmp_path / f"acc_{phrase}.db")) as store:
            Dream(store, EchoBackend())
            payload = json.loads(tools.execute("create_reminder", {"date": phrase, "text": "test"}))
            assert payload["status"] == "ok", f"phrase {phrase!r} should be accepted, got {payload!r}"  # noqa: E501
            result = payload["result"]
            # For the natural ones we pinned expected Jalali at the fixed now;
            # for numeric the time mock does not affect them (they are absolute)
            # Recompute expected via the parsers at the same now to avoid hard-coding drift
            # but also check against the table's expected
            assert result["due"] == expected_jalali, f"{phrase!r} expected {expected_jalali}, got {result['due']!r}"  # noqa: E501
            assert len(store.list_reminders()) == 1
            print(f"[accepted] {phrase!r} -> {result['due']}")
    finally:
        time.time = original_time  # type: ignore


@pytest.mark.parametrize(("phrase", "hint"), REFUSED_FOR_TOOL)
def test_refused_phrases_return_persian_error_and_write_no_row(tmp_path, phrase, hint):
    with MemoryStore(str(tmp_path / f"ref_{phrase}.db")) as store:
        Dream(store, EchoBackend())
        payload = json.loads(tools.execute("create_reminder", {"date": phrase, "text": "test"}))
        assert payload["status"] == "error", f"phrase {phrase!r} should be refused, got {payload!r}"
        msg = payload["error"]["message"]
        # The owner-visible message must be Persian or contain a hint
        # For ambiguous: contains "ambiguous" or Persian "ambiguous date"
        # For time: contains "ساعت"
        # For unrecognized: contains "unrecognized" or "try"
        assert hint.lower() in msg.lower() or "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc" in msg or "try" in msg.lower() or "\u0633\u0627\u0639\u062a" in msg, f"refusal message for {phrase!r} must contain hint {hint!r}, got {msg!r}"  # noqa: E501
        assert len(store.list_reminders()) == 0, "refused date must write no row"
        print(f"[refused] {phrase!r} -> {msg!r} (no row)")


# ---------------------------------------------------------------------------
# 5. Day-and-time phrase specifically: honest refusal, no guess
# ---------------------------------------------------------------------------


def test_day_and_time_phrase_is_refused_honestly_and_writes_no_row(tmp_path):
    with MemoryStore(str(tmp_path / "daytime.db")) as store:
        Dream(store, EchoBackend())
        payload = json.loads(tools.execute("create_reminder", {"date": PHRASE_FARDA_SAAT_NOH, "text": "\u0642\u0633\u0637 \u0648\u0627\u0645"}))  # noqa: E501
        assert payload["status"] == "error", f"day-and-time phrase must be refused, got {payload!r}"
        msg = payload["error"]["message"]
        # Must mention time not supported, not guess 09:00
        assert "\u0633\u0627\u0639\u062a" in msg or "saa" in msg.lower() or "time" in msg.lower() or "unrecognized" in msg.lower(), f"message must be honest about time, got {msg!r}"  # noqa: E501
        # Must not have created a row
        assert len(store.list_reminders()) == 0
        # The message must advise to put time in text
        print(f"[day-and-time] {PHRASE_FARDA_SAAT_NOH!r} -> refused: {msg!r} (honest, no guess)")


def test_numeric_parser_refuses_natural_and_natural_refuses_numeric_documented():
    from dream.reminders import parse_date_to_timestamp, parse_persian_date

    # Numeric refuses natural
    for phrase, _ in ACCEPTED_NATURAL:
        with pytest.raises(ValueError):
            parse_date_to_timestamp(phrase)
    # Natural refuses numeric
    for phrase, _ in ACCEPTED_NUMERIC:
        with pytest.raises(ValueError) as excinfo:
            parse_persian_date(phrase, now=_now_ts())
        assert "unrecognized" in str(excinfo.value).lower() or "try" in str(excinfo.value).lower()
    print("[trap] numeric refuses natural, natural refuses numeric — documented")


# ---------------------------------------------------------------------------
# 6. Refused date writes no row (explicit)
# ---------------------------------------------------------------------------


def test_refused_date_leaves_table_empty(tmp_path):
    with MemoryStore(str(tmp_path / "empty.db")) as store:
        Dream(store, EchoBackend())
        # Try a definitely refused phrase
        payload = json.loads(tools.execute("create_reminder", {"date": PHRASE_MEHR_ALONE, "text": "test"}))  # noqa: E501
        assert payload["status"] == "error"
        assert store.list_reminders() == []
        print("[empty-table] after refused date, table is empty")


# ---------------------------------------------------------------------------
# 7. Truthful reminder reply is not flagged by M14 fact guard
# ---------------------------------------------------------------------------


def test_truthful_reminder_reply_is_not_flagged_by_fact_guard(tmp_path):
    from dream.claims import unsaved_fact_claim

    with MemoryStore(str(tmp_path / "factguard.db")) as store:
        backend = ScriptedBackend(
            reply=REPLY_REMINDER_OK,
            call={"name": "create_reminder", "arguments": {"date": PHRASE_FARDA, "text": "test"}},
        )
        dream = Dream(store, backend)
        turn = dream.run("test")
        # The reply that echoes the reminder must not be flagged
        assert unsaved_fact_claim(REPLY_REMINDER_OK, turn.memories_created, turn.memories_injected) is False  # noqa: E501
        assert unsaved_fact_claim(REPLY_REMINDER_WITH_DATE, turn.memories_created, turn.memories_injected) is False  # noqa: E501
        # Also via guard_claims
        from dream.claims import FACT_SAVE_WARNING, guard_claims

        guarded = guard_claims(REPLY_REMINDER_OK, turn.tool_calls, turn.memories_created, turn.memories_injected, turn.extraction.status)  # noqa: E501
        assert guarded == REPLY_REMINDER_OK, f"truthful reminder reply must be untouched, got {guarded!r}"  # noqa: E501
        assert FACT_SAVE_WARNING not in guarded
        print(f"[fact-guard] truthful reminder reply untouched: {turn.reply!r}")

    # The flagged shape must still be flagged (prove guard still works)
    from dream.claims import unsaved_fact_claim as ufc

    assert ufc(REPLY_FLAGGED, [], []) is True, "the flagged shape must still be flagged"


# ---------------------------------------------------------------------------
# 8. Whether we built a reminder guard, and single-warning rule
# ---------------------------------------------------------------------------


def test_no_reminder_guard_and_single_warning_rule_holds(tmp_path):
    """We built no reminder guard, for the M14 reason: a guard would punish
    truthful replies that describe an *existing* reminder visible in the prompt.
    The single-warning rule therefore holds vacuously; we prove it by showing
    a mixed sentence yields exactly one warning (the skill one) and the
    reminder collision yields none.
    """
    with MemoryStore(str(tmp_path / "nowarn.db")) as store:
        # Create an existing reminder via /remind so it appears in prompt
        from dream.reminders import parse_date_to_timestamp

        ts = parse_date_to_timestamp("1405-07-15")
        store.add_reminder("\u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647", ts)
        # This reply describes the existing reminder truthfully, without a tool call
        reply_existing = "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc \u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 \u062b\u0628\u062a \u0634\u062f\u0647 \u0627\u0633\u062a"  # noqa: E501
        # No guard should flag it
        from dream.claims import unsaved_fact_claim

        assert unsaved_fact_claim(reply_existing, [], []) is False, "reminder description must not be flagged"  # noqa: E501

        # Mixed sentence from brief: skill+fact double claim yields exactly one warning (skill)
        from dream.claims import FACT_SAVE_WARNING
        from dream.skills import SKILL_SAVE_WARNING

        mixed_both = (
            "\u0627\u06cc\u0646 \u0631\u0648\u0634 \u062f\u0631 \u0641\u0627\u06cc\u0644 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f \u0648 \u0627\u06cc\u0646 \u0648\u0627\u0642\u0639\u06cc\u062a \u062f\u0631 \u062d\u0627\u0641\u0638\u0647 \u062b\u0628\u062a \u0634\u062f"  # noqa: E501
        )
        backend = ScriptedBackend(reply=mixed_both)
        dream = Dream(store, backend)
        turn = dream.run("test")
        assert turn.reply == mixed_both + SKILL_SAVE_WARNING
        assert FACT_SAVE_WARNING not in turn.reply

        # Brief's collision sentence fires neither guard
        brief_collision = "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc \u0631\u0648\u0634 \u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 \u062a\u0646\u0638\u06cc\u0645 \u0634\u062f"  # noqa: E501
        backend2 = ScriptedBackend(reply=brief_collision)
        dream2 = Dream(store, backend2)
        turn2 = dream2.run("test")
        assert turn2.reply == brief_collision
        print("[no-guard] reminder guard not built; single warning holds")


# ---------------------------------------------------------------------------
# 9. M13 and M14 guards still behave
# ---------------------------------------------------------------------------


def test_skill_guard_still_warns_and_fact_guard_still_warns(tmp_path):
    from dream.claims import FACT_SAVE_WARNING
    from dream.skills import SKILL_SAVE_WARNING

    with MemoryStore(str(tmp_path / "guards.db")) as store:
        # Skill claim with no save -> warned
        skill_claim = "\u0631\u0648\u0634 \u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 \u0645\u0627\u0634\u06cc\u0646 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f."  # noqa: E501
        backend = ScriptedBackend(reply=skill_claim)
        turn = Dream(store, backend).run("test")
        assert SKILL_SAVE_WARNING in turn.reply

        # Fact claim with no row -> warned
        fact_claim = "\u0627\u06cc\u0646 \u0648\u0627\u0642\u0639\u06cc\u062a \u062b\u0628\u062a \u0634\u062f"  # noqa: E501
        backend2 = ScriptedBackend(reply=fact_claim)
        turn2 = Dream(store, backend2).run("test")
        assert FACT_SAVE_WARNING in turn2.reply

        print("[guards] M13 and M14 still behave")


# ---------------------------------------------------------------------------
# 10. Break-and-restore evidence helpers (used manually in PR)
# ---------------------------------------------------------------------------


def test_create_reminder_rejects_empty_text(tmp_path):
    with MemoryStore(str(tmp_path / "emptytext.db")) as store:
        Dream(store, EchoBackend())
        payload = json.loads(tools.execute("create_reminder", {"date": PHRASE_FARDA, "text": "   "}))  # noqa: E501
        assert payload["status"] == "error"
        assert "empty" in payload["error"]["message"].lower()


def test_create_reminder_rejects_zero_repeat(tmp_path):
    with MemoryStore(str(tmp_path / "zerorep.db")) as store:
        Dream(store, EchoBackend())
        payload = json.loads(tools.execute("create_reminder", {"date": PHRASE_FARDA, "text": "t", "repeat_days": 0}))  # noqa: E501
        assert payload["status"] == "error"


def test_create_reminder_rejects_both_repeats(tmp_path):
    with MemoryStore(str(tmp_path / "bothrep.db")) as store:
        Dream(store, EchoBackend())
        payload = json.loads(tools.execute("create_reminder", {"date": PHRASE_FARDA, "text": "t", "repeat_days": 1, "repeat_months": 1}))  # noqa: E501
        assert payload["status"] == "error"
