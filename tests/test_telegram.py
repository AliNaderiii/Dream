"""Pin M5's Telegram security, offset, polling, reminder, and turn boundaries.

The evidence is the Bot API's documented long-poll/offset contract plus the
owner's measured hazards: HTTP headroom, acknowledge-after-handle, private
single-use pairing, visible typing, bounded retries, and one shared-store turn
at a time. Bot interactions use the in-file fake transport; the base-URL test
replaces ``urlopen`` with an in-file response. No test opens the network.
"""

from __future__ import annotations

import threading
import time
import traceback
from types import SimpleNamespace

from dream.agent import EchoBackend
from dream.memory import MemoryStore
from dream.telegram import (
    ALLOWED_UPDATES,
    API_BASE_URL_ENV,
    DEFAULT_API_BASE_URL,
    HTTP_TIMEOUT,
    PAIRING_CONFIRMED_TEXT,
    POLL_BACKOFF_INITIAL,
    POLL_BACKOFF_MAX,
    POLL_TIMEOUT,
    REFUSAL_TEXT,
    TelegramBot,
    TelegramTransport,
    main,
    redact_token,
)

OWNER = 4242
PAIRING_CODE = "314159"


def _fake_token():
    return "123456789" + ":" + "A_b-c" * 7


def _update(
    update_id: int,
    chat_id: int,
    text: str | None,
    *,
    user_id: int | None = None,
    chat_type: str = "private",
):
    message = {
        "chat": {"id": chat_id, "type": chat_type},
        "from": {"id": chat_id if user_id is None else user_id},
    }
    if text is not None:
        message["text"] = text
    return {"update_id": update_id, "message": message}


class FakeTransport:
    """Canned polls and recorded outbound calls; deliberately test-only."""

    def __init__(self, polls=(), *, events=None):
        self.polls = list(polls)
        self.poll_calls = []
        self.send_attempts = []
        self.sent = []
        self.actions = []
        self.events = events if events is not None else []
        self.fail_sends = 0
        self.fail_actions = 0
        self.send_error = RuntimeError("send failed")

    def get_updates(
        self,
        *,
        offset,
        allowed_updates,
        poll_timeout,
        http_timeout,
    ):
        self.poll_calls.append(
            {
                "offset": offset,
                "allowed_updates": tuple(allowed_updates),
                "poll_timeout": poll_timeout,
                "http_timeout": http_timeout,
            }
        )
        item = self.polls.pop(0) if self.polls else []
        if isinstance(item, BaseException):
            raise item
        return item

    def send_message(self, *, chat_id, text, http_timeout):
        call = (chat_id, text, http_timeout)
        self.send_attempts.append(call)
        self.events.append(("send", chat_id, text))
        if self.fail_sends:
            self.fail_sends -= 1
            raise self.send_error
        self.sent.append(call)

    def send_chat_action(self, *, chat_id, action, http_timeout):
        call = (chat_id, action, http_timeout)
        self.actions.append(call)
        self.events.append(("action", chat_id, action))
        if self.fail_actions:
            self.fail_actions -= 1
            raise RuntimeError("action failed")


class FakeHTTPResponse:
    """Context-managed Bot API success used to pin transport URL routing."""

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def read(self):
        return b'{"ok": true, "result": {}}'


class RecordingConversation:
    def __init__(self, store, *, events=None, reply=None):
        self.store = store
        self.events = events if events is not None else []
        self.reply = reply
        self.messages = []
        self.failures = 0
        self.reset_count = 0

    def run(self, message):
        self.messages.append(message)
        self.events.append(("model", message))
        if self.failures:
            self.failures -= 1
            raise RuntimeError("model crashed before answer")
        reply = self.reply if self.reply is not None else f"reply:{message}"
        return SimpleNamespace(reply=reply)

    def reset_session(self):
        self.reset_count += 1
        self.messages.clear()


