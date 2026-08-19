"""One adapter test per platform, each using an injected fake transport.

No network, no subprocess, no real servers: every seam
(TelegramTransport, DiscordHttp + ws_connect, SlackApi + ws_connect,
WhatsAppApi + webhook server, SignalCli, ImapClient/SmtpClient) is replaced
with a deterministic fake, so the per-platform mechanics run in-process.
"""

from __future__ import annotations

import asyncio
import email.message
import json
import tempfile
import urllib.error
import urllib.request
from typing import Any

import pytest

from dream.connectivity.adapters.discord import DiscordAdapter, DiscordError
from dream.connectivity.adapters.email import (
    EmailAdapter,
    EmailError,
    ImapClient,
    SmtpClient,
    html_to_text,
)
from dream.connectivity.adapters.signal import (
    SignalAdapter,
    SignalCliError,
    _message_source,
    _message_text,
    _parse_envelopes,
)
from dream.connectivity.adapters.slack import SlackAdapter
from dream.connectivity.adapters.telegram import TelegramAdapter, TelegramTransport
from dream.connectivity.adapters.whatsapp import (
    WhatsAppAdapter,
    _extract_messages,
)
from dream.connectivity.models import IncomingMessage


class _Recorder:
    """An async on_message recorder shared by the adapter tests."""

    def __init__(self) -> None:
        self.messages: list[IncomingMessage] = []

    async def __call__(self, message: IncomingMessage) -> None:
        self.messages.append(message)


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# Telegram — long polling via an injected transport
# --------------------------------------------------------------------------- #


class _FakeTelegramTransport:
    def __init__(self, updates: list[dict[str, Any]]) -> None:
        self.updates = list(updates)
        self.sent: list[tuple[int, str]] = []
        self.actions: list[tuple[int, str]] = []
        self.offsets: list[int] = []

    def get_updates(self, offset: int) -> list[dict[str, Any]]:
        self.offsets.append(offset)
        batch, self.updates = self.updates[:1], self.updates[1:]
        return batch

    def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    def send_chat_action(self, chat_id: int, action: str) -> None:
        self.actions.append((chat_id, action))


def test_telegram_adapter_polls_and_delivers_normalised_messages():
    transport = _FakeTelegramTransport(
        [
            {
                "update_id": 11,
                "message": {
                    "message_id": 5,
                    "date": 1700000000,
                    "chat": {"id": 99, "type": "private"},
                    "from": {"id": 42, "is_bot": False},
                    "text": "hello dream",
                },
            },
            {
                "update_id": 12,
                "message": {
                    "message_id": 6,
                    "chat": {"id": 99, "type": "private"},
                    "from": {"id": 42, "is_bot": False},
                    "text": "",
                },
            },
        ]
    )
    recorder = _Recorder()
    adapter = TelegramAdapter(
        {"token": "123456:abcdefghijklmnopqrstuvwx", "poll_interval": 0.01},
        on_message=recorder,
        transport=transport,
    )

    async def scenario() -> None:
        await adapter.start()
        for _ in range(50):
            if len(recorder.messages) >= 1:
                break
            await asyncio.sleep(0.02)
        await adapter.stop()
        assert len(recorder.messages) == 1  # the empty-text update is skipped
        message = recorder.messages[0]
        assert message.platform == "telegram"
        assert message.platform_user_id == "42"
        assert message.platform_channel_id == "99"
        assert message.text == "hello dream"
        assert message.message_id == "5"
        assert message.raw["update_id"] == 11
        # The offset advanced past the handled update.
        assert 12 in transport.offsets

    asyncio.run(scenario())


def test_telegram_adapter_sends_and_types_through_the_transport():
    transport = _FakeTelegramTransport([])
    adapter = TelegramAdapter(
        {"token": "123456:abcdefghijklmnopqrstuvwx"},
        on_message=_Recorder(),
        transport=transport,
    )

    async def scenario() -> None:
        await adapter.send_message("99", "hello out")
        await adapter.send_typing_indicator("99")
        assert transport.sent == [(99, "hello out")]
        assert transport.actions == [(99, "typing")]

    asyncio.run(scenario())


def test_telegram_transport_validates_token_shape():
    with pytest.raises(ValueError):
        TelegramTransport("not-a-token")


