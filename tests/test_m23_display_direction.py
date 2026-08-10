"""M23 Defect Two — alignment is not direction; Persian lines need an RTL base.

The transcript tags a Persian region with right alignment. Alignment is not
direction: the paragraph stays a left-to-right paragraph pushed to the right
edge, so a trailing full stop lands on the right, where a Persian sentence
begins. Measured on the toolkit in use (Tk 8.6.16), the Text widget has no
paragraph-direction option. The remedy available without toolkit support is to
wrap each displayed Persian line in the right-to-left mark U+200F at the start
and at the end: the mark is a strong R character, so the bidirectional
algorithm takes the paragraph's base direction from it.

The window cannot be opened in the build, so this file proves the display
layer by character index. It carries:

* a formatter under test (``desktop.format_display_line`` /
  ``desktop.build_transcript_line``), separated from the widget;
* a minimal UAX #9 resolver modelling the measured widget behaviour, validated
  against the published examples of the standard itself;
* the four acceptance lines, each proven by character index:
  1. a Persian sentence ending in a full stop puts that stop at the LEFT edge;
  2. a line mixing Persian, a Latin word, and a Jalali date keeps all three in
     logical order;
  3. a purely Latin line is unchanged and still reads left to right;
  4. the text written to the store and to the model carries no direction mark.
"""

from __future__ import annotations

import inspect
import time
import unicodedata

import desktop
from dream.agent import Dream, EchoBackend
from dream.memory import MemoryStore

RLM = "\u200f"
_STRONG = ("L", "R", "AL")

# Gloss: \u06af\u0632\u0627\u0631\u0634 \u062c\u0644\u0633\u0647 \u0641\u0631\u062f\u0627 \u0622\u0645\u0627\u062f\u0647 \u0627\u0633\u062a.  # noqa: E501
# ("gozaresh-e jalse-ye farda amade ast." — the report for tomorrow's meeting is ready.)
PERSIAN_SENTENCE = (
    "\u06af\u0632\u0627\u0631\u0634 \u062c\u0644\u0633\u0647 "
    "\u0641\u0631\u062f\u0627 \u0622\u0645\u0627\u062f\u0647 "
    "\u0627\u0633\u062a."
)
# Gloss: \u0627\u06cc\u0646 \u062c\u0645\u0644\u0647 \u06a9\u0627\u0645\u0644 \u0627\u0633\u062a\u06d4  # noqa: E501
# Same sentence shape but ending in the Persian full stop U+06D4.
PERSIAN_SENTENCE_06D4 = (
    "\u0627\u06cc\u0646 \u062c\u0645\u0644\u0647 \u06a9\u0627\u0645\u0644 "
    "\u0627\u0633\u062a\u06d4"
)
# Gloss: \u06cc\u0627\u062f\u0622\u0648\u0631\u06cc \u062a\u0645\u062f\u06cc\u062f \u0628\u06cc\u0645\u0647 insurance \u062a\u0627 1405-05-20  # noqa: E501
# ("insurance renewal reminder, insurance, until 1405-05-20") — Persian, a
# Latin word, and a Jalali date on one line.
MIXED_LINE = (
    "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc \u062a\u0645\u062f\u06cc\u062f "
    "\u0628\u06cc\u0645\u0647 insurance \u062a\u0627 1405-05-20"
)
LATIN_LINE = "Backup completed successfully."


# ---------------------------------------------------------------------------
# Minimal UAX #9 subset — models the measured behaviour of Tk 8.6.16's Text
# ---------------------------------------------------------------------------

def paragraph_base_rtl(line: str) -> bool:
    """The paragraph base direction as the window's toolkit produces it.

    Measured on Tk 8.6.16: the widget keeps a left-to-right base for content
    alone (a Persian paragraph is pushed to the right edge but stays an LTR
    paragraph — the defect under test), and an explicit right-to-left mark at
    the start of the line overrides the base, because it is a strong R
    character. Modelled here: the base is RTL exactly when the first strong
    character is a directional format mark of class R (an RLM leading the
    line). Content letters, AL or L, never flip the base on their own.
    """
    for ch in line:
        if unicodedata.bidirectional(ch) in _STRONG:
            return (
                unicodedata.bidirectional(ch) == "R"
                and unicodedata.category(ch) == "Cf"
            )
    return False


