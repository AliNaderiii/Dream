"""Telegram report bot: voice/photo messages → OCR/speech → Persian PDF.

A long-polling Telegram front end dedicated to the report pipeline: every
photo is OCR-ed, every voice note is transcribed, every text becomes a
structured report — rendered by the local Persian PDF engine (fpdf2 +
HarfBuzz + Vazirmatn) and sent straight back into the chat as a document.

Everything runs on this machine; no message content leaves it except the
Telegram API calls themselves. Token validation, redaction, and the
``TELEGRAM_API_BASE_URL`` relay override are reused from ``dream.telegram``
so both front ends recognise identical token shapes and never leak them.
"""

from __future__ import annotations

import json
import logging
import secrets
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dream.ocr.engine import OCREngine
from dream.ocr.types import DocumentType
from dream.reporting.pdf import ReportError, build_report_pdf
from dream.speech.engine import SpeechEngine
from dream.speech.types import STTRequest
from dream.telegram import (
    _TOKEN_FULL_RE,
    _resolve_api_base_url,
    redact_token,
)

logger = logging.getLogger(__name__)

__all__ = [
    "MAX_EVENTS",
    "ReportBotError",
    "ReportBotTransport",
    "TelegramReportBot",
    "ReportBotService",
    "get_report_bot_service",
    "reset_report_bot_service",
]

POLL_TIMEOUT = 25
HTTP_TIMEOUT = 35
BACKOFF_INITIAL = 1.0
BACKOFF_MAX = 30.0
MAX_EVENTS = 50
#: Telegram bot API file download ceiling (20 MB) — guards memory.
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
MAX_PARAGRAPH_CHARS = 4_000
MAX_CELL_CHARS = 500
PDF_FILENAME = "dream-report.pdf"

HELP_TEXT = (
    "سلام! من بات گزارش‌ساز دریم هستم 🌙\n\n"
    "📸 عکس سند بفرستید → OCR فارسی و فیلدها استخراج می‌شود\n"
    "🎙 پیام صوتی بفرستید → رونویسی و گزارش صوتی\n"
    "✍️ متن بفرستید → گزارش متنی ساخت‌یافته\n\n"
    "خروجی هر سه مسیر، یک PDF فارسی با حروف متصل است که همین‌جا در چت تحویل "
    "داده می‌شود. همه پردازش‌ها به‌صورت محلی روی دستگاه صاحب بات انجام "
    "می‌شود؛ هیچ داده‌ای جای دیگری ذخیره نمی‌شود."
)

CAPTION_DOC = "📄 گزارش PDF فارسی — ساخته‌شده به‌صورت محلی توسط دریم"


class ReportBotError(RuntimeError):
    """A safe-to-display report-bot failure (token already redacted)."""


