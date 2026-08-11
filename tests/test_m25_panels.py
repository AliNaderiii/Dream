"""M25 panels, store updates, direction, and platform skips.

Tests are written first and run against unchanged code to paste failures
before the implementation restores them.
"""

from __future__ import annotations

import time

import desktop
from dream.memory import MemoryStore
from dream.reminders import format_jalali, parse_date_to_timestamp

RLM = "\u200f"

# Persian helpers (backslash-u escapes for consistency, but raw also ok in tests)
PERSIAN_TODO = "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc \u062a\u0633\u062a"
PERSIAN_KIND = "semantic"
PERSIAN_CONTENT = "\u0633\u0644\u0627\u0645 \u062f\u0646\u06cc\u0627"
PERSIAN_SKILL = "\u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 \u0645\u0627\u0634\u06cc\u0646"  # noqa: E501


def _ts(jy, jm, jd):
    return parse_date_to_timestamp(f"{jy:04d}-{jm:02d}-{jd:02d}")


# ---------------------------------------------------------------------------
# Store update API existence
# ---------------------------------------------------------------------------

def test_store_has_update_reminder(tmp_path):
    store = MemoryStore(str(tmp_path / "db.db"))
    assert hasattr(store, "update_reminder"), "MemoryStore must expose update_reminder"
    store.close()


def test_store_has_update_memory(tmp_path):
    store = MemoryStore(str(tmp_path / "db.db"))
    assert hasattr(store, "update_memory"), "MemoryStore must expose update_memory"
    store.close()


# ---------------------------------------------------------------------------
# Update keeps identifier (and delivery history for reminders)
# ---------------------------------------------------------------------------

def test_update_reminder_keeps_identifier(tmp_path):
    store = MemoryStore(str(tmp_path / "db.db"))
    rem = store.add_reminder(PERSIAN_TODO, _ts(1405, 5, 20))
    original_id = rem.id
    # edit via new store method — must keep id, not delete+create
    updated = store.update_reminder(rem.id, text=PERSIAN_TODO + " \u0648\u06cc\u0631\u0627\u06cc\u0634")  # noqa: E501
    assert updated is not None
    assert updated.id == original_id, "editing must keep identifier"
    assert updated.text.endswith("\u0648\u06cc\u0631\u0627\u06cc\u0634")
    # only one row, count unchanged
    assert len(store.list_reminders()) == 1
    store.close()


def test_update_reminder_preserves_delivery_history(tmp_path):
    store = MemoryStore(str(tmp_path / "db.db"))
    rem = store.add_reminder(PERSIAN_TODO, time.time() - 100, repeat_days=7)
    # fire once to create delivery row
    fired = store.check_due_reminders()
    assert len(fired) == 1
    before = store.conn.execute("SELECT COUNT(*) FROM reminder_deliveries").fetchone()[0]
    assert before == 1
    updated = store.update_reminder(rem.id, text=PERSIAN_TODO + " \u0648\u06cc\u0631\u0627\u06cc\u0634")  # noqa: E501
    assert updated.id == rem.id
    after = store.conn.execute("SELECT COUNT(*) FROM reminder_deliveries").fetchone()[0]
    assert after == 1, "delivery history must not be lost on edit"
    # due still exists
    assert len(store.list_reminders()) == 1
    store.close()


def test_update_memory_keeps_identifier(tmp_path):
    store = MemoryStore(str(tmp_path / "db.db"))
    mem = store.remember(PERSIAN_CONTENT, kind="semantic")
    original_id = mem.id
    updated = store.update_memory(mem.id, content=PERSIAN_CONTENT + " \u0648\u06cc\u0631\u0627\u06cc\u0634")  # noqa: E501
    assert updated is not None
    assert updated.id == original_id, "editing memory must keep identifier"
    assert updated.content.endswith("\u0648\u06cc\u0631\u0627\u06cc\u0634")
    # archived/old rows not created
    assert len(store.all()) == 1
    store.close()


