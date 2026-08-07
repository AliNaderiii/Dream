"""Pin the reminder command layer: parser, listing format, and delete command.

The scheduling engine, calendar module, and anchor logic are tested separately
in test_reminders.py. These tests cover the command-line interface: parsing
repeat specs anywhere in the argument, formatting the listing with Persian
brackets, and deleting reminders by id.
"""

import pytest

from cli import _parse_remind_args, dispatch_command
from dream.agent import Dream, EchoBackend
from dream.memory import MemoryStore


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "cmd.db"))
    yield s
    s.close()


def _feeding_input(lines):
    it = iter(lines)

    def read(_prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None

    return read


# --------------------------------------------------------------------------
# Parser: repeat anywhere
# --------------------------------------------------------------------------


def test_repeat_before_and_after_text_give_identical_results():
    """Flag form: --months N before or after text."""
    # before: date, flag, text
    r1 = _parse_remind_args(
        "1405-06-01 --months 1 \u0642\u0633\u0637 \u0648\u0627\u0645"
    )
    # after: date, text, flag
    r2 = _parse_remind_args(
        "1405-06-01 \u0642\u0633\u0637 \u0648\u0627\u0645 --months 1"
    )
    assert r1[1] == r2[1]  # repeat_days
    assert r1[2] == r2[2]  # repeat_months
    assert r1[3] == r2[3]  # text
    assert r1[4] is None and r2[4] is None  # no error


def test_english_repeat_before_and_after_text_give_identical_results():
    """English form: every N months before or after text."""
    r1 = _parse_remind_args("1405-06-01 every 1 months loan payment")
    r2 = _parse_remind_args("1405-06-01 loan payment every 1 months")
    assert r1[1] == r2[1]
    assert r1[2] == r2[2]
    assert r1[3] == r2[3]
    assert r1[4] is None and r2[4] is None


def test_persian_repeat_before_and_after_text_give_identical_results():
    """Persian form: هر ماه before or after text."""
    # before: date, Persian, text
    r1 = _parse_remind_args(
        "1405-06-01 \u0647\u0631 \u0645\u0627\u0647 "
        "\u0642\u0633\u0637 \u0648\u0627\u0645"
    )
    # after: date, text, Persian
    r2 = _parse_remind_args(
        "1405-06-01 \u0642\u0633\u0637 \u0648\u0627\u0645 "
        "\u0647\u0631 \u0645\u0627\u0647"
    )
    assert r1[1] == r2[1]
    assert r1[2] == r2[2]
    assert r1[3] == r2[3]
    assert r1[4] is None and r2[4] is None


def test_persian_phrases_yield_expected_intervals():
    """Each Persian phrase yields the expected day or month count."""
    # har rooz (every day) = 1 day
    r = _parse_remind_args(
        "1405-06-01 \u0647\u0631 \u0631\u0648\u0632 text"
    )
    assert r[1] == 1 and r[2] is None

    # roozane (daily) = 1 day
    r = _parse_remind_args(
        "1405-06-01 \u0631\u0648\u0632\u0627\u0646\u0647 text"
    )
    assert r[1] == 1 and r[2] is None

    # har 3 rooz (every 3 days) = 3 days
    r = _parse_remind_args(
        "1405-06-01 \u0647\u0631 3 \u0631\u0648\u0632 text"
    )
    assert r[1] == 3 and r[2] is None

    # har hafte (every week) = 7 days
    r = _parse_remind_args(
        "1405-06-01 \u0647\u0631 \u0647\u0641\u062a\u0647 text"
    )
    assert r[1] == 7 and r[2] is None

    # haftegi (weekly) = 7 days
    r = _parse_remind_args(
        "1405-06-01 \u0647\u0641\u062a\u06af\u06cc text"
    )
    assert r[1] == 7 and r[2] is None

    # har mah (every month) = 1 month
    r = _parse_remind_args(
        "1405-06-01 \u0647\u0631 \u0645\u0627\u0647 text"
    )
    assert r[1] is None and r[2] == 1

    # harmah (every month, solid) = 1 month
    r = _parse_remind_args(
        "1405-06-01 \u0647\u0631\u0645\u0627\u0647 text"
    )
    assert r[1] is None and r[2] == 1

    # mahane (monthly) = 1 month
    r = _parse_remind_args(
        "1405-06-01 \u0645\u0627\u0647\u0627\u0646\u0647 text"
    )
    assert r[1] is None and r[2] == 1

    # mahiane (monthly variant) = 1 month
    r = _parse_remind_args(
        "1405-06-01 \u0645\u0627\u0647\u06cc\u0627\u0646\u0647 text"
    )
    assert r[1] is None and r[2] == 1

    # har 2 mah (every 2 months) = 2 months
    r = _parse_remind_args(
        "1405-06-01 \u0647\u0631 2 \u0645\u0627\u0647 text"
    )
    assert r[1] is None and r[2] == 2

    # har sal (every year) = 12 months
    r = _parse_remind_args(
        "1405-06-01 \u0647\u0631 \u0633\u0627\u0644 text"
    )
    assert r[1] is None and r[2] == 12

    # salane (yearly) = 12 months
    r = _parse_remind_args(
        "1405-06-01 \u0633\u0627\u0644\u0627\u0646\u0647 text"
    )
    assert r[1] is None and r[2] == 12


def test_persian_numerals_give_same_result_as_latin():
    """Persian numerals are normalized to Latin before parsing."""
    # Latin: 30
    r1 = _parse_remind_args(
        "1405-06-01 \u0642\u0631\u0635 \u0647\u0631 30 \u0631\u0648\u0632"
    )
    # Persian: ۳۰ (\u06f3\u06f0)
    r2 = _parse_remind_args(
        "1405-06-01 \u0642\u0631\u0635 \u0647\u0631 "
        "\u06f3\u06f0 \u0631\u0648\u0632"
    )
    assert r1[1] == r2[1] == 30
    assert r1[3] == r2[3]


def test_repeat_words_removed_from_stored_text():
    """Repeat spec is removed from the stored text in every accepted form."""
    # Flag form
    r = _parse_remind_args(
        "1405-06-01 \u0642\u0633\u0637 \u0648\u0627\u0645 --months 1"
    )
    assert r[3] == "\u0642\u0633\u0637 \u0648\u0627\u0645"

    # English form
    r = _parse_remind_args("1405-06-01 loan payment every 1 months")
    assert r[3] == "loan payment"

    # Persian form
    r = _parse_remind_args(
        "1405-06-01 \u0642\u0633\u0637 \u0648\u0627\u0645 "
        "\u0647\u0631 \u0645\u0627\u0647"
    )
    assert r[3] == "\u0642\u0633\u0637 \u0648\u0627\u0645"


def test_unrecognized_option_rejected_with_message():
    """Misspelled flag is rejected with a message naming it."""
    r = _parse_remind_args(
        "1405-06-01 \u0642\u0633\u0637 \u0648\u0627\u0645 --monthz 1"
    )
    assert r[4] is not None  # error
    assert "--monthz" in r[4]
    assert r[0] is None  # no due_at


def test_empty_text_rejected():
    """Empty text after repeat removal is rejected."""
    r = _parse_remind_args("1405-06-01 --months 1")
    assert r[4] is not None
    assert "text" in r[4].lower() or "missing" in r[4].lower()


def test_zero_repeat_rejected():
    """Zero repeat is rejected."""
    r = _parse_remind_args("1405-06-01 text every 0 days")
    assert r[4] is not None
    assert "non-zero" in r[4].lower()


def test_both_day_and_month_repeat_rejected():
    """Both day and month repeat is rejected."""
    r = _parse_remind_args("1405-06-01 text --days 1 --months 1")
    assert r[4] is not None
    # Parser accepts one flag, rejects the second as unrecognized
    assert "unrecognized" in r[4].lower() or "either" in r[4].lower()


def test_no_repeat_parses_with_text_intact():
    """Reminder with no repeat parses correctly."""
    r = _parse_remind_args(
        "1405-06-01 \u0628\u06cc\u0645\u0647 \u0645\u0627\u0634\u06cc\u0646"
    )
    assert r[1] is None and r[2] is None
    assert r[3] == "\u0628\u06cc\u0645\u0647 \u0645\u0627\u0634\u06cc\u0646"
    assert r[4] is None


# --------------------------------------------------------------------------
# Listing: Persian brackets
# --------------------------------------------------------------------------


def test_listing_shows_repeat_in_persian_brackets(store):
    """Repeating reminder prints date and repeat as visibly separate fields."""
    from dream.reminders import parse_date_to_timestamp

    ts = parse_date_to_timestamp("1405-06-01")
    store.add_reminder("test text", ts, repeat_months=1)

    dream = Dream(store, EchoBackend())
    out: list[str] = []
    dispatch_command("/reminders", dream, out.append)

    assert out
    # Should have brackets around the repeat
    assert "(" in out[0] and ")" in out[0]
    # Should have Persian words for repeat
    assert "\u0647\u0631" in out[0]  # har (every)
    assert "\u0645\u0627\u0647" in out[0]  # mah (month)


def test_listing_singular_and_plural_read_naturally(store):
    """One month and three months both read naturally in Persian."""
    from dream.reminders import parse_date_to_timestamp

    ts = parse_date_to_timestamp("1405-06-01")
    store.add_reminder("one", ts, repeat_months=1)
    store.add_reminder("three", ts, repeat_months=3)

    dream = Dream(store, EchoBackend())
    out: list[str] = []
    dispatch_command("/reminders", dream, out.append)

    # Both should have the same form (Persian doesn't pluralize after numbers)
    one_line = [line for line in out if "one" in line][0]
    three_line = [line for line in out if "three" in line][0]
    assert "\u0647\u0631 1 \u0645\u0627\u0647" in one_line
    assert "\u0647\u0631 3 \u0645\u0627\u0647" in three_line


def test_one_off_reminder_prints_no_bracket(store):
    """One-off reminder prints no bracket."""
    from dream.reminders import parse_date_to_timestamp

    ts = parse_date_to_timestamp("1405-06-01")
    store.add_reminder("once", ts)

    dream = Dream(store, EchoBackend())
    out: list[str] = []
    dispatch_command("/reminders", dream, out.append)

    assert out
    assert "(" not in out[0] and ")" not in out[0]


# --------------------------------------------------------------------------
# Delete: /unremind command
# --------------------------------------------------------------------------


def test_delete_existing_reminder_removes_it(store):
    """Deleting an existing reminder removes it."""
    from dream.reminders import parse_date_to_timestamp

    ts = parse_date_to_timestamp("1405-06-01")
    rem = store.add_reminder("to delete", ts)

    dream = Dream(store, EchoBackend())
    out: list[str] = []
    dispatch_command(f"/unremind {rem.id}", dream, out.append)

    assert out
    assert "deleted" in out[0].lower() or "permanently" in out[0].lower()
    assert len(store.list_reminders()) == 0


def test_delete_nonexistent_id_reports_clearly(store):
    """Deleting a non-existent id reports clearly."""
    dream = Dream(store, EchoBackend())
    out: list[str] = []
    dispatch_command("/unremind 99999", dream, out.append)

    assert out
    assert "no reminder" in out[0].lower() or "not found" in out[0].lower()
    assert len(store.list_reminders()) == 0


def test_delete_non_numeric_id_gives_usage():
    """Non-numeric id gives usage message."""
    store = MemoryStore(":memory:")
    dream = Dream(store, EchoBackend())
    out: list[str] = []
    dispatch_command("/unremind abc", dream, out.append)

    assert out
    assert "usage" in out[0].lower() or "number" in out[0].lower()


def test_delete_missing_id_gives_usage():
    """Missing id gives usage message."""
    store = MemoryStore(":memory:")
    dream = Dream(store, EchoBackend())
    out: list[str] = []
    dispatch_command("/unremind", dream, out.append)

    assert out
    assert "usage" in out[0].lower() or "number" in out[0].lower()


def test_delete_another_users_reminder_fails(tmp_path):
    """Reminder belonging to another user cannot be deleted."""
    db = str(tmp_path / "multi.db")
    with MemoryStore(db, user="alice") as a:
        from dream.reminders import parse_date_to_timestamp

        ts = parse_date_to_timestamp("1405-06-01")
        rem = a.add_reminder("alice only", ts)
        rid = rem.id

    with MemoryStore(db, user="bob") as b:
        dream = Dream(b, EchoBackend())
        out: list[str] = []
        dispatch_command(f"/unremind {rid}", dream, out.append)

        assert out
        assert "no reminder" in out[0].lower() or "not found" in out[0].lower()

    # Alice's reminder still exists
    with MemoryStore(db, user="alice") as a2:
        assert len(a2.list_reminders()) == 1


def test_unremind_in_known_commands_and_help():
    """The command appears in the help line and known-command list."""
    from cli import KNOWN_COMMANDS

    assert "/unremind" in KNOWN_COMMANDS

    store = MemoryStore(":memory:")
    dream = Dream(store, EchoBackend())
    out: list[str] = []
    dispatch_command("/help", dream, out.append)

    assert out
    assert "/unremind" in out[0]
