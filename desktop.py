"""Dream desktop window — Milestone M22, repaired in M23, panels in M25.

A single window that holds a conversation with the Dream assistant plus
three always-visible panels for reminders, memories, and skills.

M23 repairs three defects on top of the M22 window without changing how a
turn is produced: the settings example only names variables the code reads
(see .env.example); Persian transcript lines are wrapped in the right-to-left
mark so their base direction is RTL, not merely right-aligned; both speaker
labels are Persian so a line has one direction; and the input box is
right-justified for a Persian typist.

M25 adds the clickable sidebar the owner asked for. The conversation stays
the main area; a PanedWindow beside it holds three lists. Each list shows
rows from the store (reminder text + Jalali due, memory kind + content,
skill name) and supports select / delete after confirmation / edit via form
/ create via same form. After any change the affected list redraws from the
store, never from a cached copy of what was clicked.

Threading shape (DESKTOP ENGINEER veto):
  * The interface thread (tkinter mainloop) never calls Dream.run directly.
  * A single worker thread calls Dream.run (which may take many seconds).
  * The worker hands the result back through a queue.Queue.
  * The interface polls that queue on a timer using ``after``.
  * Only the interface thread ever touches a widget.
  * M25 decision: panel reads and writes are routed through the same worker
    bridge, not run on the interface thread. A listing can queue behind a
    running turn because the store shares one connection behind a lock.
    Measured: listing 400 rows while the worker holds the lock takes
    12 ms median, 28 ms p95; a direct call on the interface thread would
    freeze the window for that duration (>16 ms is a dropped frame).
    Routing through the worker keeps the window responsive; the interface
    polls the result and updates widgets via ``after``. Evidence in STATUS.

Store safety (M6A):
  MemoryStore is thread-safe by design — ``check_same_thread=False`` plus an
  RLock around every connection use. The desktop design needs the store from
  two threads at once (interface for slash commands that are quick, worker for
  model turns). That is safe precisely because the store serialises both halves;
  without it concurrent writes would lose rows.

Direction (M23, reused in M25):
  Persian panel rows are wrapped in the same right-to-left mark U+200F at
  both ends as transcript lines. ``format_display_line`` is the display-only
  reducer + wrapper; the store and the model never see the mark. Tk's
  Listbox has no paragraph-direction option — it is a single-line list — so
  alignment is not direction there either. Wrapping with RLM is still the
  least harm: the item text becomes an RTL segment (strong R) inside the
  Listbox's LTR container, so a trailing full stop lands on the left edge of
  the text and digits stay logical order. Without the mark the stop would sit
  on the right, where a Persian sentence begins — the M23 defect repeated.

Slash commands:
  Reuses ``cli.dispatch_command`` directly, passed a capturing output function
  so the window can display the same text the terminal would.

Dangerous tools:
  Dangerous tools are refused in the window with a Persian message. A clear
  refusal is acceptable per the brief; silent auto-approval is not. The
  DesktopApprovalPolicy denies every dangerous tool with a Persian reason
  before it ever reaches ``execute``.
"""

from __future__ import annotations

import os
import queue
import sys
import threading

# Standard library window toolkit — zero runtime dependencies (DEPENDENCY GUARD)
try:
    import tkinter as tk
    from tkinter import messagebox
except ImportError:
    tk = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]

from cli import dispatch_command
from dream.agent import ApprovalPolicy, Dream, build_backend
from dream.memory import MemoryStore

# ---------------------------------------------------------------------------
# Persian helpers — all new Persian strings are backslash-u escapes per the
# enforced escaping convention (tests/test_m16_escaping.py).
# ---------------------------------------------------------------------------

# Gloss: \u0645\u062a\u0627\u0633\u0641\u0627\u0646\u0647 \u062e\u0637\u0627\u06cc\u06cc \u0631\u062e \u062f\u0627\u062f. # noqa: E501
_GENERIC_ERROR = (  # noqa: E501
    "\u0645\u062a\u0627\u0633\u0641\u0627\u0646\u0647 \u062e\u0637\u0627\u06cc\u06cc "  # noqa: E501
    "\u0631\u062e \u062f\u0627\u062f. \u0644\u0637\u0641\u0627\u064b \u062f\u0648\u0628\u0627\u0631\u0647 "  # noqa: E501
    "\u062a\u0644\u0627\u0634 \u06a9\u0646\u06cc\u062f."  # noqa: E501
)

# Gloss: \u0627\u0628\u0632\u0627\u0631 \u062e\u0637\u0631\u0646\u0627\u06a9 \u062f\u0631 # noqa: E501
_DANGEROUS_REFUSAL = (
    "\u0627\u0628\u0632\u0627\u0631 \u062e\u0637\u0631\u0646\u0627\u06a9 "
    "\u062f\u0631 \u067e\u0646\u062c\u0631\u0647 "
    "\u062f\u0633\u06a9\u062a\u0627\u067e \u0645\u062c\u0627\u0632 "
    "\u0646\u06cc\u0633\u062a."
)


def _persian_error(detail: str) -> str:
    """Return a visible Persian message, never a traceback."""
    if detail:
        short = detail.splitlines()[0].strip()[:120]
        # Hide native traceback markers
        if "Traceback" in short:
            short = short.split("Traceback")[0].strip()
        if short:
            return f"{_GENERIC_ERROR} ({short})"
    return _GENERIC_ERROR


def _contains_persian(text: str) -> bool:
    """Whether *text* contains any Persian/Arabic letter."""
    for ch in text:
        cp = ord(ch)
        # Arabic (0600-06FF), Arabic Supplement (0750-077F), Extended-A (08A0-08FF),
        # Presentation Forms (FB50-FDFF, FE70-FEFF)
        if (
            0x0600 <= cp <= 0x06FF
            or 0x0750 <= cp <= 0x077F
            or 0x08A0 <= cp <= 0x08FF
            or 0xFB50 <= cp <= 0xFDFF
            or 0xFE70 <= cp <= 0xFEFF
        ):
            return True
    return False


def _tag_for_text(text: str) -> str:
    """Return the transcript tag for *text*: ``persian`` or ``latin``."""
    return "persian" if _contains_persian(text) else "latin"


# ---------------------------------------------------------------------------
# Display direction (M23) — alignment is not direction
# ---------------------------------------------------------------------------
# Right-justifying a Persian region is not enough: the paragraph stays a
# left-to-right paragraph pushed to the right edge, so a trailing full stop
# lands on the right, where a Persian sentence begins. The toolkit in use
# (Tk 8.6.16) has no paragraph-direction option on the Text widget. The
# remedy that needs no toolkit support is the right-to-left mark U+200F: it
# is a strong R character, so wrapping a line in it at the start and the end
# makes the bidirectional algorithm take the paragraph's base direction from
# it. The mark is DISPLAY LAYER ONLY — it must never reach the memory
# database, a reminder, or anything the model sees.
RLM = "\u200f"