def test_update_reminder_via_delete_recreate_would_change_id(tmp_path):
    """Guard that edit is not delete+create: id would change and delivery lost."""
    store = MemoryStore(str(tmp_path / "db.db"))
    rem = store.add_reminder(PERSIAN_TODO, time.time() - 100, repeat_days=7)
    store.check_due_reminders()
    did = store.conn.execute("SELECT COUNT(*) FROM reminder_deliveries").fetchone()[0]
    assert did == 1
    # Simulate broken edit: delete and re-add
    old_id = rem.id
    store.delete_reminder(old_id)
    new_rem = store.add_reminder(PERSIAN_TODO + " \u062c\u062f\u06cc\u062f", _ts(1405, 6, 15))
    assert new_rem.id != old_id
    assert store.conn.execute("SELECT COUNT(*) FROM reminder_deliveries").fetchone()[0] == 0, "delete lost deliveries"  # noqa: E501
    store.close()


# ---------------------------------------------------------------------------
# Panel formatting — direction
# ---------------------------------------------------------------------------

def test_reminder_panel_row_carries_rlm(tmp_path):
    store = MemoryStore(str(tmp_path / "db.db"))
    rem = store.add_reminder(PERSIAN_TODO, _ts(1405, 5, 20))
    line = desktop.format_reminder_panel_line(rem)
    assert line[0] == RLM, f"first char must be RLM, got {line[0]!r}"
    assert line[-1] == RLM, f"last char must be RLM, got {line[-1]!r}"
    # store never sees mark
    assert RLM not in store.list_reminders()[0].text
    # strip marks reconstructs logical
    assert line[1:-1].startswith(PERSIAN_TODO)
    assert format_jalali(rem.due_at) in line
    store.close()


def test_memory_panel_row_carries_rlm(tmp_path):
    store = MemoryStore(str(tmp_path / "db.db"))
    mem = store.remember(PERSIAN_CONTENT, kind="semantic")
    line = desktop.format_memory_panel_line(mem)
    assert line[0] == RLM
    assert line[-1] == RLM
    assert RLM not in mem.content
    # store row has no mark
    assert RLM not in store.all()[0].content
    store.close()


def test_skill_panel_row_carries_rlm(tmp_path, monkeypatch):
    from dream import skills as skills_module
    from dream import tools
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", tmp_path)
    skills_module.save_skill(PERSIAN_SKILL, "when user asks", ["step one"])
    skills, _ = skills_module.load_skills()
    assert skills
    line = desktop.format_skill_panel_line(skills[0])
    assert line[0] == RLM
    assert line[-1] == RLM
    assert RLM not in skills[0].name
    # file must not contain mark
    import pathlib
    text = pathlib.Path(tmp_path / "skills" / (PERSIAN_SKILL + ".txt")).read_text(encoding="utf-8")
    assert RLM not in text


def test_panel_store_and_model_never_see_rlm(tmp_path, monkeypatch):
    monkeypatch.setenv("DREAM_EXTRACTION", "off")
    store = MemoryStore(str(tmp_path / "db.db"))
    # use capturing backend as in M23
    class Cap:
        def __init__(self):
            from dream.agent import EchoBackend
            self.inner = EchoBackend()
            self.seen = []
        def chat(self, messages, tools=None):
            self.seen.append([dict(m) for m in messages])
            return self.inner.chat(messages, tools)
    from dream.agent import Dream
    cap = Cap()
    dream = Dream(store, cap)
    ctrl = desktop.DesktopController(dream)
    # panel formatting should not leak to model/store
    rem = store.add_reminder(PERSIAN_TODO, _ts(1405, 5, 20))
    line = desktop.format_reminder_panel_line(rem)
    assert RLM in line
    assert RLM not in rem.text
    # model messages also free
    # do a turn via controller
    ctrl.submit(PERSIAN_TODO)
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
            assert RLM not in (m.get("content") or "")
    for (c,) in store.conn.execute("SELECT content FROM memories"):
        assert RLM not in c
    for (t,) in store.conn.execute("SELECT text FROM reminders"):
        assert RLM not in t
    ctrl.shutdown()
    store.close()


