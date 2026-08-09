"""Pins M19: the owner can take a reminder back by asking, in conversation.

What this pins and what evidence justified it:

- On merged trunk the model can create a reminder (M15) but cannot take one
  back: the registry lists no cancellation tool, and the owner must open a
  terminal or the phone for ``/unremind``. Measured: the reminders render in
  the prompt section as text plus a stored Jalali date and *nothing else* —
  no identifier. A probe storing two «loan instalment» rows (due 1405-05-19
  and 1405-05-21) prints two identical lines with different dates, so a
  cancellation tool that takes only the text cannot tell them apart, and a
  tool that takes a row number asks the model for something it was never
  shown (the principal engineer's veto, measured).

- Identification decision pinned here: the tool takes the reminder *text*
  the owner says, plus an *optional date*; it matches against the active
  reminders itself (normalized exact match first, unique substring match
  second), applies the date as a filter when given, and **refuses and asks**
  when more than one row fits (data integrity veto: ask, not choose). The
  refusal names every candidate with its Jalali date so the owner can
  answer. Arguments stay obtainable from what the model is shown: the text
  comes from the owner's own message, the dates render in the prompt
  section. A read-back tool is *not* required by this decision; the tool
  reads the store directly.

- Removal decision pinned here: the conversational path deletes the row
  through the store's existing ``delete_reminder``, the same permanent
  removal ``/unremind`` performs, because no surface can reactivate an
  inactive reminder (measured: only the scheduler clears ``active``, and
  only when a one-off fires), so a deactivate-without-restore would be
  cosmetic gentleness that leaves residue in ``/reminders all`` and makes
  the two surfaces disagree. The safeguard is in the identification
  protocol: a row leaves only when exactly one row fits, and the
  confirmation names text, Jalali date and repeat rule so the owner can
  verify and, if ever wrong, recreate verbatim. A store-level reminder
  archive with a reactivation surface is reported as a future finding, not
  built (store and scheduler are out of budget).

- A fired one-off (inactive row) must not be cancellable in conversation:
  matching runs on the active listing, and the inactive row must remain in
  the full listing, untouched (measured: fired rows survive with ``active``
  false under ``include_inactive=True``).

- A truthful Persian confirmation («یادآوری «...» برای 1405-05-19 لغو شد.»)
  must not trip the M13 skill guard or the M14 fact guard; measured against
  the guards before implementation (no save stem, no skill noun, no fact
  noun in the sentence).

- The conversation removal and the slash removal must agree: after the
  tool removes a row, both the active listing and the full listing must
  equal what ``/unremind``'s store call would leave, with no residue.

Tests are written first and observed red against unchanged source before
any implementation, then green after. Every new Persian string below is a
backslash-u escape with a plain gloss comment, matching the repository
convention.
"""

from __future__ import annotations

import json

from dream import tools
from dream.agent import Dream, EchoBackend
from dream.memory import MemoryStore

# ---------------------------------------------------------------------------
# Persian literals as backslash-u escapes, with glosses.
# ---------------------------------------------------------------------------

_T_LOAN = "\u0642\u0633\u0637 \u0648\u0627\u0645"  # قسط وام
_T_INS = "\u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647"  # تمدید بیمه
_T_CAR_INS = (
    "\u062a\u0645\u062f\u06cc\u062f "
    "\u0628\u06cc\u0645\u0647 \u0645\u0627\u0634\u06cc\u0646"
)  # تمدید بیمه ماشین
_T_MOTO_INS = (
    "\u062a\u0645\u062f\u06cc\u062f "
    "\u0628\u06cc\u0645\u0647 \u0645\u0648\u062a\u0648\u0631"
)  # تمدید بیمه موتور
_T_BILL = "\u0642\u0628\u0636 \u0628\u0631\u0642"  # قبض برق
_T_MISS = "\u067e\u0631\u062f\u0627\u062e\u062a \u0642\u0628\u0636"  # پرداخت قبض
_T_DOCTOR = (
    "\u0645\u0644\u0627\u0642\u0627\u062a "
    "\u0628\u0627 \u062f\u06a9\u062a\u0631"
)  # ملاقات با دکتر
_Q_INS = "\u0628\u06cc\u0645\u0647"  # بیمه (substring query)
_Q_TEA = "\u0686\u0627\u06cc"  # چای (present in no reminder)

