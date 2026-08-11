"""M26 — long rows reachable, duplicate cleanup wired to the window.

Two defects measured on merged trunk:

1. A memory row longer than the list is wide cannot be read: the Listbox
   does not wrap and has no sideways bar. The remedy keeps the row on one
   line (the list draws one line per item): a horizontal scrollbar
   (xscrollcommand / xview) on every list, plus a wrap-capable detail line
   that shows the full text of the selected memory — kinder for reading.

2. The store's cleanup_duplicates(dry_run=True) exists and is tested, but
   nothing in the window mentions it. The control near the memories list
   runs the dry pass first, shows the report (how many pairs, which rows),
   and removes nothing until the owner accepts (DATA ENGINEER veto).

Direction (M23/M25): every display line keeps the RLM marks; the store and
the model never see a mark.
"""

from __future__ import annotations

import inspect
import json
import time

import desktop
from dream.agent import Dream, EchoBackend
from dream.memory import MemoryStore, normalize_fa
from dream.reminders import format_jalali, parse_date_to_timestamp

RLM = "\u200f"

# The owner's measured row is ninety characters. This is a natural Persian
# sentence of exactly ninety characters: "The user renews his car insurance
# every year in Ordibehesht and must pay the installment amount before the
# end of the month."
LONG_ROW = (
    "کاربر هر سال در اردیبهشت بیمه ماشین خود را تمدید میکند "
    "و باید مبلغ قسط را قبل از پایان ماه"
)
assert len(LONG_ROW) == 90, f"LONG_ROW must be exactly 90 chars, got {len(LONG_ROW)}"

# Three rows saying nearly the same thing about renewing car insurance, in
# slightly different words — the owner's measured duplicate family.
INSURANCE_A = "کاربر باید بیمه ماشین خود را تمدید کند"
INSURANCE_B = "کاربر باید بیمه ماشین را تمدید کند"
INSURANCE_C = "باید بیمه ماشین خود را تمدید کند"
UNIQUE_1 = "کاربر در تهران زندگی میکند"
UNIQUE_2 = "کاربر پایتون بلد است"

PERSIAN_SHORT = "سلام دنیا"
LATIN_SHORT = "hello world"


def _ts(jy, jm, jd):
    return parse_date_to_timestamp(f"{jy:04d}-{jm:02d}-{jd:02d}")


def _seed(store, text, kind="semantic", importance=0.5):
    """Insert a row directly (bypassing remember's write-time dedupe)."""
    now = len(store.all(include_archived=True)) + 1
    store.conn.execute(
        """INSERT INTO memories
        (user_id, kind, content, norm, tags, importance, created_at, last_used_at,
         use_count, source, archived, pinned) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '', 0, 0)""",
        (
            store.user_id,
            kind,
            text,
            normalize_fa(text),
            json.dumps([]),
            importance,
            now,
            now,
        ),
    )
    store.conn.commit()


def _seeded_store(path=":memory:"):
    store = MemoryStore(path)
    for text in (INSURANCE_A, INSURANCE_B, INSURANCE_C, UNIQUE_1, UNIQUE_2):
        _seed(store, text)
    return store


class SpyStore(MemoryStore):
    """Records every cleanup_duplicates dry_run flag; the store itself is untouched."""

    def __init__(self, path=":memory:"):
        super().__init__(path)
        self.cleanup_calls: list[bool] = []

    def cleanup_duplicates(self, dry_run: bool = True) -> dict:
        self.cleanup_calls.append(dry_run)
        return super().cleanup_duplicates(dry_run=dry_run)


def _make_dream(store):
    return Dream(store, EchoBackend())


# ---------------------------------------------------------------------------
# Defect one — a row longer than the list is fully reachable
# ---------------------------------------------------------------------------

def test_long_memory_row_is_ninety_characters(tmp_path):
    """The owner's measured row length is reproduced: 90 characters."""
    store = MemoryStore(str(tmp_path / "db.db"))
    _seed(store, LONG_ROW)
    assert len(store.all()[0].content) == 90
    store.close()