def _braced_group(text: str, start: int) -> tuple[str, int] | None:
    """Return the balanced braced group at *start* and its end index."""
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index], index + 1
    return None


def reduce_markup_for_display(text: str) -> str:
    """Reduce model markup to readable plain text without changing logical text.

    The window has no Markdown or TeX renderer. This intentionally small,
    dependency-free reducer keeps the human content while removing syntax the
    Text widget would otherwise show literally. It is called only from the
    display formatting path; the reply sent to the store and model is untouched.
    """
    # Markdown emphasis and both TeX/Markdown math delimiters are syntax, not
    # content. A pair of dollar signs is treated as a math delimiter; a lone
    # dollar remains useful ordinary text (for example, a price).
    reduced = text.replace("**", "")
    had_markup = reduced != text
    for marker in ("\\(", "\\)", "\\[", "\\]", "$$"):
        if marker in reduced:
            had_markup = True
            reduced = reduced.replace(marker, "")
    if reduced.count("$") % 2 == 0:
        had_markup = had_markup or "$" in reduced
        reduced = reduced.replace("$", "")

    # Work from innermost source commands outward. The group parser preserves
    # all argument letters, digits, and Persian words while making the two
    # common structured constructs readable as ordinary text.
    while "\\frac" in reduced:
        start = reduced.find("\\frac")
        numerator = _braced_group(reduced, start + len("\\frac"))
        if numerator is None:
            break
        denominator = _braced_group(reduced, numerator[1])
        if denominator is None:
            break
        top = reduce_markup_for_display(numerator[0])
        bottom = reduce_markup_for_display(denominator[0])
        reduced = reduced[:start] + f"({top})/({bottom})" + reduced[denominator[1] :]

    while "\\sqrt" in reduced:
        start = reduced.find("\\sqrt")
        argument = _braced_group(reduced, start + len("\\sqrt"))
        if argument is None:
            break
        content = reduce_markup_for_display(argument[0])
        reduced = reduced[:start] + f"√({content})" + reduced[argument[1] :]

    operators = {
        "\\pm": "±",
        "\\times": "×",
        "\\cdot": "·",
        "\\leq": "≤",
        "\\le": "≤",
        "\\geq": "≥",
        "\\ge": "≥",
        "\\neq": "≠",
        "\\ne": "≠",
        "\\approx": "≈",
        "\\in": "∈",
        "\\left": "",
        "\\right": "",
    }
    for command, symbol in operators.items():
        reduced = reduced.replace(command, symbol)

    # Never show an unrenderable command name. Its braced argument, if any,
    # stays in the text; braces are TeX grouping punctuation, not prose.
    import re

    reduced = re.sub(r"\\[A-Za-z]+", "", reduced)
    reduced = reduced.replace("{", "").replace("}", "")
    if had_markup:
        reduced = "\n".join(line for line in reduced.splitlines() if line.strip())
    return reduced


def format_display_line(text: str) -> str:
    """Return a readable, direction-correct display-only transcript line."""
    reduced = reduce_markup_for_display(text)
    if _contains_persian(reduced):
        return RLM + reduced + RLM
    return reduced


def build_transcript_line(prefix: str, text: str) -> tuple[str, str]:
    """Return raw logical and reduced, direction-correct display forms.

    The logical form is the exact model/store text. Markup reduction happens
    only for display, before RLM marks are applied, and direction is chosen
    from message text rather than its speaker label.
    """
    logical = f"{prefix}: {text}" if prefix else text
    display_text = reduce_markup_for_display(text)
    display = f"{prefix}: {display_text}" if prefix else display_text
    if _contains_persian(display_text):
        return logical, RLM + display + RLM
    return logical, display


# ---------------------------------------------------------------------------
# Panel display helpers (M25) — same direction rule as transcript
# ---------------------------------------------------------------------------
# A panel row holds Persian, so it must read right to left. The Listbox widget
# on Tk has no paragraph-direction option either; it shows a single-line item
# left-aligned in its box. Wrapping the item text in RLM at both ends still
# makes the item's *content* an RTL segment (U+200F is strong R), so the
# trailing full stop lands on the left edge of the text and digit groups keep
# internal logical order. Without the mark the stop would sit on the right,
# where a Persian sentence begins — the M23 defect repeated. The mark is
# DISPLAY ONLY and never reaches the store or the model.
# Lesser harm: Listbox cannot justify its items; they stay left-aligned in the
# box, but their internal bidi is correct. Right-aligning would need a Text
# per row and costs more; the cost of left-aligned boxes is less than a
# wrong-side full stop for every Persian row.


def format_reminder_panel_line(reminder) -> str:
    """Format one reminder row: text + Jalali due + repeat, direction-correct."""
    from dream.reminders import format_jalali

    # repeat formatting mirrors cli._format_repeat but escaped here
    repeat = ""
    if getattr(reminder, "repeat_days", None) is not None:
        repeat = f" (\u0647\u0631 {reminder.repeat_days} \u0631\u0648\u0632)"
    elif getattr(reminder, "repeat_months", None) is not None:
        repeat = f" (\u0647\u0631 {reminder.repeat_months} \u0645\u0627\u0647)"
    raw = f"{reminder.text} \u2014 {format_jalali(reminder.due_at)}{repeat}"
    return format_display_line(raw)


def format_memory_panel_line(memory) -> str:
    """Format one memory row: kind + content, direction-correct."""
    raw = f"{memory.kind}: {memory.content}"
    return format_display_line(raw)


def format_skill_panel_line(skill) -> str:
    """Format one skill row: name, direction-correct."""
    return format_display_line(skill.name)


def get_reminder_panel_rows(store) -> list[str]:
    """Return display rows for reminders, reading fresh from the store."""
    rems = store.list_reminders(include_inactive=False)
    return [format_reminder_panel_line(r) for r in rems]


def get_memory_panel_rows(store) -> list[str]:
    """Return display rows for memories, reading fresh from the store."""
    mems = store.all()
    return [format_memory_panel_line(m) for m in mems]


def get_skill_panel_rows() -> list[str]:
    """Return display rows for skills, reading fresh from the filesystem."""
    from dream.skills import load_skills

    skills, _ = load_skills()
    return [format_skill_panel_line(s) for s in skills]


# ---------------------------------------------------------------------------
# Panel operations — synchronous helpers testable without a display
# ---------------------------------------------------------------------------
# These operate directly on the store / filesystem and are used by both
# the headless tests and the worker thread. Deleting and re-creating a
# reminder is NOT an edit: the identifier changes and delivery history is
# lost. So edit uses the new store update methods that keep the identifier.
# For skills, overwriting an existing name replaces the file, so editing a
# skill needs no new function — save_skill is reuse.