# The owner's spoken request for the end-to-end turn: یادآوری تمدید بیمه را لغو کن
_ASK_CANCEL_INS = (
    "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc "
    "\u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 "
    "\u0631\u0627 \u0644\u063a\u0648 \u06a9\u0646"
)

# Phrase halves of the mandated refusal/confirmation wording.
_W_CANCEL = "\u0644\u063a\u0648"  # لغو
_W_ASK = "\u06a9\u062f\u0627\u0645"  # کدام
_W_NOTFOUND = "\u067e\u06cc\u062f\u0627 \u0646\u0634\u062f"  # پیدا نشد
_W_CANDIDATES = "\u0645\u0648\u0627\u0631\u062f"  # موارد
_W_REPEAT = "\u062a\u06a9\u0631\u0627\u0631"  # تکرار
_W_MONTH = "\u0645\u0627\u0647"  # ماه
_W_SAAT = "\u0633\u0627\u0639\u062a"  # ساعت
_W_SUPPORT = "\u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc"  # پشتیبانی (پشتیبانی نمی‌شود)
_W_ASKNOTCHOOSE = (
    "\u062e\u0648\u062f\u062a \u0627\u0646\u062a\u062e\u0627\u0628 "
    "\u0646\u06a9\u0646"
)  # خودت انتخاب نکن

_FARDA = "\u0641\u0631\u062f\u0627"  # فردا
_FARDA_SAAT_NOH = (
    "\u0641\u0631\u062f\u0627 "
    "\u0633\u0627\u0639\u062a \u0646\u0647"
)  # فردا ساعت نه
_MEHR = "\u0645\u0647\u0631"  # مهر

# Fixed reference noon at 1405-05-17 for the natural-date phrase variant.
_NOW_JALALI = "1405-05-17"

# The three rows of the brief's measurement.
_LOAN_19 = (_T_LOAN, "1405-05-19")
_INS_20 = (_T_INS, "1405-05-20")
_LOAN_21 = (_T_LOAN, "1405-05-21")


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
            return {"content": None, "tool_calls": [{"id": "call-1", **self._call}]}
        return {"content": self._reply, "tool_calls": []}


class ConfirmEchoBackend(ScriptedBackend):
    """A prompt-following model: repeats the tool's confirmation verbatim.

    Stands in for a model obeying the prompt rule "repeat the cancelled text
    and Jalali date exactly as the tool returned them": after the tool
    result lands in history it answers with that message verbatim.
    """

    def chat(self, messages, tools=None):
        if tools is not None and messages and messages[-1].get("role") == "tool":
            payload = json.loads(messages[-1]["content"])
            return {"content": payload["result"]["message"], "tool_calls": []}
        return super().chat(messages, tools)


def _now_ts():
    from dream.reminders import parse_date_to_timestamp

    return parse_date_to_timestamp(_NOW_JALALI) + 12 * 3600


def _seed_brief_rows(store):
    """Store the brief's three rows; return {label: row} by due-date key."""
    from dream.reminders import parse_date_to_timestamp

    rows = {}
    for text, jalali in (_LOAN_19, _INS_20, _LOAN_21):
        rows[jalali] = store.add_reminder(text, parse_date_to_timestamp(jalali))
    return rows


def _listing(store, include_inactive=False):
    return [
        (rem.text, rem.due_at, rem.repeat_days, rem.repeat_months, rem.active)
        for rem in store.list_reminders(include_inactive=include_inactive)
    ]


def _execute_cancel(text, date=None):
    arguments = {"text": text}
    if date is not None:
        arguments["date"] = date
    return json.loads(tools.execute("cancel_reminder", arguments))


# ---------------------------------------------------------------------------
# 1. The tool is in the registry, guarded, with text and optional date.
# ---------------------------------------------------------------------------


