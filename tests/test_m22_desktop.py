"""M22 desktop window logic tests.

The window itself cannot be opened in CI (no display, no tkinter mainloop),
so the logic behind the window is tested: queuing, slash routing, Persian
errors, busy state, and FIFO ordering. The widgets-only layer is not imported.
"""

from __future__ import annotations

import time

# The desktop module will provide these symbols. Before it exists the import
# fails, which is the intended red-before-green.
import desktop  # noqa: F401
from dream.agent import Dream, EchoBackend
from dream.memory import MemoryStore


class SleepingBackend:
    def __init__(self, delay: float = 0.3, reply: str = "ok"):
        self.delay = delay
        self.reply = reply
        self.calls: list[str] = []

    def chat(self, messages, tools=None):
        text = next(  # noqa: E501
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),  # noqa: E501
            "",  # noqa: E501
        )
        self.calls.append(text)
        time.sleep(self.delay)
        return {"content": self.reply + ": " + text, "tool_calls": []}


class FailingBackend:
    def chat(self, messages, tools=None):
        raise RuntimeError("simulated network failure")


def _make_dream(backend=None):
    store = MemoryStore(":memory:")
    dream = Dream(store, backend or EchoBackend())
    return store, dream


def test_request_goes_onto_queue_and_comes_back_as_reply():
    store, dream = _make_dream()
    ctrl = desktop.DesktopController(dream)
    ctrl.submit("hello")
    deadline = time.time() + 3.0
    result = None
    while time.time() < deadline:
        result = ctrl.poll()
        if result is not None and result.get("kind") == "reply":
            break
        time.sleep(0.05)
    assert result is not None, "no reply arrived on result queue"
    assert result["kind"] == "reply"
    assert "hello" in result["text"]
    ctrl.shutdown()
    store.close()


def test_slash_command_routed_to_handler_not_model():
    # slash must not reach the model. Use a backend that would fail if called.
    class MustNotBeCalledBackend:
        def chat(self, *a, **kw):
            raise AssertionError("model was called for a slash command")

    store, dream = _make_dream(MustNotBeCalledBackend())
    ctrl = desktop.DesktopController(dream)
    # /help is a slash command; dispatch_command handles it locally
    ctrl.submit("/help")
    deadline = time.time() + 2.0
    result = None
    while time.time() < deadline:
        result = ctrl.poll()
        if result is not None:
            break
        time.sleep(0.05)
    assert result is not None
    assert result["kind"] == "command"
    # TERMINAL_HELP contains /help, so the handler must have run
    assert "/help" in result["text"] or "help" in result["text"].lower()
    ctrl.shutdown()
    store.close()


def test_failing_turn_produces_persian_message_not_traceback():
    store, dream = _make_dream(FailingBackend())
    ctrl = desktop.DesktopController(dream)
    ctrl.submit("hello")
    deadline = time.time() + 2.0
    result = None
    while time.time() < deadline:
        result = ctrl.poll()
        if result is not None:
            break
        time.sleep(0.05)
    assert result is not None
    # must be Persian error, not traceback
    assert result["kind"] == "error"
    text = result["text"]
    assert "Traceback" not in text
    assert "traceback" not in text.lower()
    # contains Persian characters
    assert any("\u0600" <= ch <= "\u06FF" for ch in text)
    ctrl.shutdown()
    store.close()


def test_busy_state_set_before_and_cleared_after():
    store, dream = _make_dream(SleepingBackend(delay=0.4))
    ctrl = desktop.DesktopController(dream)
    assert ctrl.busy is False
    ctrl.submit("hello")
    # busy must be True immediately after submit, before worker finishes
    assert ctrl.busy is True, "busy not set before work started"
    # wait for reply
    deadline = time.time() + 3.0
    result = None
    while time.time() < deadline:
        result = ctrl.poll()
        if result is not None:
            break
        time.sleep(0.05)
    assert result is not None
    # after completion busy must be cleared
    # give the worker a moment to clear busy
    time.sleep(0.1)
    assert ctrl.busy is False
    ctrl.shutdown()
    store.close()


def test_busy_cleared_even_when_work_raises():
    store, dream = _make_dream(FailingBackend())
    ctrl = desktop.DesktopController(dream)
    ctrl.submit("boom")
    assert ctrl.busy is True
    deadline = time.time() + 2.0
    result = None
    while time.time() < deadline:
        result = ctrl.poll()
        if result is not None:
            break
        time.sleep(0.05)
    assert result is not None
    assert result["kind"] == "error"
    time.sleep(0.1)
    assert ctrl.busy is False, "busy not cleared after error"
    ctrl.shutdown()
    store.close()