def _resolve_levels(line: str) -> list[int]:
    """Resolved embedding levels for *line* (UAX #9 W/N/I subset)."""
    para = 1 if paragraph_base_rtl(line) else 0
    types = [unicodedata.bidirectional(ch) for ch in line]
    n = len(line)

    # W1: a nonspacing mark takes the type of the previous character.
    for i in range(n):
        if types[i] == "NSM":
            types[i] = types[i - 1] if i > 0 else ("R" if para else "L")

    # W2: EN becomes AN when the nearest preceding strong type is AL.
    last_strong = "R" if para else "L"  # sos
    for i in range(n):
        if types[i] in ("L", "R", "AL"):
            last_strong = types[i]
        elif types[i] == "EN" and last_strong == "AL":
            types[i] = "AN"

    # W3: AL becomes R.
    types = ["R" if t == "AL" else t for t in types]

    # W4: a single ES between two ENs, or a single CS between two numbers of
    # one type, joins the number. (ES between ANs is deliberately NOT covered:
    # the standard converts only CS there, so a hyphen inside a Jalali date
    # that became AN stays a separator — see the mixed-line assertions below.)
    for i in range(1, n - 1):
        left, mid, right = types[i - 1], types[i], types[i + 1]
        if mid == "ES" and left == right == "EN":
            types[i] = "EN"
        elif mid == "CS" and left == right and left in ("EN", "AN"):
            types[i] = left

    # W5: a run of European terminators adjacent to EN becomes EN.
    i = 0
    while i < n:
        if types[i] == "ET":
            j = i
            while j < n and types[j] == "ET":
                j += 1
            before = types[i - 1] if i > 0 else None
            after = types[j] if j < n else None
            if before == "EN" or after == "EN":
                for k in range(i, j):
                    types[k] = "EN"
            i = j
        else:
            i += 1

    # W6: remaining separators and terminators become Other Neutral.
    types = ["ON" if t in ("ES", "ET", "CS") else t for t in types]

    # W7: EN becomes L when the nearest preceding strong type is L.
    last_strong = "R" if para else "L"  # sos
    for i in range(n):
        if types[i] in ("L", "R"):
            last_strong = types[i]
        elif types[i] == "EN" and last_strong == "L":
            types[i] = "L"

    # N1/N2: neutrals take the surrounding direction, else the embedding
    # direction. EN and AN influence neutrals as R.
    def side_level(t: str) -> int:
        if t == "L":
            return para if para % 2 == 0 else para + 1
        return para if para % 2 == 1 else para + 1  # R, EN, AN act as R

    sos = "R" if para % 2 == 1 else "L"
    levels = [0] * n
    i = 0
    while i < n:
        t = types[i]
        if t in ("WS", "ON", "BN"):
            j = i
            while j < n and types[j] in ("WS", "ON", "BN"):
                j += 1
            left_t = types[i - 1] if i > 0 else sos
            right_t = types[j] if j < n else sos  # eos == sos type at para
            left_r = left_t in ("R", "EN", "AN")
            right_r = right_t in ("R", "EN", "AN")
            if left_r == right_r:
                level = side_level("R" if left_r else "L")
            else:
                level = para  # N2: the embedding direction
            for k in range(i, j):
                levels[k] = level
            i = j
        else:
            # I1/I2 plus the strong resolution.
            if t == "L":
                levels[i] = para if para % 2 == 0 else para + 1
            elif t == "R":
                levels[i] = para if para % 2 == 1 else para + 1
            elif t in ("EN", "AN"):
                levels[i] = para + 2 if para % 2 == 0 else para + 1
            else:  # explicit marks and anything else ride the paragraph level
                levels[i] = para
            i += 1
    return levels


def visual_order(line: str) -> str:
    """The visual (left-to-right) order of *line* after L2 reordering."""
    levels = _resolve_levels(line)
    chars = list(line)
    if not chars:
        return ""
    for level in range(max(levels), 0, -1):
        i = 0
        while i < len(chars):
            if levels[i] >= level:
                j = i
                while j < len(chars) and levels[j] >= level:
                    j += 1
                chars[i:j] = reversed(chars[i:j])
                i = j
            else:
                i += 1
    return "".join(chars)


def visible(text: str) -> str:
    """Text without zero-width directional format characters (category Cf)."""
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


# ---------------------------------------------------------------------------
# Model validation — the resolver must reproduce UAX #9's published examples
# ---------------------------------------------------------------------------