def test_tool_is_listed_in_registry_with_guarded_risk(tmp_path):
    with MemoryStore(str(tmp_path / "reg.db")) as store:
        Dream(store, EchoBackend())
        assert "cancel_reminder" in tools.REGISTRY, (
            f"cancel_reminder must be a registered tool after Dream creation; "
            f"registry holds {sorted(tools.REGISTRY)}"
        )
        reg = tools.REGISTRY["cancel_reminder"]
        assert reg.risk == "guarded", (
            f"a local, intentional removal the owner confirms in conversation is "
            f"guarded (dangerous would demand an approver the phone cannot show), "
            f"got {reg.risk!r}"
        )
        props = reg.schema["properties"]
        assert "text" in props and props["text"]["type"] == "string"
        assert "date" in props and props["date"]["type"] == "string"
        assert reg.schema.get("required") == ["text"], (
            f"only text must be required; date is the optional disambiguator, "
            f"got {reg.schema.get('required')!r}"
        )
        print(f"[registry] cancel_reminder risk={reg.risk!r} schema={reg.schema!r}")


# ---------------------------------------------------------------------------
# 2. The prompt names the tool, says ask-not-choose, and reaches the prompt.
# ---------------------------------------------------------------------------


def test_prompt_names_cancel_tool_says_ask_not_choose_and_reaches_prompt(tmp_path):
    import dream.agent as agent_module

    usage = getattr(agent_module, "_REMINDER_CANCEL_USAGE", None)
    assert usage is not None, (
        "dream.agent must define _REMINDER_CANCEL_USAGE naming cancel_reminder; "
        "a tool the prompt never names is never chosen (measured M10 principle)"
    )
    assert "cancel_reminder" in usage, "the prompt line must name the tool"
    assert _W_CANCEL in usage, "the prompt must speak of cancellation in Persian"
    assert _W_ASKNOTCHOOSE in usage, (
        "the prompt must tell the model to ask the owner rather than choose "
        "between rows it cannot tell apart (data integrity veto)"
    )
    with MemoryStore(str(tmp_path / "prompt.db")) as store:
        dream = Dream(store, EchoBackend())
        content = dream._system_message([], query="test")["content"]
        assert "cancel_reminder" in content
        assert _W_CANCEL in content
        print("[prompt] _REMINDER_CANCEL_USAGE reaches the system prompt")


# ---------------------------------------------------------------------------
# 3. The owner asks in ordinary Persian and one reminder disappears.
# ---------------------------------------------------------------------------


def test_owner_asks_in_persian_and_one_reminder_disappears(tmp_path):
    from dream.reminders import format_jalali

    with MemoryStore(str(tmp_path / "e2e.db")) as store:
        rows = _seed_brief_rows(store)
        backend = ConfirmEchoBackend(
            reply="",
            call={
                "name": "cancel_reminder",
                "arguments": {"text": _T_INS},
            },
        )
        dream = Dream(store, backend)
        before = _listing(store)
        turn = dream.run(_ASK_CANCEL_INS)
        after = _listing(store)
        assert len(before) == 3 and len(after) == 2, (
            f"exactly one row must disappear: before={before!r} after={after!r}"
        )
        assert len(turn.tool_calls) == 1
        call = turn.tool_calls[0]
        assert call["name"] == "cancel_reminder" and call["allowed"] is True
        payload = json.loads(call["result"])
        assert payload["status"] == "ok", f"the call must succeed, got {payload!r}"
        result = payload["result"]
        due = format_jalali(rows["1405-05-20"].due_at)
        assert result["text"] == _T_INS and result["due"] == due
        assert result["id"] == rows["1405-05-20"].id
        message = result["message"]
        assert _T_INS in message and due in message and _W_CANCEL in message, (
            f"the confirmation must name what was removed, in Jalali, in "
            f"Persian, got {message!r}"
        )
        removed_ids = {r.id for r in store.list_reminders()}
        assert rows["1405-05-20"].id not in removed_ids
        assert rows["1405-05-19"].id in removed_ids
        assert rows["1405-05-21"].id in removed_ids
        # The confirmation reaches the owner exactly as the tool stated it:
        # the prompt-following model repeated it and the claim guards left
        # the truthful sentence untouched (also pinned at the guard seam).
        assert turn.reply == message, (
            f"the owner must read the tool's own confirmation, got {turn.reply!r}"
        )
        output_lines = [
            f"[row-before] {[(t, format_jalali(d), act) for t, d, _, _, act in before]}",
            f"[row-after] {[(t, format_jalali(d), act) for t, d, _, _, act in after]}",
            f"[confirmation] {turn.reply}",
        ]
        print("\n".join(output_lines))