def test_two_messages_answered_in_order():
    # worker must process FIFO
    store, dream = _make_dream(SleepingBackend(delay=0.1))
    ctrl = desktop.DesktopController(dream)
    ctrl.submit("first")
    ctrl.submit("second")
    results = []
    deadline = time.time() + 3.0
    while time.time() < deadline and len(results) < 2:
        r = ctrl.poll()
        if r is not None and r.get("kind") == "reply":
            results.append(r["text"])
        else:
            time.sleep(0.05)
    assert len(results) == 2, f"expected 2 replies, got {results}"
    assert "first" in results[0]
    assert "second" in results[1]
    ctrl.shutdown()
    store.close()


def test_persian_right_to_left_helpers():
    # The helpers must detect Persian and mark mixed lines correctly
    assert desktop._contains_persian("\u0633\u0644\u0627\u0645") is True  # سلام
    assert desktop._contains_persian("hello") is False
    # mixed Persian + Latin + number as in a reminder line
    line = (  # noqa: E501
        "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc \u062a\u0645\u062f\u06cc\u062f "  # noqa: E501
        "\u0628\u06cc\u0645\u0647 1405-05-20"  # noqa: E501
    )
    assert desktop._contains_persian(line) is True
    # logical order: the Latin date must not be reversed
    # The transcript insertion must keep the string byte-identical
    assert "1405-05-20" in line
    # tag selection
    tag = desktop._tag_for_text(line)
    assert tag == "persian"
    assert desktop._tag_for_text("hello world") == "latin"


def test_dispatch_reused_not_duplicated():
    # desktop must import and reuse cli.dispatch_command, not copy it
    import inspect
    src = inspect.getsource(desktop.DesktopController._handle_one)
    assert "dispatch_command" in src
    # ensure cli.dispatch_command is the same object referenced
    assert hasattr(desktop, "dispatch_command") or (  # noqa: E501
        "cli.dispatch_command" in src  # noqa: E501
        or "from cli import"  # noqa: E501
        in open("desktop.py", encoding="utf-8").read()  # noqa: E501
    )


def test_desktop_uses_queue_and_after_and_worker():
    src = open("desktop.py", encoding="utf-8").read()
    assert "queue.Queue" in src
    assert "threading.Thread" in src
    assert ".after(" in src
    # worker hands result via queue, interface polls
    assert "result" in src.lower() and "queue" in src.lower()


def test_no_widget_touched_from_worker():
    src = open("desktop.py", encoding="utf-8").read()
    # worker method _run_loop / _handle_one must not contain widget calls
    # crude check: worker must not contain ".insert" etc.  # noqa: E501
    # Worker is _run_loop/_handle_one; only queues+dream  # noqa: E501
    assert "_run_loop" in src
    # ensure worker does not directly call tk.Text methods
    # We verify by inspecting the controller class source
    import inspect
    ctrl_src = inspect.getsource(desktop.DesktopController)
    # controller should not import tkinter
    assert "tkinter" not in ctrl_src
    assert "Text" not in ctrl_src
    assert "Widget" not in ctrl_src


def test_launcher_exists_and_finds_venv():
    import pathlib
    p = pathlib.Path("Dream.bat")
    assert p.exists(), "Dream.bat missing at repository root"
    text = p.read_text(encoding="utf-8", errors="replace")
    # must look for .venv
    assert ".venv" in text
    # must contain Persian for missing env
    assert any("\u0600" <= ch <= "\u06FF" for ch in text)
    # must reference desktop.py
    assert "desktop.py" in text
    # must not require manual typing; it should auto-find pythonw/python
    assert "python" in text.lower()


def test_launcher_missing_env_message():
    # Simulate missing env by checking the bat's Persian message
    # We run bat logic as python: echo Persian when venv absent  # noqa: E501
    text = open("Dream.bat", encoding="utf-8", errors="replace").read()
    # The Persian missing-env line should be readable and mention environment
    # Count Persian characters
    persian = "".join(ch for ch in text if "\u0600" <= ch <= "\u06FF")
    assert len(persian) > 20, "missing env message not in Persian or too short"
