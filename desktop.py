"""Dream desktop window — Milestone M22.

A single window that holds a conversation with the Dream assistant.

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
        # Persian must render right-aligned; mixed lines keep logical order.
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

        self.entry = tk.Entry(bottom, font=("Tahoma", 10))
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

        Only the interface thread calls this (via ``after``-polled ``_poll``).
        The worker never touches a widget.
        """
        tag = _tag_for_text(text + prefix)
        self.transcript.configure(state=tk.NORMAL)
        line = f"{prefix}: {text}\n" if prefix else f"{text}\n"
        self.transcript.insert(tk.END, line, (tag, base_tag))
        self.transcript.configure(state=tk.DISABLED)
        self.transcript.see(tk.END)

    def _on_send(self, event=None) -> None:  # noqa: ARG002
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)
        # Show user line immediately (interface thread)
        self._append_line("\u0634\u0645\u0627", text, "user")
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
                self._append_line("Dream", text, "assistant")
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