# ---------------------------------------------------------------------------
# 4. Two reminders with the same text: refuse and name the candidates.
# ---------------------------------------------------------------------------


def test_same_text_two_dates_refuses_and_names_candidates(tmp_path):
    with MemoryStore(str(tmp_path / "ambig.db")) as store:
        _seed_brief_rows(store)
        Dream(store, EchoBackend())
        payload = _execute_cancel(_T_LOAN)
        assert payload["status"] == "error", (
            f"two same-text rows must not be guessed between, got {payload!r}"
        )
        message = payload["error"]["message"]
        assert _W_ASK in message, f"the refusal must ask which one: {message!r}"
        assert "1405-05-19" in message and "1405-05-21" in message, (
            f"the refusal must name the candidates by Jalali date: {message!r}"
        )
        assert len(store.list_reminders()) == 3, "a refusal must touch no row"
        print(f"[ambiguous] {message}")


# ---------------------------------------------------------------------------
# 5. Text plus date disambiguates and cancels the right row.
# ---------------------------------------------------------------------------


def test_text_plus_date_disambiguates_and_cancels_the_right_row(tmp_path):
    with MemoryStore(str(tmp_path / "dated.db")) as store:
        rows = _seed_brief_rows(store)
        Dream(store, EchoBackend())
        payload = _execute_cancel(_T_LOAN, "1405-05-21")
        assert payload["status"] == "ok", f"text+date must succeed, got {payload!r}"
        result = payload["result"]
        assert result["id"] == rows["1405-05-21"].id
        assert "1405-05-21" in result["message"]
        remaining = {r.id for r in store.list_reminders()}
        assert rows["1405-05-21"].id not in remaining, "the 21st must be cancelled"
        assert rows["1405-05-19"].id in remaining, "the 19th must survive untouched"
        assert rows["1405-05-20"].id in remaining
        print(f"[dated] {result['message']}")


def test_text_plus_natural_date_phrase_disambiguates(tmp_path):
    import time

    with MemoryStore(str(tmp_path / "datedfa.db")) as store:
        _seed_brief_rows(store)
        Dream(store, EchoBackend())
        now = _now_ts()
        original_time = time.time
        try:
            time.time = lambda: now  # type: ignore
            # Rows are absolute (seeded without the clock); «فردا» resolves
            # against the fixed noon of 1405-05-17, i.e. 1405-05-18, which
            # matches no seeded row — so seed one for this phrase instead.
            from dream.reminders import format_jalali, parse_date_to_timestamp

            extra = store.add_reminder(_T_LOAN, parse_date_to_timestamp("1405-05-18"))
            payload = _execute_cancel(_T_LOAN, _FARDA)
        finally:
            time.time = original_time  # type: ignore
        assert payload["status"] == "ok", (
            f"text+«فردا» must cancel the 1405-05-18 row, got {payload!r}"
        )
        assert payload["result"]["id"] == extra.id
        assert payload["result"]["due"] == format_jalali(extra.due_at)
        assert len(store.list_reminders()) == 3, (
            "the three brief rows must survive: only the «فردا» row may go"
        )
        print(f"[dated-phrase] {payload['result']['message']}")


# ---------------------------------------------------------------------------
# 6. Cancelling something that does not exist touches nothing.
# ---------------------------------------------------------------------------


def test_cancel_of_nonexistent_reminder_touches_nothing(tmp_path):
    with MemoryStore(str(tmp_path / "miss.db")) as store:
        _seed_brief_rows(store)
        Dream(store, EchoBackend())
        before = _listing(store)
        payload = _execute_cancel(_T_MISS)
        after = _listing(store)
        assert payload["status"] == "error", (
            f"a missing reminder must be a refusal, got {payload!r}"
        )
        message = payload["error"]["message"]
        assert _W_NOTFOUND in message, (
            f"the refusal must say nothing was found: {message!r}"
        )
        assert _T_MISS in message, f"the refusal echoes the asked text: {message!r}"
        assert before == after, (
            f"no row may be touched: before={before!r} after={after!r}"
        )
        payload_absent = _execute_cancel(_Q_TEA)
        assert payload_absent["status"] == "error"
        assert _listing(store) == before
        print(f"[missing] {message} | rows unchanged: {len(after)}")