def test_each_list_renders_rows_store_actually_holds(tmp_path, monkeypatch):
    from dream import skills as skills_module
    from dream import tools
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", tmp_path)
    store = MemoryStore(str(tmp_path / "db.db"))
    store.add_reminder(PERSIAN_TODO + " 1", _ts(1405, 5, 20))
    store.add_reminder(PERSIAN_TODO + " 2", _ts(1405, 5, 21))
    store.remember(PERSIAN_CONTENT + " 1", kind="semantic")
    store.remember(PERSIAN_CONTENT + " 2", kind="semantic")
    skills_module.save_skill(PERSIAN_SKILL + " 1", "desc", ["s1"])
    skills_module.save_skill(PERSIAN_SKILL + " 2", "desc", ["s1"])
    # panel helpers must reflect store
    rem_rows = desktop.get_reminder_panel_rows(store)
    mem_rows = desktop.get_memory_panel_rows(store)
    skill_rows = desktop.get_skill_panel_rows()
    assert len(rem_rows) == 2
    assert len(mem_rows) == 2
    assert len(skill_rows) == 2
    # each row contains its Persian text
    assert any(PERSIAN_TODO in r for r in rem_rows)
    assert any(PERSIAN_CONTENT in r for r in mem_rows)
    assert any(PERSIAN_SKILL in r for r in skill_rows)
    store.close()


# ---------------------------------------------------------------------------
# Delete / create / edit via panel (store + confirmation)
# ---------------------------------------------------------------------------

def test_delete_selected_reminder_removes_exactly_one(tmp_path, monkeypatch):
    store = MemoryStore(str(tmp_path / "db.db"))
    r1 = store.add_reminder(PERSIAN_TODO + " 1", _ts(1405, 5, 20))
    r2 = store.add_reminder(PERSIAN_TODO + " 2", _ts(1405, 5, 21))
    assert len(store.list_reminders()) == 2
    # simulate panel delete: selected id = r1.id, confirm True
    monkeypatch.setattr(desktop, "ask_confirm_delete", lambda *a, **k: True)
    # desktop helper that deletes selected
    ok = desktop.panel_delete_reminder(store, r1.id, confirm_fn=lambda *a, **k: True)
    assert ok is True
    remaining = store.list_reminders()
    assert len(remaining) == 1
    assert remaining[0].id == r2.id
    # only one removed
    assert store.get_reminder(r1.id) is None
    store.close()


def test_delete_refused_at_confirmation_removes_nothing(tmp_path, monkeypatch):
    store = MemoryStore(str(tmp_path / "db.db"))
    r1 = store.add_reminder(PERSIAN_TODO, _ts(1405, 5, 20))
    assert len(store.list_reminders()) == 1
    # confirm returns False — should not delete
    ok = desktop.panel_delete_reminder(store, r1.id, confirm_fn=lambda *a, **k: False)
    assert ok is False
    assert len(store.list_reminders()) == 1
    assert store.get_reminder(r1.id) is not None
    store.close()


def test_create_reminder_appears_in_next_redraw(tmp_path):
    store = MemoryStore(str(tmp_path / "db.db"))
    assert len(store.list_reminders()) == 0
    # simulate create form submitting via panel helper
    new = desktop.panel_create_reminder(store, PERSIAN_TODO, _ts(1405, 6, 1))
    assert new is not None
    rows = desktop.get_reminder_panel_rows(store)
    assert len(rows) == 1
    assert PERSIAN_TODO in rows[0]
    assert format_jalali(new.due_at) in rows[0]
    store.close()


def test_create_memory_appears_in_next_redraw(tmp_path):
    store = MemoryStore(str(tmp_path / "db.db"))
    assert len(store.all()) == 0
    new = desktop.panel_create_memory(store, PERSIAN_CONTENT, kind="semantic")
    assert new is not None
    rows = desktop.get_memory_panel_rows(store)
    assert len(rows) == 1
    assert PERSIAN_CONTENT in rows[0]
    store.close()


def test_create_skill_appears_in_next_redraw(tmp_path, monkeypatch):
    from dream import tools
    monkeypatch.setattr(tools, "WORKSPACE_ROOT", tmp_path)
    # ensure empty
    rows_before = desktop.get_skill_panel_rows()
    assert len(rows_before) == 0
    desktop.panel_create_skill(PERSIAN_SKILL, "desc", ["step one"])
    rows_after = desktop.get_skill_panel_rows()
    assert len(rows_after) == 1
    assert PERSIAN_SKILL in rows_after[0]


def test_edit_reminder_keeps_identifier_via_panel(tmp_path):
    store = MemoryStore(str(tmp_path / "db.db"))
    rem = store.add_reminder(PERSIAN_TODO, _ts(1405, 5, 20))
    old_id = rem.id
    updated = desktop.panel_update_reminder(store, rem.id, text=PERSIAN_TODO + " \u0648\u06cc\u0631\u0627\u06cc\u0634", due_at=_ts(1405, 6, 15))  # noqa: E501
    assert updated.id == old_id
    assert updated.text.endswith("\u0648\u06cc\u0631\u0627\u06cc\u0634")
    assert len(store.list_reminders()) == 1
    store.close()