def test_long_row_every_character_reachable_in_list_row(tmp_path):
    """The whole 90-character row is in the display line the list inserts.

    The Listbox draws one line per item and does not wrap, so the row stays
    one line — but the full line (every character, in order) is what the
    list receives, and the sideways bar makes the tail reachable.
    """
    store = MemoryStore(str(tmp_path / "db.db"))
    _seed(store, LONG_ROW)
    mem = store.all()[0]
    line = desktop.format_memory_panel_line(mem)
    # every character of the row is present, in order
    assert mem.content in line, "the full 90-character row must be in the display line"
    assert line[0] == RLM and line[-1] == RLM
    # the list inserts this full line, not a truncated copy
    src = inspect.getsource(desktop.DreamDesktop._refresh_memories)
    assert "format_memory_panel_line" in src
    store.close()


def test_sideways_bar_attached_to_each_list():
    """Every list has a horizontal scrollbar driving the list's xview.

    xscrollcommand is the option that connects the sideways bar to the
    list; xview is the list method the bar drives. The one-line row then
    scrolls sideways instead of being cut.
    """
    make_src = inspect.getsource(desktop.DreamDesktop._build_widgets)
    assert "Listbox" in make_src
    assert make_src.count("make_panel(") >= 3, "three lists share the panel builder"
    # the actual code, not a comment: the sideways bar is created, wired via
    # xscrollcommand, and driven by the list's xview
    assert "xscrollcommand=sb_x.set" in make_src, (
        "xscrollcommand must connect the sideways bar to the list"
    )
    assert "orient=tk.HORIZONTAL, command=lb.xview" in make_src, (
        "the sideways bar must drive the list's xview"
    )


def test_detail_line_shows_full_text_of_selected_memory(tmp_path):
    """The detail line shows the whole row in a wrap-capable widget.

    The sideways bar is the honest widget fix; the detail line is kinder
    for reading: the selected row's full text appears where it can wrap.
    """
    store = MemoryStore(str(tmp_path / "db.db"))
    _seed(store, LONG_ROW)
    mem = store.all()[0]
    detail = desktop.format_memory_detail_text(mem)
    assert mem.content in detail, "detail line must contain the full content"
    assert detail[0] == RLM and detail[-1] == RLM, "detail line keeps the marks"
    src = inspect.getsource(desktop.DreamDesktop._build_widgets)
    assert "wrap=tk.WORD" in src, "the detail widget must wrap"
    assert "<<ListboxSelect>>" in src, "the detail line follows the selection"
    assert "memory_detail" in src
    store.close()


def test_short_row_unchanged_by_the_additions(tmp_path):
    """A short Latin row is byte-identical; a short Persian row keeps marks."""
    store = MemoryStore(str(tmp_path / "db.db"))
    _seed(store, LATIN_SHORT)
    mem = store.all()[0]
    line = desktop.format_memory_panel_line(mem)
    assert line == f"semantic: {LATIN_SHORT}", "short Latin row must be byte-identical"
    assert RLM not in line
    assert desktop.format_memory_detail_text(mem) == line
    store.close()


# ---------------------------------------------------------------------------
# Defect two — the cleanup control: dry first, report, accept, redraw
# ---------------------------------------------------------------------------

def test_cleanup_control_runs_dry_pass_first(tmp_path):
    """The first pass is always the dry one; the wet pass only after accept."""
    store = SpyStore(str(tmp_path / "db.db"))
    for text in (INSURANCE_A, INSURANCE_B, INSURANCE_C):
        _seed(store, text)
    result = desktop.panel_cleanup_memories(store, confirm_fn=lambda report: True)
    assert store.cleanup_calls == [True, False], (
        f"first pass must be dry, second wet; got {store.cleanup_calls}"
    )
    assert result["merged"] == 2
    store.close()


def test_cleanup_control_never_skips_the_dry_pass():
    """The window's control and the worker's dry op are pinned to dry first."""
    on_dedupe = inspect.getsource(desktop.DreamDesktop._on_dedupe)
    assert "request_cleanup_dry" in on_dedupe
    assert "request_cleanup_apply" not in on_dedupe, "control must not start wet"
    handle = inspect.getsource(desktop.DesktopController._handle_one)
    assert 'op == "cleanup_dry"' in handle
    assert "dry_run=True" in handle, "the dry op must call cleanup_duplicates(dry_run=True)"
    assert 'op == "cleanup_apply"' in handle
    assert "dry_run=False" in handle, "the apply op must call cleanup_duplicates(dry_run=False)"