# ---------------------------------------------------------------------------
# 7. Unique substring cancels, naming the full text; multi-substring refuses.
# ---------------------------------------------------------------------------


def test_unique_substring_match_cancels_and_names_full_text(tmp_path):
    from dream.reminders import parse_date_to_timestamp

    with MemoryStore(str(tmp_path / "subst.db")) as store:
        car = store.add_reminder(_T_CAR_INS, parse_date_to_timestamp("1405-06-01"))
        loan = store.add_reminder(_T_LOAN, parse_date_to_timestamp("1405-05-19"))
        Dream(store, EchoBackend())
        payload = _execute_cancel(_Q_INS)
        assert payload["status"] == "ok", (
            f"a unique substring match must cancel, got {payload!r}"
        )
        message = payload["result"]["message"]
        assert _T_CAR_INS in message, (
            f"the confirmation must name the full stored text, not the "
            f"fragment: {message!r}"
        )
        remaining = {r.id for r in store.list_reminders()}
        assert car.id not in remaining and loan.id in remaining
        print(f"[substring] {message}")


def test_multi_substring_match_refuses_and_names_candidates(tmp_path):
    from dream.reminders import parse_date_to_timestamp

    with MemoryStore(str(tmp_path / "subst2.db")) as store:
        store.add_reminder(_T_CAR_INS, parse_date_to_timestamp("1405-06-01"))
        store.add_reminder(_T_MOTO_INS, parse_date_to_timestamp("1405-06-02"))
        Dream(store, EchoBackend())
        payload = _execute_cancel(_Q_INS)
        assert payload["status"] == "error", (
            f"a fragment matching two rows must refuse, got {payload!r}"
        )
        message = payload["error"]["message"]
        assert _T_CAR_INS in message and _T_MOTO_INS in message
        assert "1405-06-01" in message and "1405-06-02" in message
        assert len(store.list_reminders()) == 2
        print(f"[substring-multi] {message}")


# ---------------------------------------------------------------------------
# 8. A date that matches no row names the existing candidates and touches none.
# ---------------------------------------------------------------------------


def test_date_filter_no_match_lists_existing_candidates(tmp_path):
    with MemoryStore(str(tmp_path / "datenone.db")) as store:
        _seed_brief_rows(store)
        Dream(store, EchoBackend())
        payload = _execute_cancel(_T_LOAN, "1405-05-25")
        assert payload["status"] == "error", (
            f"a date with no matching row must refuse, got {payload!r}"
        )
        message = payload["error"]["message"]
        assert _W_CANDIDATES in message, (
            f"the refusal must show what exists so the owner can correct the "
            f"date: {message!r}"
        )
        assert "1405-05-19" in message and "1405-05-21" in message
        assert len(store.list_reminders()) == 3
        print(f"[date-no-match] {message}")


# ---------------------------------------------------------------------------
# 9. A fired one-off (inactive) cannot be cancelled; the row stays listed.
# ---------------------------------------------------------------------------


def test_fired_oneoff_cannot_be_cancelled_and_stays_listed(tmp_path):
    from dream.reminders import parse_date_to_timestamp

    with MemoryStore(str(tmp_path / "fired.db")) as store:
        fired = store.add_reminder(_T_DOCTOR, parse_date_to_timestamp("1405-05-01"))
        store.check_due_reminders(
            now=parse_date_to_timestamp("1405-05-02") + 3600, destination="terminal"
        )
        Dream(store, EchoBackend())
        before = _listing(store, include_inactive=True)
        assert not store.list_reminders(), "the fired one-off must be inactive"
        payload = _execute_cancel(_T_DOCTOR)
        after = _listing(store, include_inactive=True)
        assert payload["status"] == "error", (
            f"an inactive reminder must not be cancellable, got {payload!r}"
        )
        assert _W_NOTFOUND in payload["error"]["message"]
        assert before == after, (
            f"the fired row must stay listed and untouched: "
            f"before={before!r} after={after!r}"
        )
        assert fired.id in {r.id for r in store.list_reminders(include_inactive=True)}
        print(f"[fired-oneoff] refused; inactive row intact (id={fired.id})")