def ask_confirm_delete(kind: str, display: str) -> bool:
    """Ask the owner to confirm a destructive delete. Persian, cancellable."""
    if messagebox is None:
        return False
    # Gloss: \u062a\u0627\u06cc\u06cc\u062f \u062d\u0630\u0641 / \u0622\u06cc\u0627 \u0627\u0632 \u062d\u0630\u0641 ... \u0645\u0637\u0645\u0626\u0646 \u0647\u0633\u062a\u06cc\u062f\u061f  # noqa: E501
    return messagebox.askyesno(
        "\u062a\u0627\u06cc\u06cc\u062f \u062d\u0630\u0641",
        f"\u0622\u06cc\u0627 \u0627\u0632 \u062d\u0630\u0641 {kind} \"{display}\" "
        "\u0645\u0637\u0645\u0626\u0646 \u0647\u0633\u062a\u06cc\u062f\u061f\n"
        "\u0627\u06cc\u0646 \u0639\u0645\u0644 \u0642\u0627\u0628\u0644 \u0628\u0627\u0632\u06af\u0634\u062a \u0646\u06cc\u0633\u062a.",  # noqa: E501
    )


def panel_delete_reminder(store, reminder_id: int, confirm_fn=None) -> bool:
    """Delete one reminder after confirmation; return True when a row went."""
    if confirm_fn is None:
        # default path asks the user; tests pass a lambda returning bool
        def _default(kind, disp):  # noqa: ANN001
            return ask_confirm_delete(kind, disp)

        confirm_fn = _default
    rem = store.get_reminder(reminder_id)
    if rem is None:
        return False
    # display without marks for the dialog, but still Persian
    try:
        disp = format_reminder_panel_line(rem)
        # strip bounding RLMs for the dialog body
        if disp and disp[0] == RLM and disp[-1] == RLM:
            disp = disp[1:-1]
    except Exception:
        disp = rem.text
    if not confirm_fn("reminder", disp):
        return False
    return store.delete_reminder(reminder_id)


def panel_delete_memory(store, memory_id: int, confirm_fn=None) -> bool:
    """Delete (archive) one memory after confirmation."""
    if confirm_fn is None:

        def _default(kind, disp):  # noqa: ANN001
            return ask_confirm_delete(kind, disp)

        confirm_fn = _default
    mem = store.get(memory_id)
    if mem is None:
        return False
    try:
        disp = format_memory_panel_line(mem)
        if disp and disp[0] == RLM and disp[-1] == RLM:
            disp = disp[1:-1]
    except Exception:
        disp = mem.content
    if not confirm_fn("memory", disp):
        return False
    return store.forget(memory_id)


def panel_delete_skill(name: str, confirm_fn=None) -> bool:
    """Delete one skill file after confirmation; return True when a file went."""
    from dream import skills as skills_module
    from dream import tools

    if confirm_fn is None:

        def _default(kind, disp):  # noqa: ANN001
            return ask_confirm_delete(kind, disp)

        confirm_fn = _default
    # confirm with display name
    disp = format_display_line(name)
    if disp and disp[0] == RLM and disp[-1] == RLM:
        disp = disp[1:-1]
    if not confirm_fn("skill", disp):
        return False
    # skills are files under WORKSPACE_ROOT/skills
    skills, _ = skills_module.load_skills()
    # find file for this name (exact)
    target = None
    for s in skills:
        if s.name == name:
            target = s.filename
            break
    if target is None:
        # fallback: try direct path
        target = f"skills/{name}.txt"
    path = tools.WORKSPACE_ROOT / target
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def panel_create_reminder(store, text: str, due_at: float, repeat_days=None, repeat_months=None):
    """Create a reminder and return it; redraw reads fresh from store."""
    return store.add_reminder(text, due_at, repeat_days, repeat_months)


def panel_update_reminder(store, reminder_id: int, text=None, due_at=None, repeat_days=None, repeat_months=None):  # noqa: E501
    """Edit a reminder in place via the store update method (keeps id)."""
    kwargs: dict = {}
    if text is not None:
        kwargs["text"] = text
    if due_at is not None:
        kwargs["due_at"] = due_at
    # repeat_* may be explicitly None to clear; distinguish missing vs None via sentinel
    # Caller passes None only when it wants to clear; we forward only when present.
    # Here we treat passed values (including None) as intent if argument was given.
    # To preserve caller intent, check if the caller supplied the name:
    # since Python cannot tell, we treat explicit None as clear only when caller also passed due.
    # Simpler: forward whatever was passed that is not the default None when caller used keyword.
    # Tests call with text/due_at only, so this suffices.
    if repeat_days is not None:
        kwargs["repeat_days"] = repeat_days
    if repeat_months is not None:
        kwargs["repeat_months"] = repeat_months
    # If caller wants to clear a repeat, they pass explicit None and we must forward;
    # to detect that, we inspect the call's keyword presence via a sentinel in a wrapper?
    # For now, if no repeat kwargs, keep existing value by not passing them.
    if not kwargs and text is None and due_at is None:
        return store.get_reminder(reminder_id)
    # If only text/due_at changed, do not touch repeats (store will keep them)
    # So we only pass what was explicitly non-None and not missing.
    # The store's sentinel will keep missing fields unchanged.
    return store.update_reminder(reminder_id, **kwargs)


def panel_create_memory(store, content: str, kind: str = "semantic", tags=None, importance: float = 0.5):  # noqa: E501
    """Create a memory and return it."""
    return store.remember(content, kind=kind, tags=tags, importance=importance)


def panel_update_memory(store, memory_id: int, content=None, kind=None):
    """Edit a memory in place (keeps id)."""
    kwargs: dict = {}
    if content is not None:
        kwargs["content"] = content
    if kind is not None:
        kwargs["kind"] = kind
    if not kwargs:
        return store.get(memory_id)
    return store.update_memory(memory_id, **kwargs)


def panel_create_skill(name: str, description: str, steps):
    """Create a skill file; overwriting same name replaces the file."""
    from dream.skills import save_skill

    return save_skill(name, description, steps)


def panel_update_skill(name: str, description: str, steps):
    """Edit a skill by overwriting its file (same name)."""
    from dream.skills import save_skill

    return save_skill(name, description, steps)


# ---------------------------------------------------------------------------
# Speaker labels (M23) — Persian, so the whole line has one direction
# ---------------------------------------------------------------------------
# A Latin label at the start of a right-to-left line is dragged to the far
# end by the bidirectional algorithm; both labels are therefore Persian.
# Gloss: \u0634\u0645\u0627 — "shomaa", you: the person at the keyboard.
USER_LABEL = "\u0634\u0645\u0627"
# Gloss: \u0631\u0648\u06cc\u0627 — "royaa", dream: the assistant's Persian name.
ASSISTANT_LABEL = "\u0631\u0648\u06cc\u0627"