# --------------------------------------------------------------------------- #
# Discord — fake REST + scripted websocket frames
# --------------------------------------------------------------------------- #


class _FakeDiscordHttp:
    def __init__(self, application_id: str = "app-1") -> None:
        self.application_id = application_id
        self.sent: list[tuple[str, str]] = []
        self.responded: list[tuple[str, str]] = []
        self.edited: list[tuple[str, str, str]] = []
        self.threads: list[tuple[str, str, str]] = []

    def get_current_application(self) -> dict[str, Any]:
        return {"id": self.application_id}

    def register_command(self, application_id: str) -> dict[str, Any]:
        return {"id": application_id}

    def send_message(self, channel_id: str, content: str) -> dict[str, Any]:
        self.sent.append((channel_id, content))
        return {"id": "m1"}

    def send_file(
        self, channel_id: str, filename: str, data: bytes, content: str = ""
    ) -> dict[str, Any]:
        self.sent.append((channel_id, f"[file {filename}] {content}"))
        return {"id": "m2"}

    def create_thread(self, channel_id: str, message_id: str, name: str) -> dict[str, Any]:
        self.threads.append((channel_id, message_id, name))
        return {"id": "thread-1"}

    def respond_interaction(self, interaction_id: str, token: str) -> None:
        self.responded.append((interaction_id, token))

    def edit_interaction(self, application_id: str, token: str, content: str) -> dict[str, Any]:
        self.edited.append((application_id, token, content))
        return {"id": "m3"}


