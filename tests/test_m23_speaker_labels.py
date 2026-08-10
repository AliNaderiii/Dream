"""M23 Defect Three — speaker labels must be Persian so the line has one direction.

Each turn is prefixed with a speaker label. A Latin word at the start of a
right-to-left line is dragged to the far end by the bidirectional algorithm,
which is why the assistant's label appeared on the wrong side of the line.
Both labels must be Persian, short, and distinguishable at a glance, and the
visual weight that already distinguishes the person from the assistant (the
bold ``user`` tag against the coloured ``assistant`` tag) must be kept.
"""

from __future__ import annotations

import inspect

import desktop


def test_both_labels_are_persian_and_contain_no_latin():
    for label in (desktop.USER_LABEL, desktop.ASSISTANT_LABEL):
        assert desktop._contains_persian(label), f"label not Persian: {label!r}"
        assert not any(
            "a" <= ch.lower() <= "z" for ch in label
        ), f"label carries Latin letters: {label!r}"


def test_labels_are_short_and_distinguishable():
    for label in (desktop.USER_LABEL, desktop.ASSISTANT_LABEL):
        assert 1 <= len(label) <= 8, f"label not short at a glance: {label!r}"
    assert desktop.USER_LABEL != desktop.ASSISTANT_LABEL


def test_user_line_uses_the_user_label():
    src = inspect.getsource(desktop.DreamDesktop._on_send)
    assert "USER_LABEL" in src
    # The old Latin-era hardcoded prefix must be gone from the send path.
    assert '"Dream"' not in src and "'Dream'" not in src


def test_assistant_line_uses_the_assistant_label():
    src = inspect.getsource(desktop.DreamDesktop._poll)
    assert "ASSISTANT_LABEL" in src
    # The Latin label that fought the line is no longer used for turns.
    assert '_append_line("Dream"' not in src


def test_labels_never_reach_the_model_facing_path():
    # Labels are display layer only; the worker and the model never see them.
    ctrl_src = inspect.getsource(desktop.DesktopController)
    assert "USER_LABEL" not in ctrl_src
    assert "ASSISTANT_LABEL" not in ctrl_src
    assert desktop.USER_LABEL not in ctrl_src
    assert desktop.ASSISTANT_LABEL not in ctrl_src


def test_visual_weight_still_distinguishes_person_from_assistant():
    build_src = inspect.getsource(desktop.DreamDesktop._build_widgets)
    # The user tag keeps its bold weight; the assistant tag keeps its colour.
    assert 'tag_configure("user"' in build_src or "tag_configure('user'" in build_src
    assert "bold" in build_src
    assert (
        'tag_configure("assistant"' in build_src
        or "tag_configure('assistant'" in build_src
    )
    assert "foreground" in build_src


def test_window_title_may_stay_a_single_latin_word():
    # The title bar is not part of a sentence; the brief lets it stay.
    src = inspect.getsource(desktop.DreamDesktop.__init__)
    assert 'title("Dream")' in src or "title('Dream')" in src