def _bot(
    store,
    transport,
    *,
    allowed_user=OWNER,
    pairing_code=None,
    pairing_expires_at=None,
    clock=lambda: 1_000.0,
    conversation_factory=None,
    output=None,
    sleep=lambda _seconds: None,
):
    lines = [] if output is None else output
    bot = TelegramBot(
        _fake_token(),
        store,
        transport=transport,
        allowed_user=allowed_user,
        pairing_code=pairing_code,
        pairing_expires_at=pairing_expires_at,
        backend_factory=lambda: EchoBackend(),
        conversation_factory=conversation_factory,
        output=lines.append,
        clock=clock,
        sleep=sleep,
    )
    return bot, lines


def _feeding_input(lines):
    it = iter(lines)

    def read(_prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None

    return read


def test_long_poll_has_http_headroom_and_empty_result_is_success(tmp_path):
    transport = FakeTransport([{"ok": True, "result": []}])
    with MemoryStore(str(tmp_path / "timeouts.db")) as store:
        bot, output = _bot(store, transport)
        assert bot.poll_once() is True

    assert HTTP_TIMEOUT > POLL_TIMEOUT
    assert transport.poll_calls == [
        {
            "offset": 0,
            "allowed_updates": ALLOWED_UPDATES,
            "poll_timeout": POLL_TIMEOUT,
            "http_timeout": HTTP_TIMEOUT,
        }
    ]
    assert not any("failed" in line.lower() for line in output)


def test_api_base_url_defaults_to_official_host_and_honours_environment(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        return FakeHTTPResponse()

    monkeypatch.setattr("dream.telegram.urlopen", fake_urlopen)
    monkeypatch.delenv(API_BASE_URL_ENV, raising=False)
    TelegramTransport(_fake_token()).send_message(
        chat_id=OWNER,
        text="official",
        http_timeout=HTTP_TIMEOUT,
    )

    relay = "https://relay.example.test/telegram"
    monkeypatch.setenv(API_BASE_URL_ENV, relay + "/")
    TelegramTransport(_fake_token()).send_message(
        chat_id=OWNER,
        text="relay",
        http_timeout=HTTP_TIMEOUT,
    )

    suffix = f"/bot{_fake_token()}/sendMessage"
    assert calls == [
        (DEFAULT_API_BASE_URL + suffix, HTTP_TIMEOUT),
        (relay + suffix, HTTP_TIMEOUT),
    ]


def test_offset_advances_to_highest_handled_identifier_plus_one(tmp_path):
    updates = [
        _update(12, OWNER, "third"),
        _update(10, OWNER, "first"),
        _update(11, OWNER, "second"),
    ]
    transport = FakeTransport([updates, []])
    with MemoryStore(str(tmp_path / "offset.db")) as store:
        conversation = RecordingConversation(store)
        bot, _ = _bot(store, transport, conversation_factory=lambda _chat: conversation)
        assert bot.poll_once() is True
        assert bot.offset == 13
        assert conversation.messages == ["first", "second", "third"]
        assert bot.poll_once() is True

    assert transport.poll_calls[1]["offset"] == 13


def test_replayed_update_is_not_answered_twice(tmp_path):
    replay = _update(7, OWNER, "one answer")
    transport = FakeTransport()
    with MemoryStore(str(tmp_path / "replay.db")) as store:
        conversation = RecordingConversation(store)
        bot, _ = _bot(store, transport, conversation_factory=lambda _chat: conversation)
        assert bot.process_updates([replay]) is True
        assert bot.process_updates([replay]) is True
        assert bot.offset == 8

    assert conversation.messages == ["one answer"]
    assert [text for _, text, _ in transport.sent] == ["reply:one answer"]


def test_handling_failure_does_not_advance_offset_and_replay_answers(tmp_path):
    update = _update(21, OWNER, "retry me")
    transport = FakeTransport()
    with MemoryStore(str(tmp_path / "crash.db")) as store:
        conversation = RecordingConversation(store)
        conversation.failures = 1
        bot, output = _bot(store, transport, conversation_factory=lambda _chat: conversation)

        assert bot.process_updates([update]) is False
        assert bot.offset == 0
        assert transport.sent == []

        assert bot.process_updates([update]) is True
        assert bot.offset == 22

    assert conversation.messages == ["retry me", "retry me"]
    assert [text for _, text, _ in transport.sent] == ["reply:retry me"]
    assert any("model crashed before answer" in line for line in output)


def test_unpaired_memory_question_commands_and_reminder_leak_nothing(tmp_path):
    transport = FakeTransport()
    with MemoryStore(str(tmp_path / "refusal.db")) as store:
        secret = "private-memory-value"
        store.remember(secret)

        def forbidden_conversation(_chat_id):
            raise AssertionError("an unpaired chat reached a conversation")

        bot, _ = _bot(
            store,
            transport,
            allowed_user=None,
            pairing_code=PAIRING_CODE,
            pairing_expires_at=2_000,
            conversation_factory=forbidden_conversation,
        )
        memory_question = (
            "\u0627\u0633\u0645 \u0635\u0627\u062d\u0628 \u0631\u0628\u0627\u062a "
            "\u0686\u06cc\u0633\u062a\u061f"
        )
        probes = [
            _update(1, 9001, memory_question),
            _update(2, 9001, "/mems"),
            _update(3, 9001, "/remind 1405-06-01 expose the owner"),
        ]
        assert bot.process_updates(probes) is True
        assert store.list_reminders() == []

    replies = [text for _, text, _ in transport.sent]
    assert replies == [REFUSAL_TEXT, REFUSAL_TEXT, REFUSAL_TEXT]
    assert all(secret not in text for text in replies)


def test_pairing_code_is_single_use(tmp_path):
    transport = FakeTransport()
    with MemoryStore(str(tmp_path / "pair.db")) as store:
        bot, output = _bot(
            store,
            transport,
            allowed_user=None,
            pairing_code=PAIRING_CODE,
            pairing_expires_at=2_000,
        )
        assert output == [
            f"Telegram pairing code: {PAIRING_CODE} (expires in 10 minutes)."
        ]
        assert bot.process_updates([_update(1, 100, f"/pair {PAIRING_CODE}")]) is True
        assert bot.process_updates([_update(2, 200, PAIRING_CODE)]) is True
        rows = store.conn.execute(
            "SELECT chat_id FROM paired_chats ORDER BY chat_id"
        ).fetchall()

    assert [text for _, text, _ in transport.sent] == [
        PAIRING_CONFIRMED_TEXT,
        REFUSAL_TEXT,
    ]
    assert all(PAIRING_CODE not in text for _, text, _ in transport.sent)
    assert [int(row["chat_id"]) for row in rows] == [100]
    assert bot.pairing_code is None


def test_expired_pairing_code_is_refused(tmp_path):
    transport = FakeTransport()
    with MemoryStore(str(tmp_path / "expired.db")) as store:
        bot, _ = _bot(
            store,
            transport,
            allowed_user=None,
            pairing_code=PAIRING_CODE,
            pairing_expires_at=999,
            clock=lambda: 1_000,
        )
        assert bot.process_updates([_update(1, 100, PAIRING_CODE)]) is True
        count = store.conn.execute("SELECT COUNT(*) FROM paired_chats").fetchone()[0]

    assert [text for _, text, _ in transport.sent] == [REFUSAL_TEXT]
    assert count == 0


def test_allowed_user_disables_pairing_code_for_every_other_sender(tmp_path):
    transport = FakeTransport()
    with MemoryStore(str(tmp_path / "allowlist.db")) as store:
        bot, _ = _bot(
            store,
            transport,
            allowed_user=OWNER,
            pairing_code=PAIRING_CODE,
            pairing_expires_at=2_000,
        )
        assert bot.pairing_code is None
        assert bot.process_updates(
            [_update(1, 999, PAIRING_CODE, user_id=999)]
        ) is True
        count = store.conn.execute("SELECT COUNT(*) FROM paired_chats").fetchone()[0]

    assert [text for _, text, _ in transport.sent] == [REFUSAL_TEXT]
    assert count == 0


def test_code_paired_chat_survives_restart_without_a_new_code(tmp_path):
    path = str(tmp_path / "restart.db")
    first_transport = FakeTransport()
    with MemoryStore(path) as store:
        first, _ = _bot(
            store,
            first_transport,
            allowed_user=None,
            pairing_code=PAIRING_CODE,
            pairing_expires_at=2_000,
        )
        first.process_updates([_update(1, 808, PAIRING_CODE)])

    second_transport = FakeTransport()
    with MemoryStore(path) as store:
        conversation = RecordingConversation(store)
        second, output = _bot(
            store,
            second_transport,
            allowed_user=None,
            pairing_code="271828",
            pairing_expires_at=2_000,
            conversation_factory=lambda _chat: conversation,
        )
        assert second.pairing_code is None
        assert second.process_updates([_update(2, 808, "still paired")]) is True

    assert output == []
    assert conversation.messages == ["still paired"]
    assert [text for _, text, _ in second_transport.sent] == ["reply:still paired"]


def _pairing_schema(store):
    columns = [tuple(row) for row in store.conn.execute("PRAGMA table_info(paired_chats)")]
    objects = [
        tuple(row)
        for row in store.conn.execute(
            """SELECT type, name, sql FROM sqlite_master
               WHERE tbl_name = 'paired_chats' ORDER BY type, name"""
        )
    ]
    return columns, objects


def test_old_pairing_table_migration_is_idempotent_when_opened_twice(tmp_path):
    path = str(tmp_path / "old.db")
    with MemoryStore(path) as store:
        store.conn.execute("CREATE TABLE paired_chats (chat_id INTEGER PRIMARY KEY)")
        store.conn.execute("INSERT INTO paired_chats (chat_id) VALUES (808)")
        store.conn.commit()

    with MemoryStore(path) as store:
        first, _ = _bot(store, FakeTransport(), allowed_user=None)
        first_schema = _pairing_schema(store)
        assert first.pairing_code is None

    transport = FakeTransport()
    with MemoryStore(path) as store:
        conversation = RecordingConversation(store)
        second, _ = _bot(
            store,
            transport,
            allowed_user=None,
            conversation_factory=lambda _chat: conversation,
        )
        second_schema = _pairing_schema(store)
        assert second.process_updates([_update(1, 808, "old database")]) is True

    assert second_schema == first_schema
    assert conversation.messages == ["old database"]


def test_each_chat_keeps_its_own_conversation_instance(tmp_path):
    transport = FakeTransport()
    conversations = {}
    with MemoryStore(str(tmp_path / "conversations.db")) as store:

        def factory(chat_id):
            conversation = RecordingConversation(store)
            conversations[chat_id] = conversation
            return conversation

        bot, _ = _bot(store, transport, conversation_factory=factory)
        updates = [
            _update(1, 101, "a1", user_id=OWNER),
            _update(2, 202, "b1", user_id=OWNER),
            _update(3, 101, "a2", user_id=OWNER),
        ]
        assert bot.process_updates(updates) is True

    assert set(conversations) == {101, 202}
    assert conversations[101].messages == ["a1", "a2"]
    assert conversations[202].messages == ["b1"]
    assert conversations[101] is not conversations[202]


class _ConcurrencyTracker:
    def __init__(self):
        self.guard = threading.Lock()
        self.active = 0
        self.maximum = 0
        self.first_entered = threading.Event()
        self.release_first = threading.Event()


class BlockingConversation(RecordingConversation):
    def __init__(self, store, tracker):
        super().__init__(store)
        self.tracker = tracker

    def run(self, message):
        with self.tracker.guard:
            self.tracker.active += 1
            self.tracker.maximum = max(self.tracker.maximum, self.tracker.active)
        try:
            if message == "first":
                self.tracker.first_entered.set()
                assert self.tracker.release_first.wait(2)
            return super().run(message)
        finally:
            with self.tracker.guard:
                self.tracker.active -= 1


def test_two_chats_run_turns_under_one_serialising_lock(tmp_path):
    transport = FakeTransport()
    tracker = _ConcurrencyTracker()
    with MemoryStore(str(tmp_path / "serial.db")) as store:
        bot, _ = _bot(
            store,
            transport,
            conversation_factory=lambda _chat: BlockingConversation(store, tracker),
        )
        first = threading.Thread(
            target=bot.handle_update,
            args=(_update(1, 101, "first", user_id=OWNER),),
        )
        second = threading.Thread(
            target=bot.handle_update,
            args=(_update(2, 202, "second", user_id=OWNER),),
        )
        first.start()
        assert tracker.first_entered.wait(1)
        second.start()
        time.sleep(0.05)
        assert tracker.maximum == 1
        tracker.release_first.set()
        first.join(2)
        second.join(2)

    assert not first.is_alive() and not second.is_alive()
    assert tracker.maximum == 1
    assert [text for _, text, _ in transport.sent] == ["reply:first", "reply:second"]


def test_due_reminder_is_sent_once_and_second_check_is_silent(tmp_path):
    now = 2_000_000_000.0
    transport = FakeTransport()
    with MemoryStore(str(tmp_path / "due.db")) as store:
        bot, _ = _bot(store, transport, clock=lambda: now)
        bot.process_updates([_update(1, OWNER, "/help")])
        transport.sent.clear()
        store.add_reminder("oil service", now - 1)

        first = bot.check_due_reminders(now=now)
        sent_after_first = list(transport.sent)
        second = bot.check_due_reminders(now=now)

    assert len(first) == 1
    assert second == []
    assert len(sent_after_first) == 1
    assert transport.sent == sent_after_first
    assert "oil service" in sent_after_first[0][1]


def test_failed_send_keeps_update_and_retries_prepared_answer(tmp_path):
    transport = FakeTransport()
    transport.fail_sends = 1
    update = _update(31, OWNER, "send reliably")
    with MemoryStore(str(tmp_path / "send.db")) as store:
        conversation = RecordingConversation(store)
        bot, output = _bot(store, transport, conversation_factory=lambda _chat: conversation)

        assert bot.process_updates([update]) is False
        assert bot.offset == 0
        assert bot.process_updates([update]) is True
        assert bot.offset == 32

    assert conversation.messages == ["send reliably"]
    assert len(transport.send_attempts) == 2
    assert [text for _, text, _ in transport.sent] == ["reply:send reliably"]
    assert any("send failed" in line for line in output)


def test_failed_poll_backs_off_and_retries_instead_of_exiting(tmp_path):
    transport = FakeTransport([RuntimeError("offline"), []])
    sleeps = []
    with MemoryStore(str(tmp_path / "poll-retry.db")) as store:
        bot, output = _bot(store, transport, sleep=sleeps.append)
        bot.run(max_polls=2)

    assert len(transport.poll_calls) == 2
    assert sleeps == [POLL_BACKOFF_INITIAL]
    assert any("offline" in line for line in output)


def test_twenty_failed_polls_back_off_to_ceiling_and_then_recover(tmp_path):
    failures = [OSError("tunnel down") for _ in range(20)]
    transport = FakeTransport([*failures, []])
    sleeps = []
    with MemoryStore(str(tmp_path / "long-outage.db")) as store:
        bot, output = _bot(store, transport, sleep=sleeps.append)
        bot.run(max_polls=21)

    expected = [
        min(POLL_BACKOFF_INITIAL * (2**attempt), POLL_BACKOFF_MAX)
        for attempt in range(20)
    ]
    assert len(transport.poll_calls) == 21
    assert sleeps == expected
    assert sleeps[-1] == POLL_BACKOFF_MAX
    assert output.count("Telegram poll failed: OSError: tunnel down") == 20
    assert not bot._stopping.is_set()


def test_reminders_due_during_outage_arrive_once_on_reconnection(tmp_path):
    now = [2_000_000_000.0]
    sleeps = []

    def offline_wait(delay):
        sleeps.append(delay)
        now[0] += 2 * 86400

    transport = FakeTransport([OSError("tunnel down"), OSError("tunnel down"), []])
    with MemoryStore(str(tmp_path / "offline-reminders.db")) as store:
        bot, _ = _bot(
            store,
            transport,
            clock=lambda: now[0],
            sleep=offline_wait,
        )
        bot.process_updates([_update(1, OWNER, "/help")])
        transport.sent.clear()
        transport.send_attempts.clear()

        store.add_reminder("offline one-off", now[0] + 60)
        store.add_reminder("offline repeating", now[0] + 60, repeat_days=1)
        bot.run(max_polls=3)
        sent_on_reconnection = list(transport.sent)
        second = bot.check_due_reminders(now=now[0])

    texts = [text for _, text, _ in sent_on_reconnection]
    assert sleeps == [POLL_BACKOFF_INITIAL, POLL_BACKOFF_INITIAL * 2]
    assert len(texts) == 2
    assert sum("offline one-off" in text for text in texts) == 1
    assert sum("offline repeating" in text for text in texts) == 1
    assert second == []
    assert transport.sent == sent_on_reconnection


def test_token_redaction_masks_every_occurrence_inside_a_line():
    token = _fake_token()
    redacted = redact_token(f"before[{token}]middle {token}!after")
    assert token not in redacted
    assert redacted.count("<redacted-token>") == 2
    assert redacted.startswith("before[") and redacted.endswith("!after")


def test_token_is_absent_from_log_error_and_exception_traceback(tmp_path):
    token = _fake_token()
    samples = [f"log line {token}", f"error: request used {token}"]
    try:
        raise RuntimeError(f"traceback carried {token}")
    except RuntimeError as exc:
        samples.append("".join(traceback.format_exception(exc)))
    assert all(token not in redact_token(sample) for sample in samples)

    transport = FakeTransport()
    transport.fail_sends = 1
    transport.send_error = RuntimeError(f"transport exposed {token}")
    with MemoryStore(str(tmp_path / "token.db")) as store:
        conversation = RecordingConversation(store, reply=f"reply accidentally had {token}")
        bot, output = _bot(store, transport, conversation_factory=lambda _chat: conversation)
        assert bot.process_updates([_update(1, OWNER, "token test")]) is False

    assert all(token not in line for line in output)
    assert all(token not in text for _, text, _ in transport.send_attempts)
    assert any("<redacted-token>" in line for line in output)


def test_typing_indicator_precedes_model_call_and_uses_http_timeout(tmp_path):
    events = []
    transport = FakeTransport(events=events)
    with MemoryStore(str(tmp_path / "typing.db")) as store:
        conversation = RecordingConversation(store, events=events)
        bot, _ = _bot(store, transport, conversation_factory=lambda _chat: conversation)
        assert bot.process_updates([_update(1, OWNER, "slow question")]) is True

    assert [event[0] for event in events] == ["action", "model", "send"]
    assert transport.actions == [(OWNER, "typing", HTTP_TIMEOUT)]
    assert transport.sent[0][2] == HTTP_TIMEOUT


def test_reminder_commands_and_memory_listing_work_in_chat(tmp_path):
    transport = FakeTransport()
    memory_text = (
        "\u0646\u0627\u0645 \u06a9\u0627\u0631\u0628\u0631 "
        "\u0639\u0644\u06cc \u0627\u0633\u062a"
    )
    reminder_text = "\u0633\u0631\u0648\u06cc\u0633 \u0631\u0648\u063a\u0646"
    with MemoryStore(str(tmp_path / "commands.db")) as store:
        store.remember(memory_text)
        bot, _ = _bot(store, transport)
        commands = [
            _update(1, OWNER, "/mems"),
            _update(2, OWNER, f"/remind 1405-06-01 {reminder_text}"),
            _update(3, OWNER, "/reminders"),
            _update(4, OWNER, "/unremind 1"),
        ]
        assert bot.process_updates(commands) is True
        assert store.list_reminders() == []

    replies = [text for _, text, _ in transport.sent]
    assert memory_text in replies[0]
    assert "Reminder #1 set" in replies[1]
    assert reminder_text in replies[2]
    assert "deleted permanently" in replies[3]
    assert transport.actions == []


def test_forget_command_archives_memory_in_chat(tmp_path):
    transport = FakeTransport()
    memory_text = "کاربر روی پروژه آزمایشی کار می‌کند"
    with MemoryStore(str(tmp_path / "forget.db")) as store:
        mem = store.remember(memory_text)
        bot, _ = _bot(store, transport)
        commands = [
            _update(1, OWNER, f"/forget {mem.id}"),
        ]
        assert bot.process_updates(commands) is True
        # Verify the memory was archived in the store
        assert store.get(mem.id, include_archived=False) is None
        assert store.get(mem.id, include_archived=True).archived is True

    replies = [text for _, text, _ in transport.sent]
    assert replies == ["Memory archived."]


def test_forget_command_nonexistent_id(tmp_path):
    transport = FakeTransport()
    with MemoryStore(str(tmp_path / "forget_none.db")) as store:
        bot, _ = _bot(store, transport)
        assert bot.process_updates([_update(1, OWNER, "/forget 999")]) is True

    replies = [text for _, text, _ in transport.sent]
    assert replies == ["No active memory has that ID."]


def test_forget_command_invalid_id_shows_usage(tmp_path):
    transport = FakeTransport()
    with MemoryStore(str(tmp_path / "forget_invalid.db")) as store:
        bot, _ = _bot(store, transport)
        assert bot.process_updates([_update(1, OWNER, "/forget abc")]) is True

    replies = [text for _, text, _ in transport.sent]
    assert replies == ["Usage: /forget ID — ID must be a number."]


def test_forget_command_mistap_without_id_leaves_memories_intact(tmp_path):
    transport = FakeTransport()
    memory_text = "کاربر قهوه تلخ دوست دارد"
    with MemoryStore(str(tmp_path / "forget_mistap.db")) as store:
        mem = store.remember(memory_text)
        bot, _ = _bot(store, transport)
        assert bot.process_updates([_update(1, OWNER, "/forget")]) is True
        # Memory remains active
        assert store.get(mem.id, include_archived=False) is not None

    replies = [text for _, text, _ in transport.sent]
    assert replies == ["Usage: /forget ID — ID must be a number."]


def test_chat_help_includes_forget(tmp_path):
    transport = FakeTransport()
    with MemoryStore(str(tmp_path / "help.db")) as store:
        bot, _ = _bot(store, transport)
        assert bot.process_updates([_update(1, OWNER, "/help")]) is True

    replies = [text for _, text, _ in transport.sent]
    assert "/forget ID" in replies[0]




def test_group_chat_is_refused_even_when_sender_is_allowlisted(tmp_path):
    transport = FakeTransport()
    with MemoryStore(str(tmp_path / "group.db")) as store:
        bot, _ = _bot(store, transport)
        update = _update(
            1,
            -100123,
            "/mems",
            user_id=OWNER,
            chat_type="supergroup",
        )
        assert bot.process_updates([update]) is True

    assert [text for _, text, _ in transport.sent] == [REFUSAL_TEXT]


def test_entrypoint_reads_environment_and_releases_store_on_clean_stop(
    tmp_path,
    monkeypatch,
    capsys,
):
    import dream.telegram as telegram

    transport = FakeTransport()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _fake_token())
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER", str(OWNER))
    monkeypatch.setattr(telegram, "TelegramTransport", lambda _token: transport)

    def one_security_probe(bot):
        bot.process_updates([_update(1, 999, PAIRING_CODE, user_id=999)])
        bot.stop()

    monkeypatch.setattr(telegram.TelegramBot, "run", one_security_probe)
    path = str(tmp_path / "entrypoint.db")

    assert main(["--db", path, "--backend", "echo"]) == 0
    with MemoryStore(path) as reopened:
        assert reopened.stats()["total"] == 0
    captured = capsys.readouterr()
    assert _fake_token() not in captured.out + captured.err
    assert [text for _, text, _ in transport.sent] == [REFUSAL_TEXT]


def test_terminal_entrypoint_test_uses_finite_input_helper(tmp_path, monkeypatch):
    from cli import main as terminal_main

    monkeypatch.setattr("builtins.input", _feeding_input(["/exit"]))
    assert terminal_main(["--db", str(tmp_path / "terminal.db"), "--backend", "echo"]) == 0