def test_fired_repeating_reminder_is_cancellable_without_delivery_residue(tmp_path):
    """A fired repeating reminder has reminder_deliveries children; the FK
    without ON DELETE CASCADE makes the parent undeletable — measured on
    merged trunk, where ``/unremind`` raises IntegrityError and the row
    survives (reported as a store finding; store and scheduler are frozen).
    The conversational path removes the child rows with the parent, in the
    store's own lock, so the owner can cancel a monthly bill that already
    fired once. Pinned: cancel succeeds, parent gone, no deliveries left.
    """
    from dream.reminders import parse_date_to_timestamp

    with MemoryStore(str(tmp_path / "firedrep.db")) as store:
        fired = store.add_reminder(
            _T_BILL, parse_date_to_timestamp("1405-04-19"), repeat_months=1
        )
        store.check_due_reminders(
            now=parse_date_to_timestamp("1405-05-01"), destination="terminal"
        )
        before_children = store.conn.execute(
            "SELECT COUNT(*) FROM reminder_deliveries WHERE reminder_id = ?",
            (fired.id,),
        ).fetchone()[0]
        assert before_children == 1, "the fire must have recorded a delivery"
        Dream(store, EchoBackend())
        payload = _execute_cancel(_T_BILL)
        assert payload["status"] == "ok", (
            f"a fired repeating reminder must be cancellable, got {payload!r}"
        )
        assert not store.list_reminders(), "the parent row must be gone"
        after_children = store.conn.execute(
            "SELECT COUNT(*) FROM reminder_deliveries WHERE reminder_id = ?",
            (fired.id,),
        ).fetchone()[0]
        assert after_children == 0, (
            "delivery rows must not outlive their reminder (FK intent); "
            f"{after_children} residue left"
        )
        assert not store.list_reminders(include_inactive=True)
        print(
            f"[fired-repeating] cancelled id={fired.id}; deliveries "
            f"{before_children} -> {after_children}; no residue"
        )


# ---------------------------------------------------------------------------
# 10. A truthful cancellation confirmation trips neither M13 nor M14 guard.
# ---------------------------------------------------------------------------


def test_truthful_cancellation_reply_does_not_trip_claim_guards(tmp_path):
    from dream.claims import FACT_SAVE_WARNING, guard_claims, unsaved_fact_claim
    from dream.reminders import format_jalali
    from dream.skills import SKILL_SAVE_WARNING, unsaved_skill_claim

    with MemoryStore(str(tmp_path / "guards.db")) as store:
        rows = _seed_brief_rows(store)
        due = format_jalali(rows["1405-05-20"].due_at)
        # The model repeats the tool's confirmation (the prompt rule); the
        # guards then decide whether that truthful sentence is warned.
        backend = ConfirmEchoBackend(
            reply="",
            call={"name": "cancel_reminder", "arguments": {"text": _T_INS}},
        )
        dream = Dream(store, backend)
        turn = dream.run(_ASK_CANCEL_INS)
        payload = json.loads(turn.tool_calls[0]["result"])
        assert payload["status"] == "ok"
        confirmation = payload["result"]["message"]
        assert _T_INS in confirmation and due in confirmation
        assert turn.reply == confirmation, (
            f"guards must leave the truthful confirmation byte for byte at the "
            f"turn seam, got {turn.reply!r}"
        )
        # Measured against both guards directly and through the turn seam.
        assert unsaved_skill_claim(confirmation, turn.tool_calls) is False, (
            f"M13 skill guard must be silent on a cancellation: {confirmation!r}"
        )
        assert unsaved_fact_claim(
            confirmation, turn.memories_created, turn.memories_injected
        ) is False, f"M14 fact guard must be silent on a cancellation: {confirmation!r}"
        guarded = guard_claims(
            confirmation,
            turn.tool_calls,
            turn.memories_created,
            turn.memories_injected,
            turn.extraction.status,
        )
        assert guarded == confirmation, (
            f"a truthful cancellation confirmation must pass byte for byte, "
            f"got {guarded!r}"
        )
        assert SKILL_SAVE_WARNING not in guarded
        assert FACT_SAVE_WARNING not in guarded
        print(f"[guards-silent] truthful confirmation untouched: {confirmation!r}")