def _discord_frame(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


def test_discord_adapter_gateway_session_and_interaction_followup():
    http = _FakeDiscordHttp()
    recorder = _Recorder()

    events = [
        {"op": 10, "d": {"heartbeat_interval": 41250}},  # Hello
        {  # MESSAGE_CREATE from a user
            "op": 0,
            "t": "MESSAGE_CREATE",
            "s": 1,
            "d": {
                "id": "10",
                "channel_id": "ch-1",
                "guild_id": "g-1",
                "author": {"id": "user-1", "username": "ana", "bot": False},
                "content": "hi from discord",
                "attachments": [
                    {
                        "filename": "pic.png",
                        "content_type": "image/png",
                        "url": "https://cdn/pic.png",
                        "size": 5,
                    }
                ],
            },
        },
        {"op": 11},  # heartbeat ACK
        {  # INTERACTION_CREATE for the /dream command
            "op": 0,
            "t": "INTERACTION_CREATE",
            "s": 2,
            "d": {
                "id": "i-1",
                "token": "tok-1",
                "application_id": "app-1",
                "channel_id": "ch-2",
                "type": 2,
                "data": {
                    "name": "dream",
                    "options": [{"name": "message", "value": "command message"}],
                },
                "member": {"user": {"id": "user-2"}},
            },
        },
    ]

    class _FakeWs:
        def __init__(self) -> None:
            self.queue = asyncio.Queue()
            self.sent: list[dict[str, Any]] = []

        async def send_json(self, payload: dict[str, Any]) -> None:
            self.sent.append(payload)

        async def recv_json(self) -> dict[str, Any]:
            item = await self.queue.get()
            if item is None:
                raise StopAsyncIteration
            return json.loads(item) if isinstance(item, str) else item

        async def recv_text(self) -> str:
            item = await self.queue.get()
            if item is None:
                raise StopAsyncIteration
            return item

        def __aiter__(self):
            return self

        async def __anext__(self) -> str:
            item = await self.queue.get()
            if item is None:
                raise StopAsyncIteration
            return item

        async def close(self) -> None:
            await self.queue.put(None)

    ws = _FakeWs()
    for event in events:
        ws.queue.put_nowait(_discord_frame(event))

    async def ws_connect(url: str):
        del url
        return ws

    adapter = DiscordAdapter(
        {"bot_token": "tok", "application_id": "app-1", "register_commands": False},
        on_message=recorder,
        http=http,
        ws_connect=ws_connect,
    )

    async def scenario() -> None:
        await adapter.start()
        # Give the session task a chance to consume the queued events.
        for _ in range(100):
            if len(recorder.messages) >= 2:
                break
            await asyncio.sleep(0.02)
        await adapter.stop()

        assert len(recorder.messages) == 2
        message = recorder.messages[0]
        assert message.platform_user_id == "user-1"
        assert message.text == "hi from discord"
        assert message.attachments[0].filename == "pic.png"
        interaction = recorder.messages[1]
        assert interaction.platform_user_id == "user-2"
        assert interaction.text == "command message"

        # Identify went out (with compress: false), then heartbeats.
        identify = [item for item in ws.sent if item.get("op") == 2]
        assert identify and identify[0]["d"]["compress"] is False

        # The interaction was deferred-acked within the window.
        assert http.responded == [("i-1", "tok-1")]

        # Replying to the interaction user goes to the @original webhook.
        await adapter.send_message("user-2", "the answer")
        assert http.edited == [("app-1", "tok-1", "the answer")]

        # Replying to a normal user goes to their channel over REST.
        await adapter.send_message("user-1", "plain reply")
        assert http.sent[-1] == ("ch-1", "plain reply")

    asyncio.run(scenario())


def test_discord_adapter_missing_token_fails_fast():
    adapter = DiscordAdapter({"bot_token": ""}, on_message=_Recorder())

    async def scenario() -> None:
        with pytest.raises(DiscordError):
            await adapter.start()
        assert adapter.status.error

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Slack — fake API + scripted websocket
# --------------------------------------------------------------------------- #


class _FakeSlackApi:
    def __init__(self, socket_url: str = "ws://slack.test/socket") -> None:
        self.socket_url = socket_url
        self.posted: list[tuple[str, str]] = []
        self.responses: list[tuple[str, str]] = []

    def connections_open(self) -> dict[str, Any]:
        return {"ok": True, "url": self.socket_url}

    def post_message(self, channel: str, text: str) -> dict[str, Any]:
        self.posted.append((channel, text))
        return {"ok": True}

    def post_response(self, response_url: str, text: str) -> dict[str, Any]:
        self.responses.append((response_url, text))
        return {"ok": True}


def test_slack_adapter_acks_envelopes_and_routes_messages():
    api = _FakeSlackApi()
    recorder = _Recorder()
    envelopes = [
        {  # events_api message
            "type": "events_api",
            "envelope_id": "e-1",
            "payload": {
                "event": {
                    "type": "message",
                    "user": "U1",
                    "channel": "C1",
                    "ts": "1700000000.000001",
                    "text": "slack hello",
                }
            },
        },
        {  # slash command
            "type": "slash_commands",
            "envelope_id": "e-2",
            "payload": {
                "user_id": "U2",
                "channel_id": "C2",
                "text": "slack command",
                "response_url": "https://hooks.slack.com/x",
            },
        },
        {  # an unknown envelope type still gets acked
            "type": "interactive",
            "envelope_id": "e-3",
            "payload": {},
        },
    ]

    class _FakeWs:
        def __init__(self) -> None:
            self.queue = asyncio.Queue()
            self.acks: list[dict[str, Any]] = []

        async def send_json(self, payload: dict[str, Any]) -> None:
            self.acks.append(payload)

        def __aiter__(self):
            return self

        async def __anext__(self) -> str:
            item = await self.queue.get()
            if item is None:
                raise StopAsyncIteration
            return item

        async def close(self) -> None:
            await self.queue.put(None)

    ws = _FakeWs()
    for envelope in envelopes:
        ws.queue.put_nowait(json.dumps(envelope))

    async def ws_connect(url: str):
        assert url == "ws://slack.test/socket"
        return ws

    adapter = SlackAdapter(
        {"app_token": "xapp-1", "bot_token": "xoxb-1"},
        on_message=recorder,
        api=api,
        ws_connect=ws_connect,
    )

    async def scenario() -> None:
        await adapter.start()
        for _ in range(100):
            if len(recorder.messages) >= 2:
                break
            await asyncio.sleep(0.02)
        await adapter.stop()

        assert len(recorder.messages) == 2
        assert recorder.messages[0].platform_user_id == "U1"
        assert recorder.messages[0].text == "slack hello"
        assert recorder.messages[1].text == "slack command"
        # Every envelope (including the unknown one) was acked.
        assert [ack["envelope_id"] for ack in ws.acks] == ["e-1", "e-2", "e-3"]

        # The command reply goes to its response_url...
        await adapter.send_message("U2", "command answer")
        assert api.responses == [("https://hooks.slack.com/x", "command answer")]
        # ...and a chat reply goes through chat.postMessage.
        await adapter.send_message("U1", "chat answer")
        assert api.posted == [("C1", "chat answer")]

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# WhatsApp — real local webhook server + fake API
# --------------------------------------------------------------------------- #


class _FakeWhatsAppApi:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.downloads: list[str] = []

    def send_text(self, recipient: str, text: str) -> dict[str, Any]:
        self.sent.append((recipient, text))
        return {"messaging_product": "whatsapp"}

    def download_media(self, media_id: str) -> bytes:
        self.downloads.append(media_id)
        return b"\x89PNG-fake"


def test_whatsapp_webhook_verifies_sends_and_ingests():
    api = _FakeWhatsAppApi()
    recorder = _Recorder()
    adapter = WhatsAppAdapter(
        {
            "access_token": "tok",
            "phone_number_id": "12345",
            "verify_token": "shared",
            "port": 0,
        },
        on_message=recorder,
        api=api,
    )

    async def scenario() -> None:
        await adapter.start()
        port = adapter._server.server_address[1]  # type: ignore[union-attr]
        assert adapter.status.connected

        # GET verification: right token gets the challenge, wrong token a 403.
        with urllib.request.urlopen(  # nosec B310
            f"http://127.0.0.1:{port}/webhook?hub.mode=subscribe"
            "&hub.verify_token=shared&hub.challenge=ch-42",
            timeout=5,
        ) as response:
            assert response.status == 200
            assert response.read() == b"ch-42"
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(  # nosec B310
                f"http://127.0.0.1:{port}/webhook?hub.mode=subscribe"
                "&hub.verify_token=wrong&hub.challenge=x",
                timeout=5,
            )
        assert exc.value.code == 403

        # POST a text message and an image message.
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "+15551234567",
                                        "id": "wamid.1",
                                        "type": "text",
                                        "text": {"body": "whatsapp hello"},
                                    },
                                    {
                                        "from": "+15551234567",
                                        "id": "wamid.2",
                                        "type": "image",
                                        "image": {
                                            "id": "media-1",
                                            "mime_type": "image/png",
                                        },
                                        "caption": "a picture",
                                    },
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        request = urllib.request.Request(  # nosec B310
            f"http://127.0.0.1:{port}/webhook",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310
            assert response.status == 200
            assert response.read() == b"EVENT_RECEIVED"

        for _ in range(200):
            if len(recorder.messages) >= 2:
                break
            await asyncio.sleep(0.02)
        assert len(recorder.messages) == 2
        assert recorder.messages[0].text == "whatsapp hello"
        assert recorder.messages[0].platform_user_id == "+15551234567"
        image = recorder.messages[1]
        assert image.text == "a picture"
        assert api.downloads == ["media-1"]
        assert image.attachments[0].data == b"\x89PNG-fake"

        await adapter.send_message("+15551234567", "answer")
        assert api.sent == [("+15551234567", "answer")]

        await adapter.stop()

    asyncio.run(scenario())


def test_whatsapp_hmac_signature_validation():
    import hashlib
    import hmac as hmac_module

    adapter = WhatsAppAdapter(
        {"app_secret": "s3cret", "access_token": "t", "phone_number_id": "1"},
        on_message=_Recorder(),
        api=_FakeWhatsAppApi(),
    )
    body = b'{"entry": []}'
    good = "sha256=" + hmac_module.new(
        b"s3cret", body, hashlib.sha256
    ).hexdigest()
    assert adapter.verify_signature(body, good) is True
    assert adapter.verify_signature(body, "sha256=deadbeef") is False
    # No secret configured → validation passes through (disabled).
    open_adapter = WhatsAppAdapter(
        {"access_token": "t", "phone_number_id": "1"},
        on_message=_Recorder(),
        api=_FakeWhatsAppApi(),
    )
    assert open_adapter.verify_signature(body, "") is True


def test_whatsapp_extract_messages_walks_the_webhook_shape():
    payload = {
        "entry": [{"changes": [{"value": {"messages": [{"id": "1"}, {"id": "2"}]}}]}]
    }
    assert _extract_messages(payload) == [{"id": "1"}, {"id": "2"}]
    assert _extract_messages({}) == []


# --------------------------------------------------------------------------- #
# Signal — fake CLI seam
# --------------------------------------------------------------------------- #


class _FakeSignalCli:
    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.sent: list[tuple[str, str]] = []
        self.resolved = 0

    def resolve(self) -> str:
        self.resolved += 1
        return "/usr/bin/signal-cli"

    def receive_json(self, timeout: int = 25) -> str:
        del timeout
        raw, self.raw = self.raw, ""
        return raw

    def send(self, recipient: str, text: str) -> None:
        self.sent.append((recipient, text))


def test_signal_adapter_receives_and_sends_without_logging_content():
    cli = _FakeSignalCli(
        json.dumps(
            {
                "envelope": {
                    "source": "+12025550123",
                    "timestamp": 1700000000,
                    "dataMessage": {"message": "secret signal text"},
                }
            }
        )
    )
    recorder = _Recorder()
    adapter = SignalAdapter(
        {"signal_cli_path": "signal-cli", "account": "+1"},
        on_message=recorder,
        cli=cli,
    )

    async def scenario() -> None:
        await adapter.start()
        for _ in range(100):
            if recorder.messages:
                break
            await asyncio.sleep(0.02)
        await adapter.stop()
        message = recorder.messages[0]
        assert message.platform == "signal"
        assert adapter.privacy == "e2e"
        assert message.text == "secret signal text"
        assert message.platform_user_id == "+12025550123"
        await adapter.send_message("+12025550123", "reply text")
        assert cli.sent == [("+12025550123", "reply text")]
        assert cli.resolved >= 1  # binary verified at startup

    asyncio.run(scenario())


def test_signal_cli_parsing_helpers():
    envelopes = _parse_envelopes('{"envelope": {"a": 1}} {"envelope": {"a": 2}}')
    assert len(envelopes) == 2
    assert _parse_envelopes("[{\"envelope\": {\"a\": 1}}]")[0]["envelope"]["a"] == 1
    assert _parse_envelopes("") == []
    assert _message_text({"dataMessage": {"message": "hi"}}) == "hi"
    assert _message_text({"dataMessage": {}}) == ""
    assert _message_source({"source": "+1"}) == "+1"


def test_signal_missing_binary_fails_fast():
    import os

    directory = tempfile.mkdtemp()
    missing = os.path.join(directory, "no-such-binary")

    async def scenario() -> None:
        adapter = SignalAdapter(
            {"signal_cli_path": missing, "account": "+1"},
            on_message=_Recorder(),
        )
        with pytest.raises(SignalCliError):
            await adapter.start()
        assert adapter.status.error

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Email — fake IMAP/SMTP seams
# --------------------------------------------------------------------------- #


class _FakeImap(ImapClient):
    def __init__(self, messages: list[email.message.EmailMessage]) -> None:
        self._fake_messages = list(messages)
        self._seen: list[int] = []
        self.idle_calls = 0

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def supports_idle(self) -> bool:
        return True

    def idle_once(self, timeout: int) -> bool:
        del timeout
        self.idle_calls += 1
        return bool(self.search_unseen())

    def search_unseen(self) -> list[int]:
        # Drain semantics: once a row is marked seen it disappears.
        return [
            number
            for number in range(1, len(self._fake_messages) + 1)
            if number not in self._seen
        ]

    def fetch_rfc822(self, number: int) -> bytes:
        return self._fake_messages[number - 1].as_bytes()

    def mark_seen(self, number: int) -> None:
        self._seen.append(number)


class _FakeSmtp(SmtpClient):
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send(self, from_addr: str, to_addr: str, subject: str, body: str, **headers: Any) -> None:
        self.sent.append(
            {"from": from_addr, "to": to_addr, "subject": subject, "body": body, **headers}
        )


def _email_message(
    sender: str, subject: str, body: str, html: bool = False
) -> email.message.EmailMessage:
    message = email.message.EmailMessage()
    message["From"] = sender
    message["To"] = "dream@example.com"
    message["Subject"] = subject
    message["Message-ID"] = f"<{subject.replace(' ', '')}@mail.example>"
    if html:
        message.set_content(body, subtype="html")
    else:
        message.set_content(body)
    return message


def test_email_adapter_idle_receive_threading_and_loop_guard():
    inbox = [
        _email_message("user@example.com", "First", "email hello"),
        _email_message("user@example.com", "Second", "<html><p>HTML hello</p></html>", html=True),
        _email_message("dream@example.com", "Own", "sent by ourselves"),
    ]
    imap = _FakeImap(inbox)
    smtp = _FakeSmtp()
    recorder = _Recorder()
    adapter = EmailAdapter(
        {
            "imap_host": "imap.example.com",
            "imap_user": "dream@example.com",
            "imap_password": "pw",
            "smtp_host": "smtp.example.com",
            "poll_seconds": 1,
        },
        on_message=recorder,
        imap=imap,
        smtp=smtp,
    )

    async def scenario() -> None:
        await adapter.start()
        for _ in range(100):
            if len(recorder.messages) >= 2:
                break
            await asyncio.sleep(0.02)
        await adapter.stop()

        assert imap.idle_calls >= 1  # IDLE path was taken
        assert len(recorder.messages) == 2  # our own mail was skipped
        assert recorder.messages[0].text == "email hello"
        assert recorder.messages[0].platform_user_id == "user@example.com"
        assert recorder.messages[1].text == "HTML hello"
        assert imap._seen == [1, 2, 3]  # all fetched rows marked seen

        # Reply carries In-Reply-To/References threading headers.
        await adapter.send_message("user@example.com", "threaded reply")
        sent = smtp.sent[-1]
        assert sent["to"] == "user@example.com"
        assert sent["in_reply_to"].startswith("<")
        assert sent["references"] == sent["in_reply_to"]

    asyncio.run(scenario())


def test_email_adapter_uses_poll_fallback_without_idle():
    imap = _FakeImap([_email_message("user@example.com", "Poll", "polled hello")])
    imap.supports_idle = lambda: False  # type: ignore[method-assign]
    recorder = _Recorder()
    adapter = EmailAdapter(
        {
            "imap_host": "h",
            "imap_user": "dream@example.com",
            "imap_password": "pw",
            "smtp_host": "s",
            "use_idle": False,
            "poll_seconds": 0.1,
        },
        on_message=recorder,
        imap=imap,
        smtp=_FakeSmtp(),
    )

    async def scenario() -> None:
        await adapter.start()
        for _ in range(100):
            if recorder.messages:
                break
            await asyncio.sleep(0.02)
        await adapter.stop()
        assert imap.idle_calls == 0
        assert recorder.messages[0].text == "polled hello"

    asyncio.run(scenario())


def test_email_adapter_missing_password_fails_fast():
    adapter = EmailAdapter(
        {"imap_host": "h", "imap_user": "u", "smtp_host": "s"},
        on_message=_Recorder(),
    )

    async def scenario() -> None:
        with pytest.raises(EmailError):
            await adapter.start()

    asyncio.run(scenario())


def test_html_to_text_strips_markup():
    assert html_to_text("<p>Hello <b>Dream</b></p><div>next</div>") == "Hello Dream\nnext"
    assert html_to_text("plain") == "plain"


def test_telegram_adapter_ignores_group_messages_even_from_a_linked_user():
    recorder = _Recorder()
    adapter = TelegramAdapter(
        {"token": "123456:abcdefghijklmnopqrstuvwx"},
        on_message=recorder,
        transport=_FakeTelegramTransport([]),
    )
    group_update = {
        "update_id": 30,
        "message": {
            "message_id": 7,
            "chat": {"id": -1001, "type": "supergroup"},
            "from": {"id": 42, "is_bot": False},
            "text": "/link 123456",
        },
    }

    _run(adapter._handle_update(group_update))

    assert recorder.messages == []


def test_telegram_adapter_retries_failed_handler_before_advancing_offset():
    attempts = 0
    delivered: list[str] = []

    async def flaky_handler(message: IncomingMessage) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary route failure")
        delivered.append(message.text)

    adapter = TelegramAdapter(
        {"token": "123456:abcdefghijklmnopqrstuvwx"},
        on_message=flaky_handler,
        transport=_FakeTelegramTransport([]),
    )
    update = {
        "update_id": 41,
        "message": {
            "message_id": 8,
            "chat": {"id": 99, "type": "private"},
            "from": {"id": 42, "is_bot": False},
            "text": "retry safely",
        },
    }

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="temporary route failure"):
            await adapter._process_updates([update])
        assert adapter._offset == 0

        await adapter._process_updates([update])
        assert adapter._offset == 42

    _run(scenario())
    assert attempts == 2
    assert delivered == ["retry safely"]
