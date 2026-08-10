"""M23 input box — the entry must be right-justified for a Persian typist.

Measured defect: the entry was left-justified, so a Persian typist watched the
cursor sit on the wrong side of the box while the text grew away from the eye.
Right-justifying puts the insertion point on the right edge, where Persian
typing happens.

Lesser harm, chosen deliberately (DESKTOP ENGINEER): in a right-justified
entry a Latin string sits against the right edge of the box instead of the
left. The toolkit does not reorder the Latin characters — the string still
reads left to right internally and the caret stays after the last character —
so the only cost is cosmetic alignment, which is the smaller harm against a
cursor on the wrong side for every Persian sentence. This cannot be exercised
against a real widget in the build (no display), so the configuration is
pinned as data: ``desktop.ENTRY_JUSTIFY`` is what ``_build_widgets`` passes to
``tk.Entry``.
"""

from __future__ import annotations

import inspect

import desktop


def test_entry_justify_constant_is_right():
    # tk.RIGHT is the string "right" when tkinter is present; the constant
    # must resolve to it either way so the pin holds without a display.
    assert desktop.ENTRY_JUSTIFY == "right"


def test_build_widgets_passes_the_constant_to_the_entry():
    src = inspect.getsource(desktop.DreamDesktop._build_widgets)
    assert "tk.Entry" in src
    assert "justify=ENTRY_JUSTIFY" in src


def test_entry_focus_still_lands_on_the_input():
    # The typist's eye goes to the box: focus must still be set on it.
    src = inspect.getsource(desktop.DreamDesktop._build_widgets)
    assert "focus_set" in src