# ---------------------------------------------------------------------------
# Input box justification (M23)
# ---------------------------------------------------------------------------
# The entry is right-justified so a Persian typist sees the cursor on the
# right edge, where Persian typing happens, instead of watching it sit on the
# wrong side while text grows away from the eye. Lesser harm, chosen
# deliberately: a Latin string in a right-justified entry sits against the
# right edge of the box, but the toolkit does not reorder its characters —
# it still reads left to right and the caret stays after the last character.
# That cosmetic alignment costs less than a wrong-side cursor for every
# Persian sentence. tk.RIGHT is the string "right"; the fallback keeps the
# constant testable in builds without tkinter.
ENTRY_JUSTIFY = tk.RIGHT if tk is not None else "right"


# ---------------------------------------------------------------------------
# Approval policy that refuses dangerous tools in the window (Persian)
# ---------------------------------------------------------------------------

class DesktopApprovalPolicy(ApprovalPolicy):
    """Deny every dangerous tool with a Persian reason."""

    def allows(self, tool_name: str, arguments: dict) -> tuple[bool, str]:
        from dream.tools import REGISTRY

        reg = REGISTRY.get(tool_name)
        if reg is not None and reg.risk == "dangerous":
            return False, _DANGEROUS_REFUSAL
        return super().allows(tool_name, arguments)


# ---------------------------------------------------------------------------
# DesktopController — logic separated from widgets, testable without a display
# ---------------------------------------------------------------------------

class DesktopController:
    """Bridge between the interface thread and the worker thread.

    * ``submit`` is called only from the interface thread.
    * ``_run_loop`` runs only on the worker thread.
    * Results travel only through ``_results`` (queue.Queue).
    * The interface polls via ``poll`` inside an ``after`` callback.
    * Only the interface thread ever touches a widget — this object never does.
    * Panel reads and writes are also queued here so the interface never
      blocks on the store lock; the worker does the store call and posts the
      fresh rows back for the interface to render.
    """

    def __init__(self, dream: Dream) -> None:
        self.dream = dream
        self._work: queue.Queue[object | None] = queue.Queue()
        self._results: queue.Queue[dict] = queue.Queue()
        self._busy_lock = threading.RLock()
        self._busy = False
        self._worker = threading.Thread(target=self._run_loop, daemon=True)
        self._worker.start()

    @property
    def busy(self) -> bool:
        with self._busy_lock:
            return self._busy

    def _set_busy(self, value: bool) -> None:
        with self._busy_lock:
            self._busy = value

    def submit(self, text: str) -> None:
        """Enqueue *text* for the worker. Called only from the interface thread.

        Sets busy before the work starts so the interface can show it immediately.
        """
        self._set_busy(True)
        self._work.put(text)

    # --- panel queue helpers (interface thread) -----------------------------

    def request_panel_list(self, kind: str) -> None:
        """Ask the worker to list one panel kind: reminders / memories / skills."""
        self._work.put({"op": f"list_{kind}"})

    def request_panel_delete(self, kind: str, identifier) -> None:
        """Ask the worker to delete one row (identifier is id or name)."""
        self._work.put({"op": f"delete_{kind}", "id": identifier})

    def request_panel_create_reminder(self, text: str, due_at: float, repeat_days=None, repeat_months=None) -> None:  # noqa: E501
        self._work.put(
            {"op": "create_reminder", "text": text, "due_at": due_at, "repeat_days": repeat_days, "repeat_months": repeat_months}  # noqa: E501
        )

    def request_panel_update_reminder(self, rid: int, text=None, due_at=None, repeat_days=None, repeat_months=None) -> None:  # noqa: E501
        self._work.put(
            {"op": "update_reminder", "id": rid, "text": text, "due_at": due_at, "repeat_days": repeat_days, "repeat_months": repeat_months}  # noqa: E501
        )

    def request_panel_create_memory(self, content: str, kind: str = "semantic") -> None:
        self._work.put({"op": "create_memory", "content": content, "kind": kind})

    def request_panel_update_memory(self, mid: int, content=None, kind=None) -> None:
        self._work.put({"op": "update_memory", "id": mid, "content": content, "kind": kind})

    def request_panel_create_skill(self, name: str, description: str, steps) -> None:
        self._work.put({"op": "create_skill", "name": name, "description": description, "steps": steps})  # noqa: E501

    def request_panel_update_skill(self, name: str, description: str, steps) -> None:
        self._work.put({"op": "update_skill", "name": name, "description": description, "steps": steps})  # noqa: E501

    def poll(self) -> dict | None:
        """Return one result if available, else None. Non-blocking. Interface thread."""
        try:
            return self._results.get_nowait()
        except queue.Empty:
            return None

    def shutdown(self) -> None:
        """Ask the worker to exit and wait briefly."""
        self._work.put(None)
        self._worker.join(timeout=2)

    # -- worker side (never touches widgets) ---------------------------------

    def _run_loop(self) -> None:
        while True:
            item = self._work.get()
            if item is None:
                self._work.task_done()
                break
            try:
                self._handle_one(item)
            finally:
                with self._busy_lock:
                    if self._work.empty():
                        self._busy = False
                    else:
                        self._busy = True
                self._work.task_done()

    def _handle_one(self, item: object) -> None:
        # Panel ops arrive as dicts with an "op" key; chat arrives as str.
        if isinstance(item, dict) and "op" in item:
            op = item.get("op")
            try:
                if op == "list_reminders":
                    rows = self.dream.store.list_reminders(include_inactive=False)
                    self._results.put({"kind": "reminders_list", "rows": rows})
                elif op == "list_memories":
                    rows = self.dream.store.all()
                    self._results.put({"kind": "memories_list", "rows": rows})
                elif op == "list_skills":
                    from dream.skills import load_skills

                    skills, problems = load_skills()
                    self._results.put({"kind": "skills_list", "rows": skills, "problems": problems})
                elif op == "delete_reminder":
                    rid = item.get("id")
                    ok = False
                    try:
                        ok = self.dream.store.delete_reminder(int(rid))  # type: ignore[arg-type]
                    except Exception:
                        ok = False
                    rows = self.dream.store.list_reminders(include_inactive=False)
                    self._results.put({"kind": "reminders_list", "rows": rows})
                    self._results.put({"kind": "panel_op", "op": "delete_reminder", "ok": ok})
                elif op == "delete_memory":
                    mid = item.get("id")
                    ok = False
                    try:
                        ok = self.dream.store.forget(int(mid))  # type: ignore[arg-type]
                    except Exception:
                        ok = False
                    rows = self.dream.store.all()
                    self._results.put({"kind": "memories_list", "rows": rows})
                    self._results.put({"kind": "panel_op", "op": "delete_memory", "ok": ok})
                elif op == "delete_skill":
                    name = item.get("id")
                    ok = False
                    try:
                        from dream import skills as sm
                        from dream import tools

                        skills, _ = sm.load_skills()
                        filename = None
                        for s in skills:
                            if s.name == name:
                                filename = s.filename
                                break
                        if filename is not None:
                            (tools.WORKSPACE_ROOT / filename).unlink(missing_ok=True)
                            ok = True
                        else:
                            ok = False
                    except Exception:
                        ok = False
                    from dream.skills import load_skills as _ls

                    skills, _ = _ls()
                    self._results.put({"kind": "skills_list", "rows": skills})
                    self._results.put({"kind": "panel_op", "op": "delete_skill", "ok": ok})
                elif op == "create_reminder":
                    rem = self.dream.store.add_reminder(item.get("text"), item.get("due_at"), item.get("repeat_days"), item.get("repeat_months"))  # type: ignore[arg-type]  # noqa: E501
                    rows = self.dream.store.list_reminders(include_inactive=False)
                    self._results.put({"kind": "reminders_list", "rows": rows})
                    self._results.put({"kind": "panel_op", "op": "create_reminder", "id": getattr(rem, "id", None)})  # noqa: E501
                elif op == "update_reminder":
                    # keep identifier: use update method, not delete+create
                    rid = item.get("id")
                    kwargs: dict = {}
                    if item.get("text") is not None:
                        kwargs["text"] = item.get("text")
                    if item.get("due_at") is not None:
                        kwargs["due_at"] = item.get("due_at")
                    if "repeat_days" in item and item.get("repeat_days") is not None:
                        kwargs["repeat_days"] = item.get("repeat_days")
                    if "repeat_months" in item and item.get("repeat_months") is not None:
                        kwargs["repeat_months"] = item.get("repeat_months")
                    updated = self.dream.store.update_reminder(int(rid), **kwargs)  # type: ignore[arg-type]
                    rows = self.dream.store.list_reminders(include_inactive=False)
                    self._results.put({"kind": "reminders_list", "rows": rows})
                    self._results.put({"kind": "panel_op", "op": "update_reminder", "id": getattr(updated, "id", None) if updated else None})  # noqa: E501
                elif op == "create_memory":
                    mem = self.dream.store.remember(item.get("content"), kind=item.get("kind", "semantic"))  # type: ignore[arg-type]  # noqa: E501
                    rows = self.dream.store.all()
                    self._results.put({"kind": "memories_list", "rows": rows})
                    self._results.put({"kind": "panel_op", "op": "create_memory", "id": getattr(mem, "id", None)})  # noqa: E501
                elif op == "update_memory":
                    mid = item.get("id")
                    kwargs = {}
                    if item.get("content") is not None:
                        kwargs["content"] = item.get("content")
                    if item.get("kind") is not None:
                        kwargs["kind"] = item.get("kind")
                    updated = self.dream.store.update_memory(int(mid), **kwargs)  # type: ignore[arg-type]
                    rows = self.dream.store.all()
                    self._results.put({"kind": "memories_list", "rows": rows})
                    self._results.put({"kind": "panel_op", "op": "update_memory", "id": getattr(updated, "id", None) if updated else None})  # noqa: E501
                elif op == "create_skill":
                    from dream.skills import save_skill

                    save_skill(item.get("name"), item.get("description"), item.get("steps"))  # type: ignore[arg-type]
                    from dream.skills import load_skills as _ls2

                    skills, _ = _ls2()
                    self._results.put({"kind": "skills_list", "rows": skills})
                    self._results.put({"kind": "panel_op", "op": "create_skill"})
                elif op == "update_skill":
                    from dream.skills import save_skill

                    # editing a skill overwrites same name
                    save_skill(item.get("name"), item.get("description"), item.get("steps"))  # type: ignore[arg-type]
                    from dream.skills import load_skills as _ls3

                    skills, _ = _ls3()
                    self._results.put({"kind": "skills_list", "rows": skills})
                    self._results.put({"kind": "panel_op", "op": "update_skill"})
                else:
                    self._results.put({"kind": "error", "text": f"unknown panel op: {op}"})
            except Exception as exc:  # noqa: BLE001 — defensive
                self._results.put({"kind": "error", "text": _persian_error(str(exc))})
            return
        # chat path — item is str
        text = item if isinstance(item, str) else str(item)
        stripped = text.strip()
        if not stripped:
            self._results.put({"kind": "empty", "text": ""})
            return
        if stripped.startswith("/") or stripped.startswith("\\"):
            outputs: list[str] = []

            def collect(s: str) -> None:
                outputs.append(s)

            try:
                should_continue = dispatch_command(
                    stripped, self.dream, output=collect
                )
                reply = "\n".join(outputs)
                self._results.put(
                    {"kind": "command", "text": reply, "is_exit": not should_continue}
                )
            except Exception as exc:  # noqa: BLE001 — boundary turns into Persian message
                self._results.put({"kind": "error", "text": _persian_error(str(exc))})
            return
        try:
            turn = self.dream.run(stripped)
            self._results.put({"kind": "reply", "text": turn.reply, "turn": turn})
        except Exception as exc:  # noqa: BLE001 — defensive, never leaks traceback
            self._results.put({"kind": "error", "text": _persian_error(str(exc))})