class ReportBotTransport:
    """Standard-library Bot API client for the report pipeline.

    The injectable seam: unit tests substitute a fake with the same methods,
    so no test ever touches the network.
    """

    def __init__(self, token: str, api_base_url: str | None = None) -> None:
        if not token or _TOKEN_FULL_RE.fullmatch(token) is None:
            raise ReportBotError("telegram token is missing or malformed")
        self._token = token
        base = _resolve_api_base_url(api_base_url)
        self._base_url = f"{base}/bot{token}"
        self._file_base_url = f"{base}/file/bot{token}"

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self._base_url}/{method}",
            data=urlencode(payload).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        return self._read_json(request, method)

    def _call_multipart(
        self,
        method: str,
        fields: dict[str, str],
        file_field: str,
        filename: str,
        data: bytes,
        mime_type: str,
    ) -> dict[str, Any]:
        boundary = f"----dreambot{secrets.token_hex(12)}"
        parts: list[bytes] = []
        for name, value in fields.items():
            parts.append(
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                    f"{value}\r\n"
                ).encode()
            )
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{filename}"\r\n'
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode()
        )
        parts.append(data)
        parts.append(f"\r\n--{boundary}--\r\n".encode())
        request = Request(
            f"{self._base_url}/{method}",
            data=b"".join(parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        return self._read_json(request, method)

    def _read_json(self, request: Request, method: str) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=HTTP_TIMEOUT) as response:  # nosec B310
                decoded = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ReportBotError(f"Telegram {method} failed: {redact_token(exc)}") from None
        if not isinstance(decoded, dict) or decoded.get("ok") is not True:
            description = redact_token(
                decoded.get("description", "request rejected") if isinstance(decoded, dict)
                else "request rejected"
            )
            raise ReportBotError(f"Telegram {method} rejected the request: {description}")
        return decoded

    def get_updates(self, offset: int) -> list[dict[str, Any]]:
        response = self._call(
            "getUpdates",
            {"offset": offset, "timeout": POLL_TIMEOUT, "allowed_updates": json.dumps(["message"])},
        )
        updates = response.get("result", [])
        return updates if isinstance(updates, list) else []

    def send_message(self, chat_id: int, text: str) -> None:
        self._call("sendMessage", {"chat_id": chat_id, "text": text})

    def send_chat_action(self, chat_id: int, action: str) -> None:
        self._call("sendChatAction", {"chat_id": chat_id, "action": action})

    def get_file_path(self, file_id: str) -> str:
        response = self._call("getFile", {"file_id": file_id})
        file_path = response.get("result", {}).get("file_path")
        if not isinstance(file_path, str) or not file_path:
            raise ReportBotError("Telegram getFile returned no file_path")
        return file_path

    def download_file(self, file_path: str) -> bytes:
        request = Request(f"{self._file_base_url}/{file_path}", method="GET")
        try:
            with urlopen(request, timeout=HTTP_TIMEOUT) as response:  # nosec B310
                data = response.read(MAX_DOWNLOAD_BYTES + 1)
        except Exception as exc:
            raise ReportBotError(f"Telegram file download failed: {redact_token(exc)}") from None
        if len(data) > MAX_DOWNLOAD_BYTES:
            raise ReportBotError("file exceeds the 20 MB bot API download limit")
        return data

    def send_document(self, chat_id: int, filename: str, data: bytes, caption: str) -> None:
        self._call_multipart(
            "sendDocument",
            {"chat_id": str(chat_id), "caption": caption},
            "document",
            filename,
            data,
            "application/pdf",
        )


class TelegramReportBot:
    """One poller instance: routes updates through the report pipeline."""

    def __init__(
        self,
        token: str,
        api_base_url: str | None = None,
        transport: ReportBotTransport | None = None,
        poll_interval: float = 0.2,
    ) -> None:
        self._transport = (
            transport if transport is not None else ReportBotTransport(token, api_base_url)
        )
        self._ocr = OCREngine()
        self._speech = SpeechEngine()
        self._poll_interval = poll_interval
        self._lock = threading.Lock()
        self._events: list[dict[str, Any]] = []
        self._updates_processed = 0
        self._connected = False
        self._last_error: str | None = None

    # ------------------------------------------------------------------ events
    def _event(self, kind: str, chat_id: int | None = None, **detail: Any) -> None:
        entry = {
            "ts": round(time.time(), 3),
            "kind": kind,
            "chat_id": chat_id,
            "detail": detail,
        }
        with self._lock:
            self._events.append(entry)
            if len(self._events) > MAX_EVENTS:
                del self._events[: len(self._events) - MAX_EVENTS]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            events = list(self._events)
            connected = self._connected
            updates = self._updates_processed
            last_error = self._last_error
        return {
            "connected": connected,
            "updates_processed": updates,
            "last_error": last_error,
            "events": events,
        }

    # ------------------------------------------------------------------- loop
    def run(self, stop_event: threading.Event) -> None:
        """Long-poll until *stop_event* is set. Never raises."""
        self._event("started")
        backoff = BACKOFF_INITIAL
        offset = 0
        while not stop_event.is_set():
            try:
                updates = self._transport.get_updates(offset)
                backoff = BACKOFF_INITIAL
                with self._lock:
                    self._connected = True
                    self._last_error = None
                for update in updates:
                    if stop_event.is_set():
                        break
                    offset = max(offset, int(update.get("update_id", 0)) + 1)
                    self.handle_update(update)
                    with self._lock:
                        self._updates_processed += 1
            except ReportBotError as exc:
                with self._lock:
                    self._connected = False
                    self._last_error = redact_token(str(exc))
                self._event("poll_error", message=self._last_error)
                if stop_event.wait(min(backoff, BACKOFF_MAX)):
                    break
                backoff = min(backoff * 2, BACKOFF_MAX)
                continue
            except Exception as exc:  # pragma: no cover - defensive hardening
                with self._lock:
                    self._connected = False
                    self._last_error = redact_token(f"unexpected poller failure: {exc}")
                self._event("poll_error", message=self._last_error)
                if stop_event.wait(min(backoff, BACKOFF_MAX)):
                    break
                backoff = min(backoff * 2, BACKOFF_MAX)
                continue
            if stop_event.wait(self._poll_interval):
                break

    # ---------------------------------------------------------------- routing
    def handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat_id = message.get("chat", {}).get("id")
        if not isinstance(chat_id, int):
            return
        try:
            if isinstance(message.get("photo"), list) and message["photo"]:
                self._handle_photo(chat_id, message)
            elif isinstance(message.get("voice"), dict):
                self._handle_voice(chat_id, message)
            else:
                text = message.get("text") or message.get("caption") or ""
                if isinstance(text, str) and text.strip():
                    self._handle_text(chat_id, text)
        except ReportBotError as exc:
            self._event("error", chat_id, message=redact_token(str(exc)))
            self._safe_reply(chat_id, f"⚠ پردازش این گزارش ناموفق بود: {redact_token(str(exc))}")
        except Exception as exc:  # pragma: no cover - defensive hardening
            self._event("error", chat_id, message=redact_token(f"unexpected failure: {exc}"))
            self._safe_reply(chat_id, "⚠ خطای غیرمنتظره در پردازش گزارش. لطفاً دوباره تلاش کنید.")

    def _safe_reply(self, chat_id: int, text: str) -> None:
        try:
            self._transport.send_message(chat_id, text)
        except ReportBotError as exc:
            self._event("error", chat_id, message=redact_token(str(exc)))

    def _handle_photo(self, chat_id: int, message: dict[str, Any]) -> None:
        sizes = message.get("photo") or []
        largest = max(sizes, key=lambda s: s.get("file_size", 0) or 0)
        file_id = largest.get("file_id")
        if not isinstance(file_id, str) or not file_id:
            raise ReportBotError("photo update carried no file_id")
        self._transport.send_chat_action(chat_id, "typing")
        data = self._transport.download_file(self._transport.get_file_path(file_id))
        suffix = Path(largest.get("file_path", "")).suffix or ".jpg"
        caption = message.get("caption")
        with tempfile.TemporaryDirectory(prefix="dream-reportbot-") as tmp:
            image_path = Path(tmp) / f"photo{suffix}"
            image_path.write_bytes(data)
            ocr = self._ocr.extract_document(str(image_path), DocumentType.GENERAL)
        report = self._build_ocr_report(ocr, caption if isinstance(caption, str) else None)
        self._send_report(chat_id, report, "photo_report", ocr_chars=len(ocr.cleaned_text))

    def _handle_voice(self, chat_id: int, message: dict[str, Any]) -> None:
        voice = message.get("voice") or {}
        file_id = voice.get("file_id")
        if not isinstance(file_id, str) or not file_id:
            raise ReportBotError("voice update carried no file_id")
        self._transport.send_chat_action(chat_id, "typing")
        data = self._transport.download_file(self._transport.get_file_path(file_id))
        with tempfile.TemporaryDirectory(prefix="dream-reportbot-") as tmp:
            audio_path = Path(tmp) / "voice.oga"
            audio_path.write_bytes(data)
            stt = self._speech.transcribe(STTRequest(audio_path=str(audio_path), language="fa"))
        report = self._build_voice_report(stt.text, stt.duration)
        self._send_report(
            chat_id,
            report,
            "voice_report",
            transcript_chars=len(stt.text),
            duration_s=round(stt.duration, 2),
        )

    def _handle_text(self, chat_id: int, text: str) -> None:
        stripped = text.strip()
        if stripped in {"/start", "/help", "شروع"}:
            self._transport.send_message(chat_id, HELP_TEXT)
            self._event("help_sent", chat_id)
            return
        self._transport.send_chat_action(chat_id, "typing")
        report = self._build_text_report(stripped)
        self._send_report(chat_id, report, "text_report", text_chars=len(stripped))

    # --------------------------------------------------------------- pipeline
    def _build_ocr_report(self, ocr: Any, caption: str | None) -> dict[str, Any]:
        body = ocr.cleaned_text.strip() or "متنی از این تصویر استخراج نشد."
        paragraphs = [body[:MAX_PARAGRAPH_CHARS]]
        if caption and caption.strip():
            paragraphs.append(f"توضیح ارسال‌کننده: {caption.strip()[:MAX_PARAGRAPH_CHARS]}")
        fields = ocr.extracted_fields or {}
        section: dict[str, Any] = {
            "heading": "متن استخراج‌شده (OCR)",
            "paragraphs": paragraphs,
            "kpis": [
                {"label": "زبان سند", "value": "فارسی" if ocr.language == "fa" else "لاتین"},
                {"label": "بلوک‌های متن", "value": str(len(ocr.blocks))},
                {"label": "فیلدهای شناسایی‌شده", "value": str(len(fields))},
            ],
        }
        if fields:
            section["table"] = {
                "columns": ["فیلد", "مقدار"],
                "rows": [
                    [str(key)[:MAX_CELL_CHARS], str(value)[:MAX_CELL_CHARS]]
                    for key, value in list(fields.items())[:200]
                ],
            }
        return {
            "title": "گزارش سند تصویری — دریم",
            "subtitle": "استخراج‌شده با OCR محلی فارسی",
            "sections": [section],
        }

    def _build_voice_report(self, transcript: str, duration: float) -> dict[str, Any]:
        return {
            "title": "گزارش صوتی — دریم",
            "subtitle": "رونویسی خودکار پیام صوتی",
            "sections": [
                {
                    "heading": "رونویسی صوتی",
                    "paragraphs": [(transcript.strip() or "…")[:MAX_PARAGRAPH_CHARS]],
                    "kpis": [
                        {"label": "مدت پیام", "value": f"{duration:.0f} ثانیه"},
                    ],
                }
            ],
        }

    def _build_text_report(self, text: str) -> dict[str, Any]:
        return {
            "title": "گزارش متنی — دریم",
            "subtitle": "ساخت‌یافته از پیام کاربر",
            "sections": [
                {
                    "heading": "متن پیام",
                    "paragraphs": [text[:MAX_PARAGRAPH_CHARS]],
                }
            ],
        }

    def _send_report(
        self, chat_id: int, report: dict[str, Any], kind: str, **detail: Any
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="dream-reportbot-") as tmp:
            pdf_path = Path(tmp) / PDF_FILENAME
            try:
                built = build_report_pdf(report, str(pdf_path))
            except ReportError as exc:
                raise ReportBotError(f"invalid report model: {exc}") from None
            data = pdf_path.read_bytes()
        self._transport.send_document(
            chat_id,
            PDF_FILENAME,
            data,
            f"{CAPTION_DOC} · {built['pages']} صفحه",
        )
        self._event(
            kind,
            chat_id,
            pdf_pages=built.get("pages"),
            pdf_bytes=built.get("size_bytes"),
            **detail,
        )


class ReportBotService:
    """Thread-safe owner of the single running report bot."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None
        self._bot: TelegramReportBot | None = None
        self._started_at: float | None = None
        self._fingerprint: str | None = None
        self._transport_factory: Callable[[str, str | None], ReportBotTransport] | None = None

    def set_transport_factory(
        self, factory: Callable[[str, str | None], ReportBotTransport] | None
    ) -> None:
        """Test seam: inject a fake transport builder (None restores real)."""
        with self._lock:
            self._transport_factory = factory

    def start(self, token: str, api_base_url: str | None = None) -> dict[str, Any]:
        if not isinstance(token, str) or _TOKEN_FULL_RE.fullmatch(token.strip() or "") is None:
            raise ReportBotError("telegram token is missing or malformed")
        token = token.strip()
        # Never call status() while holding the lock — it acquires the same one.
        already_running_same = False
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                already_running_same = bool(self._fingerprint and token.endswith(self._fingerprint))
                if not already_running_same:
                    raise ReportBotError("a report bot is already running; stop it first")
            else:
                transport = (
                    self._transport_factory(token, api_base_url)
                    if self._transport_factory is not None
                    else ReportBotTransport(token, api_base_url)
                )
                bot = TelegramReportBot(token, api_base_url, transport=transport)
                stop_event = threading.Event()
                thread = threading.Thread(
                    target=bot.run,
                    args=(stop_event,),
                    name="dream-reportbot",
                    daemon=True,
                )
                self._bot = bot
                self._stop_event = stop_event
                self._thread = thread
                self._started_at = time.time()
                self._fingerprint = token[-4:]
                thread.start()
        if not already_running_same:
            logger.info("report bot started (token …%s)", self._fingerprint)
        return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            thread, stop_event = self._thread, self._stop_event
        if stop_event is not None:
            stop_event.set()
        if thread is not None:
            thread.join(timeout=HTTP_TIMEOUT + 5)
        with self._lock:
            self._thread = None
            self._stop_event = None
            started = self._started_at
            bot = self._bot
            self._bot = None
            self._started_at = None
            self._fingerprint = None
        if bot is not None:
            bot._event("stopped")
        logger.info("report bot stopped (ran %.0fs)", (time.time() - started) if started else 0)
        payload: dict[str, Any] = {
            "running": False,
            "started_at": None,
            "token_fingerprint": None,
        }
        if bot is not None:
            # Keep the final snapshot (with the stopped event) visible once more.
            payload.update(bot.snapshot())
        else:
            payload.update(
                {"connected": False, "updates_processed": 0, "last_error": None, "events": []}
            )
        return payload

    def status(self) -> dict[str, Any]:
        with self._lock:
            thread = self._thread
            bot = self._bot
            started_at = self._started_at
            fingerprint = self._fingerprint
        running = thread is not None and thread.is_alive()
        payload: dict[str, Any] = {
            "running": running,
            "started_at": started_at,
            "token_fingerprint": f"…{fingerprint}" if fingerprint else None,
        }
        if bot is not None:
            payload.update(bot.snapshot())
        else:
            payload.update(
                {
                    "connected": False,
                    "updates_processed": 0,
                    "last_error": None,
                    "events": [],
                }
            )
        return payload


_service: ReportBotService | None = None
_service_lock = threading.Lock()


def get_report_bot_service() -> ReportBotService:
    global _service
    with _service_lock:
        if _service is None:
            _service = ReportBotService()
        return _service


def reset_report_bot_service() -> None:
    """Test isolation: drop the singleton (stop any running bot first)."""
    global _service
    with _service_lock:
        if _service is not None:
            try:
                _service.stop()
            except Exception:  # pragma: no cover - best-effort teardown
                pass
        _service = None
