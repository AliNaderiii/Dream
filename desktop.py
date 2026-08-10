"""Dream desktop window — Milestone M22, repaired in M23.

A single window that holds a conversation with the Dream assistant.

M23 repairs three defects on top of the M22 window without changing how a
turn is produced: the settings example only names variables the code reads
(see .env.example); Persian transcript lines are wrapped in the right-to-left
mark so their base direction is RTL, not merely right-aligned; both speaker
labels are Persian so a line has one direction; and the input box is
right-justified for a Persian typist.

Threading shape (DESKTOP ENGINEER veto):
  * The interface thread (tkinter mainloop) never calls Dream.run directly.
  * A single worker thread calls Dream.run (which may take many seconds).
  * The worker hands the result back through a queue.Queue.
  * The interface polls that queue on a timer using ``after``.
  * Only the interface thread ever touches a widget.

Store safety (M6A):
  MemoryStore is thread-safe by design — ``check_same_thread=False`` plus an
  RLock around every connection use. The desktop design needs the store from
  two threads at once (interface for slash commands that are quick, worker for
  model turns). That is safe precisely because the store serialises both halves;
  without it concurrent writes would lose rows.

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
    """

    def __init__(self, dream: Dream) -> None:
        self.dream = dream
        self._work: queue.Queue[str | None] = queue.Queue()
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

    def _handle_one(self, text: str) -> None:
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
    """The single M22 window."""

    def __init__(self, dream: Dream | None = None, store: MemoryStore | None = None) -> None:
        if tk is None:
            raise RuntimeError("tkinter is not available in this Python build")
        super().__init__()
        self.title("Dream")
        self.geometry("760x560")
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

        self._build_widgets()
        self._poll()

    def _build_widgets(self) -> None:
        # Transcript area — read-only Text with a vertical scrollbar
        frame = tk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.transcript = tk.Text(
            frame,
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
        self.busy_label = tk.Label(self, text="", fg="#b36b00", font=("Tahoma", 9))
        self.busy_label.pack(fill=tk.X, padx=8)

        # Single-line input at the bottom — send on Enter
        bottom = tk.Frame(self)
        bottom.pack(fill=tk.X, padx=8, pady=(0, 8))

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