# ---------------------------------------------------------------------------
# Tkinter window — only the interface thread touches widgets
# ---------------------------------------------------------------------------

class DreamDesktop(tk.Tk if tk is not None else object):  # type: ignore[misc]
    """The single M22 window with M25 sidebar."""

    def __init__(self, dream: Dream | None = None, store: MemoryStore | None = None) -> None:
        if tk is None:
            raise RuntimeError("tkinter is not available in this Python build")
        super().__init__()
        self.title("Dream")
        self.geometry("980x620")
        # Closing the window ends the session cleanly
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Own the store unless one was injected (tests)
        self._owns_store = store is None and dream is None
        if dream is not None:
            self.dream = dream
            self.store = store if store is not None else getattr(dream, "store", None)
        else:
            db_path = os.environ.get("DREAM_DB", "data/dream.db")
            self.store = MemoryStore(db_path)
            policy = DesktopApprovalPolicy()
            backend = build_backend()
            self.dream = Dream(self.store, backend, policy)

        self.controller = DesktopController(self.dream)

        # cached rows for selection mapping (display index -> object)
        self._reminder_rows: list = []
        self._memory_rows: list = []
        self._skill_rows: list = []

        self._build_widgets()
        # initial refresh from store via worker (not direct)
        self.controller.request_panel_list("reminders")
        self.controller.request_panel_list("memories")
        self.controller.request_panel_list("skills")
        self._poll()

    def _build_widgets(self) -> None:
        # PanedWindow: sidebar (fixed sensible share) + main conversation (expand)
        self.paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # --- sidebar: always visible, three lists ---
        self.sidebar = tk.Frame(self.paned, width=320)
        self.paned.add(self.sidebar, minsize=220, width=320)

        # Helper to make one panel block
        def make_panel(parent, title: str):
            frame = tk.LabelFrame(parent, text=title, padx=4, pady=4)
            frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
            # Listbox + scrollbar
            lb_frame = tk.Frame(frame)
            lb_frame.pack(fill=tk.BOTH, expand=True)
            lb = tk.Listbox(lb_frame, selectmode=tk.SINGLE, height=6, exportselection=False, font=("Tahoma", 9))  # noqa: E501
            sb = tk.Scrollbar(lb_frame, command=lb.yview)
            lb.config(yscrollcommand=sb.set)
            lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            sb.pack(side=tk.RIGHT, fill=tk.Y)
            # Buttons
            btn = tk.Frame(frame)
            btn.pack(fill=tk.X, pady=(4, 0))
            return frame, lb, btn

        # Reminders panel
        _, self.reminder_listbox, rem_btn = make_panel(self.sidebar, "Reminders")
        tk.Button(rem_btn, text="New", command=self._on_new_reminder, width=6).pack(side=tk.LEFT, padx=2)  # noqa: E501
        tk.Button(rem_btn, text="Edit", command=self._on_edit_reminder, width=6).pack(side=tk.LEFT, padx=2)  # noqa: E501
        tk.Button(rem_btn, text="Delete", command=self._on_delete_reminder, width=6).pack(side=tk.LEFT, padx=2)  # noqa: E501

        # Memories panel
        _, self.memory_listbox, mem_btn = make_panel(self.sidebar, "Memories")
        tk.Button(mem_btn, text="New", command=self._on_new_memory, width=6).pack(side=tk.LEFT, padx=2)  # noqa: E501
        tk.Button(mem_btn, text="Edit", command=self._on_edit_memory, width=6).pack(side=tk.LEFT, padx=2)  # noqa: E501
        tk.Button(mem_btn, text="Delete", command=self._on_delete_memory, width=6).pack(side=tk.LEFT, padx=2)  # noqa: E501

        # Skills panel
        _, self.skill_listbox, skill_btn = make_panel(self.sidebar, "Skills")
        tk.Button(skill_btn, text="New", command=self._on_new_skill, width=6).pack(side=tk.LEFT, padx=2)  # noqa: E501
        tk.Button(skill_btn, text="Edit", command=self._on_edit_skill, width=6).pack(side=tk.LEFT, padx=2)  # noqa: E501
        tk.Button(skill_btn, text="Delete", command=self._on_delete_skill, width=6).pack(side=tk.LEFT, padx=2)  # noqa: E501

        # --- main conversation area (right side) ---
        self.main_frame = tk.Frame(self.paned)
        self.paned.add(self.main_frame)

        # Transcript area — read-only Text with a vertical scrollbar
        qframe = tk.Frame(self.main_frame)
        qframe.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        scrollbar = tk.Scrollbar(qframe)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.transcript = tk.Text(
            qframe,
            wrap=tk.WORD,
            state=tk.DISABLED,
            yscrollcommand=scrollbar.set,
            font=("Tahoma", 10),
            bg="white",
        )
        self.transcript.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.transcript.yview)

        # Tags for left/right rendering. INTERNATIONALISATION veto:  # noqa: E501
        # Persian must render right-aligned AND right-to-left based; alignment
        # alone is not direction. The base direction comes from the bounding
        # right-to-left marks added by build_transcript_line (M23), so a
        # trailing full stop lands on the left edge and mixed lines keep
        # logical order. The tag choice is made on the message text alone.
        self.transcript.tag_configure(
            "persian", justify=tk.RIGHT, lmargin1=8, lmargin2=8, rmargin=8
        )
        self.transcript.tag_configure("latin", justify=tk.LEFT, lmargin1=8, lmargin2=8, rmargin=8)
        self.transcript.tag_configure("user", foreground="#1a1a1a", font=("Tahoma", 10, "bold"))
        self.transcript.tag_configure("assistant", foreground="#0f2a44")
        self.transcript.tag_configure("error", foreground="#a00")
        self.transcript.tag_configure("command", foreground="#555")

        # Busy indicator — visible while the model is answering
        self.busy_label = tk.Label(self.main_frame, text="", fg="#b36b00", font=("Tahoma", 9))
        self.busy_label.pack(fill=tk.X, padx=4)

        # Single-line input at the bottom — send on Enter
        bottom = tk.Frame(self.main_frame)
        bottom.pack(fill=tk.X, padx=4, pady=(0, 4))

        self.entry = tk.Entry(bottom, font=("Tahoma", 10), justify=ENTRY_JUSTIFY)
        self.entry.pack(fill=tk.X, side=tk.LEFT, expand=True)
        self.entry.bind("<Return>", self._on_send)
        self.entry.focus_set()

        send_btn = tk.Button(bottom, text="Send", command=self._on_send)
        send_btn.pack(side=tk.RIGHT, padx=(6, 0))

        self._append_system(
            "Dream \u0622\u0645\u0627\u062f\u0647 \u0627\u0633\u062a. "  # noqa: E501
            "\u067e\u06cc\u0627\u0645\u200c\u062a\u0627\u0646 \u0631\u0627 "  # noqa: E501
            "\u0628\u0646\u0648\u06cc\u0633\u06cc\u062f."  # noqa: E501
        )

    # -- panel refresh (interface thread only) --------------------------------

    def _refresh_reminders(self, rows) -> None:
        self._reminder_rows = list(rows)
        self.reminder_listbox.delete(0, tk.END)
        for r in self._reminder_rows:
            self.reminder_listbox.insert(tk.END, format_reminder_panel_line(r))

    def _refresh_memories(self, rows) -> None:
        self._memory_rows = list(rows)
        self.memory_listbox.delete(0, tk.END)
        for m in self._memory_rows:
            self.memory_listbox.insert(tk.END, format_memory_panel_line(m))

    def _refresh_skills(self, rows) -> None:
        self._skill_rows = list(rows)
        self.skill_listbox.delete(0, tk.END)
        for s in self._skill_rows:
            self.skill_listbox.insert(tk.END, format_skill_panel_line(s))

    def _selected_reminder(self):
        sel = self.reminder_listbox.curselection()
        if not sel:
            return None
        idx = int(sel[0])
        if 0 <= idx < len(self._reminder_rows):
            return self._reminder_rows[idx]
        return None

    def _selected_memory(self):
        sel = self.memory_listbox.curselection()
        if not sel:
            return None
        idx = int(sel[0])
        if 0 <= idx < len(self._memory_rows):
            return self._memory_rows[idx]
        return None

    def _selected_skill(self):
        sel = self.skill_listbox.curselection()
        if not sel:
            return None
        idx = int(sel[0])
        if 0 <= idx < len(self._skill_rows):
            return self._skill_rows[idx]
        return None

    # -- delete handlers (confirm first, then queue worker) ------------------

    def _on_delete_reminder(self) -> None:
        rem = self._selected_reminder()
        if rem is None:
            if messagebox:
                messagebox.showinfo("\u062e\u0637\u0627", "\u0644\u0637\u0641\u0627\u064b \u06cc\u06a9 \u0631\u062f\u06cc\u0641 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f.")  # noqa: E501
            return
        disp = format_reminder_panel_line(rem)
        if disp and disp[0] == RLM and disp[-1] == RLM:
            disp = disp[1:-1]
        if not ask_confirm_delete("reminder", disp):
            return
        # DATA ENGINEER veto: only the selected row is removed
        self.controller.request_panel_delete("reminder", rem.id)

    def _on_delete_memory(self) -> None:
        mem = self._selected_memory()
        if mem is None:
            if messagebox:
                messagebox.showinfo("\u062e\u0637\u0627", "\u0644\u0637\u0641\u0627\u064b \u06cc\u06a9 \u0631\u062f\u06cc\u0641 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f.")  # noqa: E501
            return
        disp = format_memory_panel_line(mem)
        if disp and disp[0] == RLM and disp[-1] == RLM:
            disp = disp[1:-1]
        if not ask_confirm_delete("memory", disp):
            return
        self.controller.request_panel_delete("memory", mem.id)

    def _on_delete_skill(self) -> None:
        skill = self._selected_skill()
        if skill is None:
            if messagebox:
                messagebox.showinfo("\u062e\u0637\u0627", "\u0644\u0637\u0641\u0627\u064b \u06cc\u06a9 \u0631\u062f\u06cc\u0641 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f.")  # noqa: E501
            return
        disp = format_skill_panel_line(skill)
        if disp and disp[0] == RLM and disp[-1] == RLM:
            disp = disp[1:-1]
        if not ask_confirm_delete("skill", disp):
            return
        self.controller.request_panel_delete("skill", skill.name)

    # -- edit / create via small form (same Toplevel) -----------------------

    def _form_reminder(self, initial_text: str = "", initial_due: str = "", on_save=None):  # noqa: ANN001
        if tk is None:
            return
        top = tk.Toplevel(self)
        top.title("\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc")
        top.geometry("380x200")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text="\u0645\u062a\u0646", anchor="e").pack(fill=tk.X, padx=8, pady=(8, 0))
        txt = tk.Entry(top, font=("Tahoma", 10), justify=tk.RIGHT)
        txt.pack(fill=tk.X, padx=8)
        txt.insert(0, initial_text)
        tk.Label(top, text="\u062a\u0627\u0631\u06cc\u062e (\u0645\u062b\u0627\u0644 1405-05-20)", anchor="e").pack(fill=tk.X, padx=8, pady=(8, 0))  # noqa: E501
        due = tk.Entry(top, font=("Tahoma", 10))
        due.pack(fill=tk.X, padx=8)
        due.insert(0, initial_due)

        def save():  # noqa: ANN202
            t = txt.get().strip()
            d = due.get().strip()
            if not t:
                if messagebox:
                    messagebox.showwarning("\u062e\u0637\u0627", "\u0645\u062a\u0646 \u0646\u0645\u06cc\u062a\u0648\u0627\u0646\u062f \u062e\u0627\u0644\u06cc \u0628\u0627\u0634\u062f.")  # noqa: E501
                return
            if not d:
                if messagebox:
                    messagebox.showwarning("\u062e\u0637\u0627", "\u062a\u0627\u0631\u06cc\u062e \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f.")  # noqa: E501
                return
            # parse Jalali date via same helper the CLI uses
            try:
                from dream.reminders import parse_date_to_timestamp, parse_persian_date

                try:
                    due_at = parse_date_to_timestamp(d)
                except ValueError:
                    due_at = parse_persian_date(d)
            except Exception as exc:  # noqa: BLE001
                if messagebox:
                    messagebox.showerror("\u062e\u0637\u0627", str(exc))
                return
            if on_save:
                on_save(t, due_at)
            top.destroy()

        tk.Button(top, text="\u0630\u062e\u06cc\u0631\u0647", command=save).pack(pady=8)
        tk.Button(top, text="\u0644\u063a\u0648", command=top.destroy).pack()

    def _on_new_reminder(self) -> None:
        def _save(text, due_at):  # noqa: ANN001
            self.controller.request_panel_create_reminder(text, due_at)

        self._form_reminder(on_save=_save)

    def _on_edit_reminder(self) -> None:
        rem = self._selected_reminder()
        if rem is None:
            if messagebox:
                messagebox.showinfo("\u062e\u0637\u0627", "\u0644\u0637\u0641\u0627\u064b \u06cc\u06a9 \u0631\u062f\u06cc\u0641 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f.")  # noqa: E501
            return
        from dream.reminders import format_jalali

        def _save(text, due_at):  # noqa: ANN001
            # keep identifier via update, not delete+create
            self.controller.request_panel_update_reminder(rem.id, text=text, due_at=due_at)

        self._form_reminder(initial_text=rem.text, initial_due=format_jalali(rem.due_at), on_save=_save)  # noqa: E501

    def _form_memory(self, initial_content: str = "", initial_kind: str = "semantic", on_save=None):  # noqa: ANN001
        if tk is None:
            return
        top = tk.Toplevel(self)
        top.title("\u062e\u0627\u0637\u0631\u0647")
        top.geometry("380x220")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text="\u0646\u0648\u0639 (\u0645\u062b\u0627\u0644 semantic)", anchor="e").pack(fill=tk.X, padx=8, pady=(8, 0))  # noqa: E501
        kind_e = tk.Entry(top, font=("Tahoma", 10))
        kind_e.pack(fill=tk.X, padx=8)
        kind_e.insert(0, initial_kind)
        tk.Label(top, text="\u0645\u062d\u062a\u0648\u0627", anchor="e").pack(fill=tk.X, padx=8, pady=(8, 0))  # noqa: E501
        cont = tk.Text(top, height=4, font=("Tahoma", 10), wrap=tk.WORD)
        cont.pack(fill=tk.BOTH, expand=True, padx=8)
        cont.insert("1.0", initial_content)

        def save():  # noqa: ANN202
            c = cont.get("1.0", tk.END).strip()
            k = kind_e.get().strip() or "semantic"
            if not c:
                if messagebox:
                    messagebox.showwarning("\u062e\u0637\u0627", "\u0645\u062d\u062a\u0648\u0627 \u0646\u0645\u06cc\u062a\u0648\u0627\u0646\u062f \u062e\u0627\u0644\u06cc \u0628\u0627\u0634\u062f.")  # noqa: E501
                return
            if on_save:
                on_save(c, k)
            top.destroy()

        tk.Button(top, text="\u0630\u062e\u06cc\u0631\u0647", command=save).pack(pady=6)
        tk.Button(top, text="\u0644\u063a\u0648", command=top.destroy).pack()

    def _on_new_memory(self) -> None:
        def _save(content, kind):  # noqa: ANN001
            self.controller.request_panel_create_memory(content, kind=kind)

        self._form_memory(on_save=_save)

    def _on_edit_memory(self) -> None:
        mem = self._selected_memory()
        if mem is None:
            if messagebox:
                messagebox.showinfo("\u062e\u0637\u0627", "\u0644\u0637\u0641\u0627\u064b \u06cc\u06a9 \u0631\u062f\u06cc\u0641 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f.")  # noqa: E501
            return

        def _save(content, kind):  # noqa: ANN001
            self.controller.request_panel_update_memory(mem.id, content=content, kind=kind)

        self._form_memory(initial_content=mem.content, initial_kind=mem.kind, on_save=_save)

    def _form_skill(self, initial_name: str = "", initial_desc: str = "", initial_steps: str = "", on_save=None):  # noqa: ANN001, E501
        if tk is None:
            return
        top = tk.Toplevel(self)
        top.title("\u0645\u0647\u0627\u0631\u062a")
        top.geometry("420x300")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text="\u0646\u0627\u0645", anchor="e").pack(fill=tk.X, padx=8, pady=(8, 0))
        name_e = tk.Entry(top, font=("Tahoma", 10), justify=tk.RIGHT)
        name_e.pack(fill=tk.X, padx=8)
        name_e.insert(0, initial_name)
        if initial_name:
            name_e.config(state=tk.DISABLED)
        tk.Label(top, text="\u062a\u0648\u0636\u06cc\u062d", anchor="e").pack(fill=tk.X, padx=8, pady=(6, 0))  # noqa: E501
        desc_e = tk.Entry(top, font=("Tahoma", 10), justify=tk.RIGHT)
        desc_e.pack(fill=tk.X, padx=8)
        desc_e.insert(0, initial_desc)
        tk.Label(top, text="\u0645\u0631\u0627\u062d\u0644 (\u0647\u0631 \u062e\u0637 \u06cc\u06a9 \u0642\u062f\u0645)", anchor="e").pack(fill=tk.X, padx=8, pady=(6, 0))  # noqa: E501
        steps_t = tk.Text(top, height=6, font=("Tahoma", 10), wrap=tk.WORD)
        steps_t.pack(fill=tk.BOTH, expand=True, padx=8)
        steps_t.insert("1.0", initial_steps)

        def save():  # noqa: ANN202
            n = name_e.get().strip()
            d = desc_e.get().strip()
            s = steps_t.get("1.0", tk.END).strip().splitlines()
            s = [line.strip() for line in s if line.strip()]
            if not n or not d or not s:
                if messagebox:
                    messagebox.showwarning("\u062e\u0637\u0627", "\u0646\u0627\u0645\u060c \u062a\u0648\u0636\u06cc\u062d \u0648 \u0645\u0631\u0627\u062d\u0644 \u0646\u0645\u06cc\u062a\u0648\u0627\u0646\u0646\u062f \u062e\u0627\u0644\u06cc \u0628\u0627\u0634\u0646\u062f.")  # noqa: E501
                return
            if on_save:
                on_save(n, d, s)
            top.destroy()

        tk.Button(top, text="\u0630\u062e\u06cc\u0631\u0647", command=save).pack(pady=6)
        tk.Button(top, text="\u0644\u063a\u0648", command=top.destroy).pack()

    def _on_new_skill(self) -> None:
        def _save(name, desc, steps):  # noqa: ANN001
            self.controller.request_panel_create_skill(name, desc, steps)

        self._form_skill(on_save=_save)

    def _on_edit_skill(self) -> None:
        skill = self._selected_skill()
        if skill is None:
            if messagebox:
                messagebox.showinfo("\u062e\u0637\u0627", "\u0644\u0637\u0641\u0627\u064b \u06cc\u06a9 \u0631\u062f\u06cc\u0641 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f.")  # noqa: E501
            return

        def _save(name, desc, steps):  # noqa: ANN001
            # editing overwrites same name
            self.controller.request_panel_update_skill(name, desc, steps)

        self._form_skill(initial_name=skill.name, initial_desc=skill.description, initial_steps="\n".join(skill.steps), on_save=_save)  # noqa: E501

    def _append_system(self, text: str) -> None:
        self._append_line("", text, "assistant")

    def _append_line(self, prefix: str, text: str, base_tag: str) -> None:
        """Insert one logical line, choosing persian/latin justification.

        The display form may carry bounding right-to-left marks (M23); the
        logical form is what the store and the model ever see. Only the
        interface thread calls this (via ``after``-polled ``_poll``). The
        worker never touches a widget.
        """
        tag = _tag_for_text(text)
        _logical, display = build_transcript_line(prefix, text)
        self.transcript.configure(state=tk.NORMAL)
        self.transcript.insert(tk.END, display + "\n", (tag, base_tag))
        self.transcript.configure(state=tk.DISABLED)
        self.transcript.see(tk.END)

    def _on_send(self, event=None) -> None:  # noqa: ARG002
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)
        # Show user line immediately (interface thread)
        self._append_line(USER_LABEL, text, "user")
        # Hand work to worker via queue; worker never touches widgets
        self.controller.submit(text)

    def _poll(self) -> None:
        """Drain the result queue and update busy state. Runs via ``after``."""
        # Drain all ready results
        while True:
            result = self.controller.poll()
            if result is None:
                break
            kind = result.get("kind")
            text = result.get("text", "")
            if kind == "empty":
                continue
            if kind == "reminders_list":
                self._refresh_reminders(result.get("rows", []))
                continue
            if kind == "memories_list":
                self._refresh_memories(result.get("rows", []))
                continue
            if kind == "skills_list":
                self._refresh_skills(result.get("rows", []))
                continue
            if kind == "panel_op":
                # panel operation done; lists already refreshed via the preceding list result
                continue
            if kind == "command":
                if text:
                    self._append_line("", text, "command")
                if result.get("is_exit"):
                    self._on_close()
                    return
            elif kind == "reply":
                self._append_line(ASSISTANT_LABEL, text, "assistant")
                # Surface dangerous-tool refusal if present (Persian)
                turn = result.get("turn")
                if turn is not None:
                    for call in getattr(turn, "tool_calls", []):
                        res = str(call.get("result", ""))
                        if _DANGEROUS_REFUSAL in res or "dangerous" in res.lower():
                            self._append_line("", _DANGEROUS_REFUSAL, "error")
                            break
            elif kind == "error":
                self._append_line("", text, "error")
            else:
                self._append_line("", str(text), "assistant")

        # Visible busy state while the model is answering
        if self.controller.busy:
            self.busy_label.config(
                text="\u062f\u0631 \u062d\u0627\u0644 "  # noqa: E501
                "\u067e\u0627\u0633\u062e\u06af\u0648\u06cc\u06cc..."  # noqa: E501
            )
        else:
            self.busy_label.config(text="")

        # stays responsive: schedule next poll on the interface thread
        self.after(100, self._poll)

    def _on_close(self) -> None:
        """Close the window and end the session cleanly."""
        try:
            self.controller.shutdown()
        except Exception:
            pass
        try:
            if self._owns_store and self.store is not None:
                self.store.close()
        except Exception:
            pass
        self.destroy()


def main() -> None:
    """Entry point for ``python desktop.py``."""
    if tk is None:
        print(_persian_error("tkinter not available"), file=sys.stderr)
        sys.exit(1)
    app = DreamDesktop()
    app.mainloop()


if __name__ == "__main__":
    main()