def test_model_reproduces_uax9_number_example():
    # Adapted from UAX #9 3.3.5 ("he said 'THE VALUES ARE 123, 456, 789, OK'."):
    # in an RTL paragraph the digit groups keep their internal logical order
    # and appear in reversed group order. Hebrew stands in for the RTL words.
    rtl = "\u05d0\u05de\u05e8"  # Hebrew letters, class R
    line = RLM + rtl + ' "' + rtl + " 123, 456, 789, " + rtl + '".'
    vis = visible(visual_order(line))
    # Each group intact (never mirrored internally) ...
    assert "123" in vis
    assert "456" in vis
    assert "789" in vis
    # ... and in RTL group order: leftmost group is the logically last one.
    assert vis.find("789") < vis.find("456") < vis.find("123")


def test_model_reproduces_uax9_latin_run_example():
    # Adapted from UAX #9 3.3.5 ("IT IS A bmw 500, OK." on an RTL base shows
    # ".KO ,bmw 500 ..."): the Latin run and its number stay internally LTR.
    rtl_a = "\u05d4\u05db\u05dc"  # Hebrew letters, class R
    rtl_b = "\u05d1\u05e1\u05d3\u05e8"
    line = RLM + rtl_a + " bmw 500, " + rtl_b + "."
    vis = visible(visual_order(line))
    assert "bmw 500" in vis, "the Latin run must stay internally LTR"
    assert vis.startswith(".")
    assert vis.find(",") < vis.find("bmw 500")


def test_model_discriminates_marked_from_unmarked():
    # The whole point: content alone keeps the widget's LTR base; a leading
    # RLM flips it. A test that cannot tell these apart proves nothing.
    assert paragraph_base_rtl(PERSIAN_SENTENCE) is False
    assert paragraph_base_rtl(RLM + PERSIAN_SENTENCE) is True
    assert paragraph_base_rtl(LATIN_LINE) is False


# ---------------------------------------------------------------------------
# Acceptance line 1 — the trailing full stop sits on the LEFT edge
# ---------------------------------------------------------------------------

def test_persian_full_stop_lands_on_left_edge():
    logical, display = desktop.build_transcript_line("", PERSIAN_SENTENCE)
    assert logical == PERSIAN_SENTENCE
    # Character-index proof of the wrap: mark at index 0, mark at the end,
    # full stop is the last logical character (index -2).
    assert display[0] == RLM
    assert display[-1] == RLM
    assert display[-2] == "."
    assert display[1:-1] == PERSIAN_SENTENCE
    assert paragraph_base_rtl(display) is True

    vis = visible(visual_order(display))
    assert vis[0] == ".", "the full stop must render at the left edge"
    assert vis[-1] == PERSIAN_SENTENCE[0], "the sentence start must render right"


def test_persian_full_stop_u06d4_lands_on_left_edge():
    logical, display = desktop.build_transcript_line("", PERSIAN_SENTENCE_06D4)
    assert display[-2] == "\u06d4"
    vis = visible(visual_order(display))
    assert vis[0] == "\u06d4"


def test_unmarked_persian_would_put_the_stop_on_the_wrong_edge():
    # Break evidence, modelled: without the mark the widget's base stays LTR.
    # The RTL runs mirror, but the trailing neutral (the full stop) keeps the
    # LTR paragraph direction (UAX #9 N2), so it stays on the RIGHT edge —
    # where a Persian sentence begins. This is the defect.
    assert paragraph_base_rtl(PERSIAN_SENTENCE) is False
    vis = visible(visual_order(PERSIAN_SENTENCE))
    assert vis[-1] == ".", "on the broken LTR base the stop sits on the right"
    assert vis[0] == PERSIAN_SENTENCE.rstrip(".")[-1], "the runs are mirrored"
    assert vis != PERSIAN_SENTENCE


def test_labeled_persian_line_still_ends_on_the_left():
    # With a Persian speaker label in front, the stop still lands left.
    logical, display = desktop.build_transcript_line(
        desktop.ASSISTANT_LABEL, PERSIAN_SENTENCE
    )
    assert logical == f"{desktop.ASSISTANT_LABEL}: {PERSIAN_SENTENCE}"
    assert display[0] == RLM and display[-1] == RLM
    vis = visible(visual_order(display))
    assert vis[0] == "."


# ---------------------------------------------------------------------------
# Acceptance line 2 — mixed line keeps Persian, Latin word, and Jalali date
# in logical order
# ---------------------------------------------------------------------------

