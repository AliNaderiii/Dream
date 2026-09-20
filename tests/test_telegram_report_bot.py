"""Tests for the Telegram report bot pipeline (``dream.reporting.telegram_bot``).

All Telegram I/O is faked at the transport seam — no test touches the network.
Photo bytes are binary (the OCR engine's simulated Persian-invoice path) and
voice bytes go through the speech engine's simulated transcript, both of which
are the core's honest local pipelines.
"""

from __future__ import annotations

import time

import pytest

from dream.reporting.telegram_bot import (
    ReportBotError,
    ReportBotService,
    ReportBotTransport,
    TelegramReportBot,
)

VALID_TOKEN = "123456789:AAFakeDreamBotTokenForTests_-abc123XYZ"
OTHER_TOKEN = "987654321:AAAnotherDreamBotTokenForTests_-xyz789UVW"


class FakeTransport:
    """Records every outbound call; hands back scripted updates and files."""

    def __init__(self, updates: list[dict] | None = None) -> None:
        self.pending = list(updates or [])
        self.sent_messages: list[tuple[int, str]] = []
        self.sent_documents: list[tuple[int, str, bytes, str]] = []
        self.actions: list[tuple[int, str]] = []
        self.downloads: list[str] = []
        self.fail_download_for: set[str] = set()
        self.files: dict[str, bytes] = {
            "photo-1": b"\x89PNG\r\n\x1a\n fake image bytes",
            "voice-1": b"OggS fake opus bytes",
        }
        self.paths = {
            "photo-1": "photos/photo_1.jpg",
            "voice-1": "voice/file_1.oga",
        }

    def get_updates(self, offset: int) -> list[dict]:
        if self.pending:
            return [self.pending.pop(0)]
        return []

    def send_message(self, chat_id: int, text: str) -> None:
        self.sent_messages.append((chat_id, text))

    def send_chat_action(self, chat_id: int, action: str) -> None:
        self.actions.append((chat_id, action))

    def get_file_path(self, file_id: str) -> str:
        return self.paths[file_id]

    def download_file(self, file_path: str) -> bytes:
        file_id = next((k for k, v in self.paths.items() if v == file_path), file_path)
        if file_id in self.fail_download_for or file_id not in self.files:
            raise ReportBotError(
                "Telegram getFile failed: token 111111111:AAAleakSecretTokenABCDEF leaked"
            )
        self.downloads.append(file_id)
        return self.files[file_id]

    def send_document(self, chat_id: int, filename: str, data: bytes, caption: str) -> None:
        self.sent_documents.append((chat_id, filename, data, caption))


def make_bot(transport: FakeTransport) -> TelegramReportBot:
    return TelegramReportBot(VALID_TOKEN, transport=transport, poll_interval=0.01)


def photo_update(caption: str | None = None) -> dict:
    message: dict = {
        "chat": {"id": 42},
        "photo": [
            {"file_id": "photo-1", "file_size": 100, "file_path": "photos/photo_1.jpg"},
            {"file_id": "photo-1", "file_size": 900, "file_path": "photos/photo_1.jpg"},
        ],
    }
    if caption:
        message["caption"] = caption
    return {"update_id": 1, "message": message}


def voice_update() -> dict:
    return {
        "update_id": 2,
        "message": {
            "chat": {"id": 42},
            "voice": {"file_id": "voice-1", "duration": 7, "file_size": 4800},
        },
    }


def text_update(text: str) -> dict:
    return {"update_id": 3, "message": {"chat": {"id": 42}, "text": text}}


class TestTransport:
    def test_rejects_malformed_token(self) -> None:
        with pytest.raises(ReportBotError, match="malformed"):
            ReportBotTransport("not-a-token")

    def test_rejects_empty_token(self) -> None:
        with pytest.raises(ReportBotError, match="missing or malformed"):
            ReportBotTransport("")