def test_dry_pass_removes_nothing_counted(tmp_path):
    """Counting rows before and after the dry pass: identical."""
    store = _seeded_store(str(tmp_path / "db.db"))
    before = [
        (m.id, m.content, m.importance, m.tags)
        for m in store.all()
    ]
    assert len(before) == 5
    report = desktop.panel_cleanup_memories(store, confirm_fn=lambda r: False)
    assert report["merged"] == 2, "the report must name the pairs even when refused"
    after = [
        (m.id, m.content, m.importance, m.tags)
        for m in store.all()
    ]
    assert len(after) == 5
    assert after == before, "dry pass must remove nothing: rows, contents, values unchanged"
    store.close()


def test_cleanup_refused_at_confirmation_removes_nothing(tmp_path):
    """A refused confirmation means the wet pass never runs."""
    store = SpyStore(str(tmp_path / "db.db"))
    for text in (INSURANCE_A, INSURANCE_B, INSURANCE_C):
        _seed(store, text)
    result = desktop.panel_cleanup_memories(store, confirm_fn=lambda report: False)
    assert store.cleanup_calls == [True], (  # noqa: E501
        f"wet pass must not run when refused: {store.cleanup_calls}"
    )
    assert result["merged"] == 2
    assert len(store.all()) == 3
    store.close()


def test_accepted_cleanup_removes_only_what_report_named(tmp_path):
    """The wet pass removes exactly the rows the dry report named."""
    store = _seeded_store(str(tmp_path / "db.db"))
    dry = desktop.panel_cleanup_memories(store, confirm_fn=lambda r: False)
    named_removed = {new_id for new_id, _old_id in dry["pairs"]}
    assert named_removed == {2, 3}
    assert dry["remaining"] == 3
    wet = desktop.panel_cleanup_memories(store, confirm_fn=lambda r: True)
    assert wet["pairs"] == dry["pairs"], "the applied pass must match the shown report"
    remaining = store.all()
    assert len(remaining) == dry["remaining"]
    remaining_ids = {m.id for m in remaining}
    assert named_removed.isdisjoint(remaining_ids), "named rows must be gone"
    # the rows the report did not name are untouched
    uniques = {m.id: m.content for m in remaining if m.id in (4, 5)}
    assert uniques == {4: UNIQUE_1, 5: UNIQUE_2}
    kept = next(m for m in remaining if m.id == 1)
    assert kept.content == INSURANCE_A
    store.close()


def test_list_redraws_from_store_after_cleanup(tmp_path):
    """After the accepted cleanup, the memories list redraws from the store."""
    store = _seeded_store(str(tmp_path / "db.db"))
    dream = _make_dream(store)
    ctrl = desktop.DesktopController(dream)
    ctrl._handle_one({"op": "cleanup_dry"})
    report_result = None
    while True:
        result = ctrl.poll()
        if result is None:
            break
        if result.get("kind") == "cleanup_report":
            report_result = result
    assert report_result is not None
    assert report_result["report"]["merged"] == 2
    assert len(store.all()) == 5, "dry pass changed nothing"
    ctrl._handle_one({"op": "cleanup_apply"})
    list_result = None
    while True:
        result = ctrl.poll()
        if result is None:
            break
        if result.get("kind") == "memories_list":
            list_result = result
    assert list_result is not None, "the apply op must post a fresh memories list"
    fresh = store.all()
    assert len(list_result["rows"]) == len(fresh) == 3
    assert [r.id for r in list_result["rows"]] == [r.id for r in fresh], (
        "the redrawn list must be the store's own rows"
    )
    ctrl.shutdown()
    store.close()