def test_mixed_line_keeps_logical_order():
    logical, display = desktop.build_transcript_line("", MIXED_LINE)
    # The display layer adds exactly the two bounding marks: the content is
    # byte-identical, so all three parts keep their logical positions.
    assert logical == MIXED_LINE
    assert display == RLM + MIXED_LINE + RLM
    assert paragraph_base_rtl(display) is True

    vis = visible(visual_order(display))
    # The Latin word is never mirrored internally.
    assert "insurance" in vis
    # UAX #9: the digits became AN (W2), the hyphens are ES which W4 only
    # converts between ENs, so they resolve neutral at the paragraph level
    # (N1/N2) and each digit group keeps its internal logical order while
    # the groups mirror — reading the blocks right-to-left reconstructs the
    # logical Jalali date.
    date_visual = "20-05-1405"
    assert date_visual in vis
    assert "-".join(date_visual.split("-")[::-1]) == "1405-05-20"
    assert vis.find("1405") > vis.find("-05-") > vis.find("20")
    # Reading the line right-to-left reconstructs the logical order:
    # the Persian run sits right of the Latin word, right of the date.
    persian_visual = MIXED_LINE.split()[0][::-1]
    assert vis.find(persian_visual) > vis.find("insurance")
    assert vis.find("insurance") > vis.find(date_visual)


# ---------------------------------------------------------------------------
# Acceptance line 3 — a purely Latin line is unchanged, reads left to right
# ---------------------------------------------------------------------------

def test_latin_line_unchanged_and_reads_left_to_right():
    logical, display = desktop.build_transcript_line("", LATIN_LINE)
    assert display == LATIN_LINE == logical
    assert RLM not in display
    assert paragraph_base_rtl(display) is False
    assert visible(visual_order(display)) == LATIN_LINE


def test_formatter_wraps_persian_and_leaves_latin():
    assert desktop.format_display_line(LATIN_LINE) == LATIN_LINE
    wrapped = desktop.format_display_line(PERSIAN_SENTENCE)
    assert wrapped[0] == RLM
    assert wrapped[-1] == RLM
    assert wrapped[1:-1] == PERSIAN_SENTENCE


# ---------------------------------------------------------------------------
# Acceptance line 4 — stored text and model-facing text carry no mark
# ---------------------------------------------------------------------------

class CapturingBackend:
    """Records every message list handed to the model, then answers as Echo."""

    def __init__(self) -> None:
        self.inner = EchoBackend()
        self.messages_seen: list[list[dict]] = []

    def chat(self, messages, tools=None):
        self.messages_seen.append([dict(m) for m in messages])
        return self.inner.chat(messages, tools)


def _wait_for_reply(ctrl, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = ctrl.poll()
        if result is not None and result.get("kind") == "reply":
            return result
        time.sleep(0.05)
    raise AssertionError("no reply arrived on the result queue")


def test_store_and_model_text_carry_no_direction_mark(monkeypatch):
    monkeypatch.setenv("DREAM_EXTRACTION", "off")
    store = MemoryStore(":memory:")
    backend = CapturingBackend()
    dream = Dream(store, backend)
    ctrl = desktop.DesktopController(dream)
    try:
        ctrl.submit(PERSIAN_SENTENCE)
        result = _wait_for_reply(ctrl)
        assert RLM not in result["text"]

        # Model-facing: every message of every call is mark-free.
        assert backend.messages_seen, "the model was never called"
        for messages in backend.messages_seen:
            for message in messages:
                content = message.get("content") or ""
                assert RLM not in content, f"mark leaked to model: {message!r}"

        # Stored: every text column the turn wrote is mark-free.
        rows = store.conn.execute("SELECT role, content FROM journal").fetchall()
        assert len(rows) >= 2, "expected the user and assistant journal rows"
        for _role, content in rows:
            assert RLM not in content, "mark leaked into the journal"
        for table, column in (("memories", "content"), ("reminders", "text")):
            for (text,) in store.conn.execute(
                f"SELECT {column} FROM {table}"
            ).fetchall():
                assert RLM not in text, f"mark leaked into {table}"
    finally:
        ctrl.shutdown()
        store.close()


def test_model_facing_path_never_touches_the_display_layer():
    # The controller is the model-facing half; it must not format for display.
    ctrl_src = inspect.getsource(desktop.DesktopController)
    assert RLM not in ctrl_src
    assert "format_display_line" not in ctrl_src
    assert "build_transcript_line" not in ctrl_src


def test_widget_inserts_the_formatted_line():
    append_src = inspect.getsource(desktop.DreamDesktop._append_line)
    assert "build_transcript_line" in append_src
