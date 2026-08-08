"""Long-polling Telegram front end for the local Dream assistant.

The front end opens no inbound port. It keeps one conversation per paired
private chat, shares the local memory store, serialises complete turns, and
uses the existing reminder due-check. Pairing and all Telegram I/O stay in
this module so the memory, scheduler, date parser, and provider interfaces do
not acquire transport concerns.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import secrets
import signal
import sys
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from cli import dispatch_command
from dream.agent import Dream, Turn, build_backend
from dream.memory import MemoryStore
from dream.providers import BuiltInMemoryProvider, ProviderManager

# Telegram holds getUpdates open for POLL_TIMEOUT seconds. The HTTP timeout
# needs ten seconds of transport headroom or every healthy long poll times out
# before Telegram can answer it.
POLL_TIMEOUT = 30
HTTP_TIMEOUT = 40

# The official host is only a default. TELEGRAM_API_BASE_URL lets a laptop
# behind filtering route the same bounded outbound calls through its relay.
DEFAULT_API_BASE_URL = "https://api.telegram.org"
API_BASE_URL_ENV = "TELEGRAM_API_BASE_URL"

ALLOWED_UPDATES = ("message",)
PAIRING_CODE_TTL = 10 * 60
REMINDER_CHECK_INTERVAL = 30
POLL_BACKOFF_INITIAL = 1.0
POLL_BACKOFF_MAX = 30.0
MAX_MESSAGE_LENGTH = 4_000

_TOKEN_RE = re.compile(r"\d+:[A-Za-z0-9_-]{20,}")
_TOKEN_FULL_RE = re.compile(r"\d+:[A-Za-z0-9_-]{20,}\Z")

# New Persian strings are kept as backslash-u escapes.
REFUSAL_TEXT = (
    "\u062f\u0633\u062a\u0631\u0633\u06cc \u0645\u062c\u0627\u0632 "
    "\u0646\u06cc\u0633\u062a."
)
PAIRING_CONFIRMED_TEXT = (
    "\u0627\u062a\u0635\u0627\u0644 \u0627\u0645\u0646 "
    "\u0628\u0631\u0642\u0631\u0627\u0631 \u0634\u062f."
)
TEXT_ONLY_TEXT = (
    "\u0641\u0642\u0637 \u067e\u06cc\u0627\u0645 \u0645\u062a\u0646\u06cc "
    "\u067e\u0630\u06cc\u0631\u0641\u062a\u0647 \u0645\u06cc\u200c\u0634\u0648\u062f."
)
REMINDER_LABEL = (
    "\u06cc\u0627\u062f\u0622\u0648\u0631\u06cc:"
)

CHAT_COMMANDS = frozenset(
    {
        "/mem",
        "/mems",
        "/remind",
        "/reminder",
        "/reminders",
        "/reminder-list",
        "/reminds",
        "/unremind",
        "/reset",
    }
)
CHAT_HELP = (
    "/mem QUERY  /mems  /remind DATE TEXT [every N days|months]  "
    "/reminders  /unremind ID  /reset  /help"
)


class TelegramConfigurationError(ValueError):
    """A safe-to-display Telegram configuration failure."""


class TelegramNetworkError(RuntimeError):
    """A redacted Telegram API or transport failure."""


def redact_token(text: object) -> str:
    """Mask a Telegram-token-shaped value anywhere in printable text."""
    return _TOKEN_RE.sub("<redacted-token>", str(text))


def _exception_text(exc: BaseException) -> str:
    return redact_token(f"{type(exc).__name__}: {exc}")


def _poll_backoff(failures: int) -> float:
    """Return exponential retry delay, stopping arithmetic at the ceiling."""
    delay = POLL_BACKOFF_INITIAL
    for _ in range(max(0, failures - 1)):
        delay = min(delay * 2, POLL_BACKOFF_MAX)
        if delay >= POLL_BACKOFF_MAX:
            break
    return delay


def _parse_allowed_user(raw: str | None) -> int | None:
    """Parse TELEGRAM_ALLOWED_USER, failing closed on a non-numeric value."""
    if raw is None or not raw.strip():
        return None
    value = raw.strip()
    if not value.isdecimal() or int(value) <= 0:
        raise TelegramConfigurationError(
            "TELEGRAM_ALLOWED_USER must be a positive numeric Telegram user identifier."
        )
    return int(value)


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _resolve_api_base_url(raw: str | None = None) -> str:
    """Resolve a safe Bot API base from the environment or official default."""
    configured = os.environ.get(API_BASE_URL_ENV, "") if raw is None else raw
    value = configured.strip() or DEFAULT_API_BASE_URL
    value = value.rstrip("/")
    parsed = urlsplit(value)
    valid = (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and "\r" not in value
        and "\n" not in value
    )
    if not valid:
        raise TelegramConfigurationError(
            f"{API_BASE_URL_ENV} must be an absolute HTTP(S) base URL without credentials, "
            "query, or fragment."
        )
    if parsed.scheme == "http" and not _is_loopback_host(parsed.hostname or ""):
        raise TelegramConfigurationError(
            f"{API_BASE_URL_ENV} must use HTTPS unless it points to this machine."
        )
    return value


class TelegramTransport:
    """Small standard-library client for the Bot API methods used here."""

    def __init__(self, token: str, api_base_url: str | None = None) -> None:
        if not token or _TOKEN_FULL_RE.fullmatch(token) is None:
            raise TelegramConfigurationError(
                "TELEGRAM_BOT_TOKEN is missing or does not have a valid token shape."
            )
        base_url = _resolve_api_base_url(api_base_url)
        self._base_url = f"{base_url}/bot{token}"

    def _call(
        self,
        method: str,
        payload: Mapping[str, object],
        *,
        http_timeout: float,
    ) -> dict[str, Any]:
        request = Request(
            f"{self._base_url}/{method}",
            data=urlencode(payload).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=http_timeout) as response:  # nosec B310: Bot API
                decoded = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise TelegramNetworkError(
                f"Telegram {method} failed: {_exception_text(exc)}"
            ) from None
        if not isinstance(decoded, dict):
            raise TelegramNetworkError(f"Telegram {method} returned a non-object response.")
        if decoded.get("ok") is not True:
            description = redact_token(decoded.get("description", "request rejected"))
            raise TelegramNetworkError(f"Telegram {method} rejected the request: {description}")
        return decoded

    def get_updates(
        self,
        *,
        offset: int,
        allowed_updates: Iterable[str],
        poll_timeout: int,
        http_timeout: float,
    ) -> list[dict[str, Any]]:
        response = self._call(
            "getUpdates",
            {
                "offset": offset,
                "timeout": poll_timeout,
                "allowed_updates": json.dumps(list(allowed_updates)),
            },
            http_timeout=http_timeout,
        )
        result = response.get("result")
        if not isinstance(result, list) or not all(isinstance(item, dict) for item in result):
            raise TelegramNetworkError("Telegram getUpdates returned an invalid result list.")
        return result

    def send_message(self, *, chat_id: int, text: str, http_timeout: float) -> None:
        self._call(
            "sendMessage",
            {"chat_id": chat_id, "text": text},
            http_timeout=http_timeout,
        )

    def send_chat_action(
        self,
        *,
        chat_id: int,
        action: str,
        http_timeout: float,
    ) -> None:
        self._call(
            "sendChatAction",
            {"chat_id": chat_id, "action": action},
            http_timeout=http_timeout,
        )


class _Conversation(Protocol):
    store: MemoryStore

    def run(self, message: str) -> Turn: ...

    def reset_session(self) -> None: ...


class _Transport(Protocol):
    def get_updates(
        self,
        *,
        offset: int,
        allowed_updates: Iterable[str],
        poll_timeout: int,
        http_timeout: float,
    ) -> list[dict[str, Any]] | dict[str, Any]: ...

    def send_message(self, *, chat_id: int, text: str, http_timeout: float) -> None: ...

    def send_chat_action(
        self,
        *,
        chat_id: int,
        action: str,
        http_timeout: float,
    ) -> None: ...


_PAIRED_CHATS_SCHEMA = """
CREATE TABLE IF NOT EXISTS paired_chats (
    chat_id          INTEGER PRIMARY KEY,
    user_id          TEXT    NOT NULL DEFAULT 'local',
    telegram_user_id INTEGER,
    paired_at        REAL    NOT NULL DEFAULT 0
)
"""


class TelegramBot:
    """Secure long-polling coordinator around per-chat Dream conversations."""

    def __init__(
        self,
        token: str,
        memory_store: MemoryStore,
        *,
        transport: _Transport | None = None,
        allowed_user: int | None = None,
        pairing_code: str | None = None,
        pairing_expires_at: float | None = None,
        backend_factory: Callable[[], Any] | None = None,
        provider_manager: ProviderManager | None = None,
        conversation_factory: Callable[[int], _Conversation] | None = None,
        output: Callable[[str], None] = print,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if allowed_user is not None and (
            isinstance(allowed_user, bool) or not isinstance(allowed_user, int) or allowed_user <= 0
        ):
            raise TelegramConfigurationError("allowed_user must be a positive integer.")
        self.memory_store = memory_store
        self.transport = transport if transport is not None else TelegramTransport(token)
        self.allowed_user = allowed_user
        self._output = output
        self._clock = clock
        self._sleep = sleep
        self.offset = 0
        self._conversations: dict[int, _Conversation] = {}
        self._pending_replies: dict[int, tuple[int, str]] = {}
        self._pending_reminders: list[tuple[int, str]] = []
        self._last_reminder_check: float | None = None
        self._stopping = threading.Event()

        # A single Lock covers command/model execution and response delivery.
        # Polling is normally sequential, but this also prevents two externally
        # triggered chats from interleaving history or shared-store operations.
        self._turn_lock = threading.Lock()

        if provider_manager is None:
            provider_manager = ProviderManager()
            provider_manager.register(BuiltInMemoryProvider(memory_store))
        self.provider_manager = provider_manager
        self._backend_factory = backend_factory or build_backend
        self._conversation_factory = conversation_factory or self._build_conversation

        self._ensure_paired_chats_table()
        self.pairing_code: str | None = None
        self.pairing_expires_at: float | None = None
        if self.allowed_user is None and not self._paired_chat_ids():
            code = (
                pairing_code
                if pairing_code is not None
                else f"{secrets.randbelow(1_000_000):06d}"
            )
            if not code.isdecimal() or len(code) != 6:
                raise TelegramConfigurationError("pairing_code must contain exactly six digits.")
            self.pairing_code = code
            self.pairing_expires_at = (
                float(pairing_expires_at)
                if pairing_expires_at is not None
                else self._clock() + PAIRING_CODE_TTL
            )
            self._report(
                f"Telegram pairing code: {code} "
                f"(expires in {PAIRING_CODE_TTL // 60} minutes)."
            )

    def _report(self, text: object) -> None:
        self._output(redact_token(text))

    def _build_conversation(self, _chat_id: int) -> Dream:
        return Dream(
            store=self.memory_store,
            backend=self._backend_factory(),
            manager=self.provider_manager,
        )

    def conversation_for(self, chat_id: int) -> _Conversation:
        """Return the stable conversation instance belonging to one chat."""
        conversation = self._conversations.get(chat_id)
        if conversation is None:
            conversation = self._conversation_factory(chat_id)
            self._conversations[chat_id] = conversation
        return conversation

    def _ensure_paired_chats_table(self) -> None:
        """Create or idempotently migrate the local pairing table."""
        with self.memory_store._lock:
            self.memory_store.conn.execute(_PAIRED_CHATS_SCHEMA)
            columns = {
                row["name"]
                for row in self.memory_store.conn.execute(
                    "PRAGMA table_info(paired_chats)"
                )
            }
            if "chat_id" not in columns:
                self.memory_store.conn.execute(
                    "ALTER TABLE paired_chats ADD COLUMN chat_id INTEGER NOT NULL DEFAULT 0"
                )
            if "user_id" not in columns:
                self.memory_store.conn.execute(
                    "ALTER TABLE paired_chats "
                    "ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'"
                )
            if "telegram_user_id" not in columns:
                self.memory_store.conn.execute(
                    "ALTER TABLE paired_chats ADD COLUMN telegram_user_id INTEGER"
                )
            if "paired_at" not in columns:
                self.memory_store.conn.execute(
                    "ALTER TABLE paired_chats ADD COLUMN paired_at REAL NOT NULL DEFAULT 0"
                )
            self.memory_store.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_paired_chats_user "
                "ON paired_chats(user_id)"
            )
            self.memory_store.conn.commit()

    def _pair_chat(self, chat_id: int, telegram_user_id: int) -> None:
        with self.memory_store._lock:
            self.memory_store.conn.execute(
                """INSERT INTO paired_chats
                   (chat_id, user_id, telegram_user_id, paired_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(chat_id) DO UPDATE SET
                       user_id = excluded.user_id,
                       telegram_user_id = excluded.telegram_user_id,
                       paired_at = excluded.paired_at""",
                (chat_id, self.memory_store.user_id, telegram_user_id, self._clock()),
            )
            self.memory_store.conn.commit()

    def _paired_sender(self, chat_id: int) -> int | None | object:
        with self.memory_store._lock:
            row = self.memory_store.conn.execute(
                """SELECT telegram_user_id FROM paired_chats
                   WHERE user_id = ? AND chat_id = ?""",
                (self.memory_store.user_id, chat_id),
            ).fetchone()
        if row is None:
            return _NOT_PAIRED
        value = row["telegram_user_id"]
        return int(value) if value is not None else None

    def _paired_chat_ids(self) -> list[int]:
        with self.memory_store._lock:
            # Private chat identifiers are positive. The filter is defence in
            # depth for a database migrated from an experimental build that
            # might have recorded a group before private-only pairing existed.
            sql = "SELECT chat_id FROM paired_chats WHERE user_id = ? AND chat_id > 0"
            params: list[object] = [self.memory_store.user_id]
            if self.allowed_user is not None:
                sql += " AND telegram_user_id = ?"
                params.append(self.allowed_user)
            sql += " ORDER BY paired_at, chat_id"
            rows = self.memory_store.conn.execute(sql, params).fetchall()
        return [int(row["chat_id"]) for row in rows]

    def _pairing_candidate(self, text: str) -> str:
        stripped = text.strip()
        command, separator, argument = stripped.partition(" ")
        if command.split("@", 1)[0].lower() == "/pair" and separator:
            return argument.strip()
        return stripped

    def _authorise(
        self,
        chat_id: int,
        telegram_user_id: int,
        chat_type: str,
        text: str,
    ) -> tuple[bool, str | None]:
        # Pairing is private-chat only: a group response would expose owner data
        # to every group member even when the allowed sender initiated it.
        if chat_type != "private":
            return False, REFUSAL_TEXT

        if self.allowed_user is not None:
            # Environment allowlisting has complete precedence. No pairing code
            # is generated or compared while this branch is active.
            if telegram_user_id != self.allowed_user:
                return False, REFUSAL_TEXT
            paired_sender = self._paired_sender(chat_id)
            if paired_sender is _NOT_PAIRED or paired_sender != telegram_user_id:
                self._pair_chat(chat_id, telegram_user_id)
            return True, None

        paired_sender = self._paired_sender(chat_id)
        if paired_sender is not _NOT_PAIRED:
            if paired_sender is None or paired_sender == telegram_user_id:
                return True, None
            return False, REFUSAL_TEXT

        candidate = self._pairing_candidate(text)
        unexpired = (
            self.pairing_code is not None
            and self.pairing_expires_at is not None
            and self._clock() < self.pairing_expires_at
        )
        matches_code = (
            unexpired
            and self.pairing_code is not None
            and secrets.compare_digest(
                candidate.encode("utf-8"),
                self.pairing_code.encode("ascii"),
            )
        )
        if matches_code:
            self._pair_chat(chat_id, telegram_user_id)
            self.pairing_code = None
            self.pairing_expires_at = None
            return False, PAIRING_CONFIRMED_TEXT
        return False, REFUSAL_TEXT

    def _command_text(self, text: str) -> tuple[str, str]:
        head, separator, tail = text.partition(" ")
        command = head.split("@", 1)[0].lower()
        rebuilt = command + (separator + tail if separator else "")
        return command, rebuilt

    def _run_command(self, text: str, conversation: _Conversation) -> str:
        command, rebuilt = self._command_text(text)
        if command in {"/help", "/start"}:
            return CHAT_HELP
        if command not in CHAT_COMMANDS:
            return "This command is not available in Telegram. Type /help."
        lines: list[str] = []
        dispatch_command(rebuilt, conversation, output=lines.append, quiet=True)
        return "\n".join(lines) if lines else "Command completed."

    def _send_message(self, chat_id: int, text: str) -> None:
        safe = redact_token(text)
        if len(safe) > MAX_MESSAGE_LENGTH:
            safe = safe[: MAX_MESSAGE_LENGTH - 18] + "\n... (truncated)"
        self.transport.send_message(
            chat_id=chat_id,
            text=safe,
            http_timeout=HTTP_TIMEOUT,
        )

    def _prepare_reply(self, update: Mapping[str, Any]) -> tuple[int, str] | None:
        message = update.get("message")
        if not isinstance(message, dict):
            return None
        chat = message.get("chat")
        sender = message.get("from")
        if not isinstance(chat, dict) or not isinstance(sender, dict):
            return None
        chat_id = _integer_identifier(chat.get("id"))
        telegram_user_id = _integer_identifier(sender.get("id"))
        if chat_id is None or telegram_user_id is None:
            return None
        chat_type = str(chat.get("type", ""))
        raw_text = message.get("text")
        text = raw_text if isinstance(raw_text, str) else ""

        authorised, immediate_reply = self._authorise(
            chat_id,
            telegram_user_id,
            chat_type,
            text,
        )
        if not authorised:
            return chat_id, immediate_reply or REFUSAL_TEXT
        if not text.strip():
            return chat_id, TEXT_ONLY_TEXT

        conversation = self.conversation_for(chat_id)
        if text.startswith("/"):
            return chat_id, self._run_command(text, conversation)

        # The activity is sent before entering the potentially minute-long
        # model call. Its failure is visible locally but does not suppress the
        # eventual answer.
        try:
            self.transport.send_chat_action(
                chat_id=chat_id,
                action="typing",
                http_timeout=HTTP_TIMEOUT,
            )
        except Exception as exc:
            self._report(f"Typing indicator failed: {_exception_text(exc)}")
        turn = conversation.run(text)
        return chat_id, turn.reply

    def handle_update(self, update: Mapping[str, Any]) -> None:
        """Handle one update and only then advance its offset."""
        update_id = _integer_identifier(update.get("update_id"))
        if update_id is None:
            self._report("Ignored a Telegram update without a numeric update_id.")
            return
        with self._turn_lock:
            if update_id < self.offset:
                return
            pending = self._pending_replies.get(update_id)
            if pending is None:
                pending = self._prepare_reply(update)
                if pending is not None:
                    self._pending_replies[update_id] = pending
            if pending is not None:
                self._send_message(*pending)
                self._pending_replies.pop(update_id, None)
            # This assignment deliberately follows all command/model and send
            # work. An exception above leaves the failed update replayable.
            self.offset = max(self.offset, update_id + 1)

    def process_updates(self, updates: Iterable[Mapping[str, Any]]) -> bool:
        """Process a batch in identifier order, stopping at the first failure."""
        valid: list[tuple[int, Mapping[str, Any]]] = []
        for update in updates:
            update_id = _integer_identifier(update.get("update_id"))
            if update_id is None:
                self._report("Ignored a Telegram update without a numeric update_id.")
                continue
            valid.append((update_id, update))
        for update_id, update in sorted(valid, key=lambda pair: pair[0]):
            try:
                self.handle_update(update)
            except Exception as exc:
                self._report(f"Update {update_id} failed: {_exception_text(exc)}")
                return False
        return True

    def _updates_from_payload(
        self, payload: list[dict[str, Any]] | dict[str, Any]
    ) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise TelegramNetworkError("Telegram poll returned an invalid payload.")
        result = payload.get("result")
        if not isinstance(result, list) or not all(isinstance(item, dict) for item in result):
            raise TelegramNetworkError("Telegram poll returned an invalid update list.")
        return result

    def poll_once(self) -> bool:
        """Complete one bounded long poll and one reminder-cadence check."""
        payload = self.transport.get_updates(
            offset=self.offset,
            allowed_updates=ALLOWED_UPDATES,
            poll_timeout=POLL_TIMEOUT,
            http_timeout=HTTP_TIMEOUT,
        )
        updates = self._updates_from_payload(payload)
        handled = self.process_updates(updates)
        if handled:
            # An empty successful poll is also a reconnection signal. Running
            # the existing due-check here delivers reminders accrued offline.
            self._check_reminders_on_cadence()
        return handled

    def _reminder_text(self, text: str) -> str:
        return f"{REMINDER_LABEL} {text}"

    def _flush_pending_reminders(self) -> None:
        while self._pending_reminders:
            chat_id, text = self._pending_reminders[0]
            self._send_message(chat_id, text)
            self._pending_reminders.pop(0)

    def check_due_reminders(self, now: float | None = None) -> list[Any]:
        """Send each result from the existing due-check to paired chats once."""
        with self._turn_lock:
            self._flush_pending_reminders()
            chat_ids = self._paired_chat_ids()
            if not chat_ids:
                return []
            due = self.memory_store.check_due_reminders(now=now)
            for reminder in due:
                text = self._reminder_text(reminder.text)
                for chat_id in chat_ids:
                    self._pending_reminders.append((chat_id, text))
            self._flush_pending_reminders()
            return due

    def _check_reminders_on_cadence(self) -> None:
        now = self._clock()
        if (
            self._last_reminder_check is not None
            and now - self._last_reminder_check < REMINDER_CHECK_INTERVAL
        ):
            return
        self.check_due_reminders(now=now)
        self._last_reminder_check = now

    def stop(self) -> None:
        """Request a clean stop after the operation currently in flight."""
        self._stopping.set()

    def run(self, *, max_polls: int | None = None) -> None:
        """Poll until stopped, retrying every network or handling failure."""
        previous_handler: Any = None
        installed_handler = False
        if threading.current_thread() is threading.main_thread():
            previous_handler = signal.getsignal(signal.SIGINT)

            def request_stop(_signum: int, _frame: object) -> None:
                # Replacing KeyboardInterrupt with a flag lets an active turn
                # finish; every network call is bounded, so shutdown still ends.
                self.stop()

            signal.signal(signal.SIGINT, request_stop)
            installed_handler = True

        attempts = 0
        failures = 0
        try:
            while not self._stopping.is_set():
                if max_polls is not None and attempts >= max_polls:
                    break
                attempts += 1
                try:
                    succeeded = self.poll_once()
                except KeyboardInterrupt:
                    self.stop()
                    break
                except Exception as exc:
                    self._report(f"Telegram poll failed: {_exception_text(exc)}")
                    succeeded = False
                if succeeded:
                    failures = 0
                    continue
                failures += 1
                if self._stopping.is_set() or (
                    max_polls is not None and attempts >= max_polls
                ):
                    continue
                delay = _poll_backoff(failures)
                try:
                    self._sleep(delay)
                except KeyboardInterrupt:
                    self.stop()
        finally:
            if installed_handler:
                signal.signal(signal.SIGINT, previous_handler)


def _integer_identifier(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdecimal():
        return int(value)
    return None


_NOT_PAIRED = object()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dream Telegram front end")
    parser.add_argument("--backend", choices=("echo", "openai", "ollama"), default="echo")
    parser.add_argument("--db", default="data/dream.db", help="SQLite database path")
    return parser


def _stderr_output(text: str) -> None:
    print(redact_token(text), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """Start Telegram using credentials read exclusively from the environment."""
    args = build_parser().parse_args(argv)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        _stderr_output("TELEGRAM_BOT_TOKEN is required in the environment.")
        return 2
    try:
        allowed_user = _parse_allowed_user(os.environ.get("TELEGRAM_ALLOWED_USER"))
        with MemoryStore(args.db) as memory_store:
            bot = TelegramBot(
                token,
                memory_store,
                allowed_user=allowed_user,
                backend_factory=lambda: build_backend(args.backend),
                output=_stderr_output,
            )
            bot.run()
    except (OSError, TelegramConfigurationError) as exc:
        _stderr_output(f"Could not start Telegram: {_exception_text(exc)}")
        return 2
    except KeyboardInterrupt:
        # A signal normally becomes TelegramBot's stop flag. This protects the
        # small construction/teardown windows too, without a traceback.
        return 0
    except Exception as exc:
        # Keep unexpected startup/teardown failures credential-safe too. Poll
        # and send failures are already retried inside TelegramBot.run().
        _stderr_output(f"Telegram stopped after an error: {_exception_text(exc)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