def test_cleanup_report_shows_pairs_and_which_rows(tmp_path):
    """The report says how many pairs and names both rows of each pair."""
    store = _seeded_store(str(tmp_path / "db.db"))
    dry = store.cleanup_duplicates(dry_run=True)
    lines = desktop.format_cleanup_report_lines(dry)
    joined = "\n".join(lines)
    assert "2" in joined, "how many pairs must be visible"
    assert INSURANCE_A in joined, "the kept row must be named"
    assert INSURANCE_B in joined, "the removed row must be named"
    assert INSURANCE_C in joined
    for line in lines:
        assert line[0] == RLM and line[-1] == RLM, f"Persian report line keeps marks: {line!r}"
    store.close()


def test_cleanup_report_zero_pairs(tmp_path):
    """No duplicates: the report says so, and nothing is offered for removal."""
    store = MemoryStore(str(tmp_path / "db.db"))
    _seed(store, UNIQUE_1)
    _seed(store, UNIQUE_2)
    dry = store.cleanup_duplicates(dry_run=True)
    assert dry["merged"] == 0
    lines = desktop.format_cleanup_report_lines(dry)
    assert "یافت نشد" in "\n".join(lines), "no-duplicates line must be visible"
    store.close()


# ---------------------------------------------------------------------------
# Direction — marks kept everywhere, store and model never see them
# ---------------------------------------------------------------------------

def test_persian_row_still_carries_marks_after_change(tmp_path):
    """One Persian row proven by character index: mark at 0 and -1 everywhere."""
    store = MemoryStore(str(tmp_path / "db.db"))
    _seed(store, PERSIAN_SHORT)
    mem = store.all()[0]
    row = desktop.format_memory_panel_line(mem)
    assert row[0] == RLM and row[-1] == RLM
    detail = desktop.format_memory_detail_text(mem)
    assert detail[0] == RLM and detail[-1] == RLM
    assert detail[1:-1] == row[1:-1]
    # logical text between the marks is byte-identical to the stored row
    assert f"{mem.kind}: {mem.content}" in row[1:-1]
    store.close()


def test_store_and_model_never_see_direction_mark_after_cleanup(tmp_path, monkeypatch):
    """After an accepted cleanup, stored rows and model messages carry no mark."""
    monkeypatch.setenv("DREAM_EXTRACTION", "off")
    store = _seeded_store(str(tmp_path / "db.db"))

    class Cap:
        def __init__(self):
            self.inner = EchoBackend()
            self.seen = []

        def chat(self, messages, tools=None):
            self.seen.append([dict(m) for m in messages])
            return self.inner.chat(messages, tools)

    cap = Cap()
    dream = Dream(store, cap)
    ctrl = desktop.DesktopController(dream)
    ctrl._handle_one({"op": "cleanup_apply"})
    kinds = []
    while True:
        result = ctrl.poll()
        if result is None:
            break
        kinds.append(result.get("kind"))
    assert "memories_list" in kinds, "the accepted cleanup must redraw the list"
    assert len(store.all()) == 3, "the accepted cleanup must have merged the pairs"
    for m in store.all():
        assert RLM not in m.content, "stored content must never carry the mark"
    ctrl.submit("hello")
    deadline = time.time() + 3
    result = None
    while time.time() < deadline:
        result = ctrl.poll()
        if result and result.get("kind") == "reply":
            break
        time.sleep(0.05)
    assert result is not None
    for msgs in cap.seen:
        for m in msgs:
            assert RLM not in (m.get("content") or ""), "model messages must never carry the mark"
    ctrl.shutdown()
    store.close()


# ---------------------------------------------------------------------------
# Ordering was checked, not changed
# ---------------------------------------------------------------------------

def test_reminder_ordering_checked_and_correct(tmp_path):
    """Four reminders inserted out of order list ascending by due date."""
    store = MemoryStore(str(tmp_path / "db.db"))
    for jy, jm, jd in [(1405, 7, 18), (1405, 5, 21), (1405, 8, 18), (1405, 6, 9)]:
        store.add_reminder(f"test {jy:04d}-{jm:02d}-{jd:02d}", _ts(jy, jm, jd))
    rows = store.list_reminders()
    dates = [format_jalali(r.due_at) for r in rows]
    assert dates == ["1405-05-21", "1405-06-09", "1405-07-18", "1405-08-18"], (
        f"store must list by due date ascending, got {dates}"
    )
    store.close()