class TestPipeline:
    def test_photo_update_produces_persian_pdf_document(self) -> None:
        transport = FakeTransport([photo_update(caption="فاکتور خرید این هفته")])
        bot = make_bot(transport)
        bot.handle_update(transport.pending.pop(0))
        assert len(transport.sent_documents) == 1
        chat_id, filename, data, caption = transport.sent_documents[0]
        assert chat_id == 42
        assert filename == "dream-report.pdf"
        assert data[:5] == b"%PDF-"
        assert "صفحه" in caption
        assert (42, "typing") in transport.actions
        events = bot.snapshot()["events"]
        assert events[-1]["kind"] == "photo_report"
        assert events[-1]["detail"]["pdf_pages"] >= 1
        assert events[-1]["detail"]["ocr_chars"] > 0

    def test_voice_update_transcribes_into_pdf(self) -> None:
        transport = FakeTransport([voice_update()])
        bot = make_bot(transport)
        bot.handle_update(transport.pending.pop(0))
        assert len(transport.sent_documents) == 1
        _, _, data, _ = transport.sent_documents[0]
        assert data[:5] == b"%PDF-"
        events = bot.snapshot()["events"]
        assert events[-1]["kind"] == "voice_report"
        assert events[-1]["detail"]["transcript_chars"] > 0
        assert events[-1]["detail"]["duration_s"] > 0

    def test_text_update_becomes_structured_pdf_report(self) -> None:
        transport = FakeTransport([text_update("گزارش جلسه امروز: فروش ۱۲ درصد رشد داشت.")])
        bot = make_bot(transport)
        bot.handle_update(transport.pending.pop(0))
        assert len(transport.sent_documents) == 1
        _, _, data, _ = transport.sent_documents[0]
        assert data[:5] == b"%PDF-"
        events = bot.snapshot()["events"]
        assert events[-1]["kind"] == "text_report"
        assert events[-1]["detail"]["text_chars"] > 20

    def test_start_command_replies_with_help_and_no_document(self) -> None:
        transport = FakeTransport([text_update("/start")])
        bot = make_bot(transport)
        bot.handle_update(transport.pending.pop(0))
        assert len(transport.sent_messages) == 1
        assert "بات گزارش‌ساز دریم" in transport.sent_messages[0][1]
        assert transport.sent_documents == []
        assert bot.snapshot()["events"][-1]["kind"] == "help_sent"

    def test_failed_download_is_redacted_and_does_not_crash(self) -> None:
        transport = FakeTransport([photo_update()])
        transport.fail_download_for.add("photo-1")
        bot = make_bot(transport)
        bot.handle_update(transport.pending.pop(0))
        assert transport.sent_documents == []
        events = bot.snapshot()["events"]
        assert events[-1]["kind"] == "error"
        message = events[-1]["detail"]["message"]
        assert "111111111:AAAleakSecretTokenABCDEF" not in message
        assert "<redacted-token>" in message
        # The loop must survive: the next update still processes.
        transport.pending.append(text_update("بعد از خطا دوباره تلاش کن"))
        bot.handle_update(transport.pending.pop(0))
        assert len(transport.sent_documents) == 1


class TestService:
    def test_start_rejects_malformed_token(self) -> None:
        service = ReportBotService()
        with pytest.raises(ReportBotError, match="missing or malformed"):
            service.start("bad-token")

    def test_start_stop_roundtrip_processes_updates(self) -> None:
        service = ReportBotService()
        transport_holder: dict[str, FakeTransport] = {}

        def factory(token: str, base: str | None) -> FakeTransport:
            transport = FakeTransport([text_update("سلام گزارش بده")])
            transport_holder["t"] = transport
            return transport

        service.set_transport_factory(factory)
        status = service.start(VALID_TOKEN)
        try:
            assert status["running"] is True
            assert status["token_fingerprint"] == f"…{VALID_TOKEN[-4:]}"
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                events = service.status()["events"]
                if any(e["kind"] == "text_report" for e in events):
                    break
                time.sleep(0.05)
            final = service.status()
            assert any(e["kind"] == "text_report" for e in final["events"])
            assert final["updates_processed"] >= 1
            assert len(transport_holder["t"].sent_documents) == 1
            assert any(e["kind"] == "started" for e in final["events"])
        finally:
            stopped = service.stop()
        assert stopped["running"] is False
        assert any(e["kind"] == "stopped" for e in stopped["events"])

    def test_second_start_with_other_token_conflicts(self) -> None:
        service = ReportBotService()
        service.set_transport_factory(lambda token, base: FakeTransport())
        service.start(VALID_TOKEN)
        try:
            with pytest.raises(ReportBotError, match="already running"):
                service.start(OTHER_TOKEN)
            # Same token is idempotent.
            assert service.start(VALID_TOKEN)["running"] is True
        finally:
            service.stop()

    def test_stop_when_not_running_is_idempotent(self) -> None:
        service = ReportBotService()
        assert service.stop()["running"] is False

    def test_status_when_stopped_has_empty_state(self) -> None:
        service = ReportBotService()
        status = service.status()
        assert status["running"] is False
        assert status["events"] == []
        assert status["token_fingerprint"] is None