def test_edit_memory_keeps_identifier_via_panel(tmp_path):
    store = MemoryStore(str(tmp_path / "db.db"))
    mem = store.remember(PERSIAN_CONTENT, kind="semantic")
    old_id = mem.id
    updated = desktop.panel_update_memory(store, mem.id, content=PERSIAN_CONTENT + " \u0648\u06cc\u0631\u0627\u06cc\u0634")  # noqa: E501
    assert updated.id == old_id
    store.close()


# ---------------------------------------------------------------------------
# Desktop has sidebar and threading shape
# ---------------------------------------------------------------------------

def test_desktop_has_sidebar_and_panels():
    # file must create sidebar with three lists, using PanedWindow or similar
    src = open("desktop.py", encoding="utf-8").read()
    assert "PanedWindow" in src or "sidebar" in src.lower(), "sidebar must exist"
    # three listboxes
    assert src.count("Listbox") >= 3, "three Listboxes for three panels"
    # each panel has delete/edit/new buttons — look for those words
    assert "Delete" in src or "delete" in src.lower()
    assert "Edit" in src or "edit" in src.lower()
    # must use messagebox for confirmation
    assert "messagebox" in src and "askyesno" in src, "delete must ask confirmation"
    # must have refresh that reads from store (not cached)
    assert "list_reminders" in src or "get_reminder_panel_rows" in src


def test_desktop_panel_reads_go_through_worker_or_are_fast():
    src = open("desktop.py", encoding="utf-8").read()
    # either route through worker bridge or prove direct read cannot block
    # check for evidence: either panel_list goes via queue/worker, or a comment with measurement
    via_worker = ("panel" in src.lower() and "queue" in src.lower() and "_work" in src)
    # direct fast proof would contain timing comment
    has_measurement = ("measure" in src.lower() and "ms" in src.lower()) or ("prove" in src.lower())
    assert via_worker or has_measurement, "must decide and document threading for panel reads"


def test_desktop_only_interface_touches_widgets():
    import inspect
    ctrl_src = inspect.getsource(desktop.DesktopController)
    assert "tkinter" not in ctrl_src
    assert "Listbox" not in ctrl_src
    assert "Widget" not in ctrl_src
    # DreamDesktop is the only widget toucher — it inserts via after
    assert "after" in open("desktop.py", encoding="utf-8").read()


# ---------------------------------------------------------------------------
# Direction handling for list widget
# ---------------------------------------------------------------------------

def test_list_widget_direction_handling_documented():
    src = open("desktop.py", encoding="utf-8").read()
    # Panel rows must carry direction mark; file uses RLM constant (escaped as \u200f)
    assert "RLM" in src
    assert "\\u200f" in src or desktop.RLM in src
    assert "format_display_line" in src or "RLM" in src


# ---------------------------------------------------------------------------
# Platform skips are annotated on the test (meta-test)
# ---------------------------------------------------------------------------

def test_platform_bound_tests_have_skipif():
    import tests.test_concurrent_processes as mod1
    import tests.test_m13_phone_policy_guards as mod2
    # first file: test_two_real_processes...
    fn1 = mod1.test_two_real_processes_hitting_the_due_check_at_once_are_never_refused
    marks1 = getattr(fn1, "pytestmark", [])
    assert any(getattr(m, "name", None) == "skipif" for m in marks1), "fork test must have skipif"
    # reason must mention fork or Unix
    reasons1 = " ".join(str(getattr(m, "kwargs", {}).get("reason", "")) for m in marks1)
    assert "fork" in reasons1.lower() or "unix" in reasons1.lower(), f"reason must name fork/Unix, got {reasons1!r}"  # noqa: E501

    fn2 = mod2.test_terminal_stats_keeps_the_filesystem_path
    marks2 = getattr(fn2, "pytestmark", [])
    assert any(getattr(m, "name", None) == "skipif" for m in marks2), "path test must have skipif"
    reasons2 = " ".join(str(getattr(m, "kwargs", {}).get("reason", "")) for m in marks2)
    assert "separator" in reasons2.lower() or "escaped" in reasons2.lower() or "windows" in reasons2.lower(), f"reason must name separator/escaped, got {reasons2!r}"  # noqa: E501