# ---------------------------------------------------------------------------
# 11. Time words and ambiguous dates in the date filter refuse and touch nothing.
# ---------------------------------------------------------------------------


def test_time_word_in_date_is_refused_and_touches_nothing(tmp_path):
    with MemoryStore(str(tmp_path / "time.db")) as store:
        _seed_brief_rows(store)
        Dream(store, EchoBackend())
        payload = _execute_cancel(_T_LOAN, _FARDA_SAAT_NOH)
        assert payload["status"] == "error"
        message = payload["error"]["message"]
        assert _W_SAAT in message and _W_SUPPORT in message, (
            f"a time word must be refused with the honest time-hint "
            f"(«ساعت ... پشتیبانی نمی‌شود»), not the generic unrecognized-date "
            f"echo that also contains the word ساعت — measured: only "
            f"«پشتیبانی» separates them: {message!r}"
        )
        assert len(store.list_reminders()) == 3
        print(f"[time-word] {payload['error']['message']}")


def test_ambiguous_date_phrase_is_refused_and_touches_nothing(tmp_path):
    with MemoryStore(str(tmp_path / "ambigdate.db")) as store:
        _seed_brief_rows(store)
        Dream(store, EchoBackend())
        payload = _execute_cancel(_T_LOAN, _MEHR)
        assert payload["status"] == "error"
        assert "ambiguous" in payload["error"]["message"].lower()
        assert len(store.list_reminders()) == 3, (
            "an unparseable date filter must never fall back to text-only "
            "cancellation"
        )
        print(f"[ambiguous-date] {payload['error']['message']}")


# ---------------------------------------------------------------------------
# 12. A repeating reminder's confirmation names its repeat rule.
# ---------------------------------------------------------------------------


def test_repeating_reminder_cancellation_names_repeat_rule(tmp_path):
    from dream.reminders import parse_date_to_timestamp

    with MemoryStore(str(tmp_path / "repeat.db")) as store:
        store.add_reminder(
            _T_BILL, parse_date_to_timestamp("1405-05-19"), repeat_months=1
        )
        Dream(store, EchoBackend())
        payload = _execute_cancel(_T_BILL)
        assert payload["status"] == "ok"
        message = payload["result"]["message"]
        assert _W_REPEAT in message and _W_MONTH in message, (
            f"cancelling a repeating reminder must say what rule died with "
            f"the row: {message!r}"
        )
        assert payload["result"]["repeat_months"] == 1
        assert not store.list_reminders()
        print(f"[repeat] {message}")


# ---------------------------------------------------------------------------
# 13. An empty text is refused and touches nothing.
# ---------------------------------------------------------------------------


def test_empty_text_is_refused(tmp_path):
    with MemoryStore(str(tmp_path / "empty.db")) as store:
        _seed_brief_rows(store)
        Dream(store, EchoBackend())
        payload = _execute_cancel("   ")
        assert payload["status"] == "error"
        assert "empty" in payload["error"]["message"].lower()
        assert len(store.list_reminders()) == 3
        print(f"[empty-text] {payload['error']['message']}")


# ---------------------------------------------------------------------------
# 14. Owner-facing Persian wording, spelled right, against typed oracles.
# ---------------------------------------------------------------------------


def test_owner_facing_persian_wording_matches_typed_oracles(tmp_path):
    """Every refusal and confirmation equals a plainly typed, correctly
    spelled oracle. The oracle side is plain Persian on purpose: it is
    generated independently of the escape-transcription process, so a typo
    inside an escape (measured during this milestone: تارئخ for تاریخ, and
    مبل for مثل) cannot coincide in both. Plain Persian literals are allowed
    in tests; the escaping enforcement scans dream/*.py only.
    """
    import dream.agent as agent_module
    from dream.reminders import parse_date_to_timestamp

    with MemoryStore(str(tmp_path / "oracle.db")) as store:
        loan = store.add_reminder(_T_LOAN, parse_date_to_timestamp("1405-05-19"))
        bill = store.add_reminder(
            _T_BILL, parse_date_to_timestamp("1405-05-19"), repeat_months=1
        )
        oracles = {
            "not found": (
                agent_module._cancel_not_found_message("قسط وام"),
                "یادآوری فعالی با متن «قسط وام» پیدا نشد؛ چیزی لغو نشد.",
            ),
            "ambiguous": (
                agent_module._cancel_ambiguous_message("قسط وام", [loan]),
                "چند یادآوری با متن «قسط وام» پیدا شد؛ کدام را لغو کنم؟ "
                "قسط وام (1405-05-19)",
            ),
            "date no match": (
                agent_module._cancel_no_date_match_message("قسط وام", "1405-05-25", [loan]),
                "یادآوری فعالی با متن «قسط وام» برای تاریخ 1405-05-25 پیدا نشد؛ "
                "چیزی لغو نشد. موارد موجود: قسط وام (1405-05-19)",
            ),
            "confirmation": (
                agent_module._cancelled_message(loan),
                "یادآوری «قسط وام» برای 1405-05-19 لغو شد.",
            ),
            "confirmation repeating": (
                agent_module._cancelled_message(bill),
                "یادآوری «قبض برق» برای 1405-05-19 (تکرار: هر ماه) لغو شد.",
            ),
            "cancel time hint": (
                agent_module._CANCEL_TIME_HINT,
                "در date ساعت پشتیبانی نمی‌شود؛ فقط تاریخ را مثل «فردا» یا "
                "«1405-05-19» بفرست.",
            ),
            # The create-side hint moved to a shared constant this milestone;
            # a spelling typo here survives every M15 substring pin (measured
            # while breaking: تارئخ for تاریخ kept the M15 suite green). The
            # oracle keeps the shipped M15 spelling byte for byte (نمیشود
            # without the joiner), because the create message must not change.
            "create time hint (moved constant)": (
                agent_module._CREATE_TIME_HINT,
                "عبارت زمان «ساعت» در تاریخ پشتیبانی نمیشود؛ تاریخ را مثل "
                "«فردا» بفرست و ساعت را در متن یادآوری بنویس.",
            ),
        }
        for name, (produced, oracle) in sorted(oracles.items()):
            assert produced == oracle, (
                f"owner-facing wording for {name!r} must be correctly spelled "
                f"Persian:\nproduced: {produced!r}\noracle:   {oracle!r}"
            )
        print(f"[wording-oracle] {len(oracles)} sentences spelled correctly")


# ---------------------------------------------------------------------------
# 15. The conversation removal and the slash removal leave the same database.
# ---------------------------------------------------------------------------


def test_conversation_and_slash_removal_agree(tmp_path):
    from dream.reminders import parse_date_to_timestamp

    with MemoryStore(str(tmp_path / "conv.db")) as conversation_store:
        rows = _seed_brief_rows(conversation_store)
        Dream(conversation_store, EchoBackend())
        payload = _execute_cancel(_T_INS)
        assert payload["status"] == "ok"
        conversation_active = _listing(conversation_store)
        conversation_all = _listing(conversation_store, include_inactive=True)
    with MemoryStore(str(tmp_path / "slash.db")) as slash_store:
        for text, jalali in (_LOAN_19, _INS_20, _LOAN_21):
            slash_store.add_reminder(text, parse_date_to_timestamp(jalali))
        removed = slash_store.delete_reminder(rows["1405-05-20"].id)
        assert removed, "the slash path's store call succeeds on the twin row"
        slash_active = _listing(slash_store)
        slash_all = _listing(slash_store, include_inactive=True)
    assert conversation_active == slash_active, (
        f"active listings must agree: conversation={conversation_active!r} "
        f"slash={slash_active!r}"
    )
    assert conversation_all == slash_all, (
        f"full listings must agree, no residue: conversation="
        f"{conversation_all!r} slash={slash_all!r}"
    )
    print(
        f"[parity] conversation active={conversation_active}\n"
        f"[parity] slash        active={slash_active}\n"
        f"[parity] both full listings identical, no residue"
    )
