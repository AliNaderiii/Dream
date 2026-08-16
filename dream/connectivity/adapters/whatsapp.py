"""WhatsApp adapter: Cloud API webhook server plus outbound message API.

* the webhook is a standard-library ``ThreadingHTTPServer`` on a configured
  port: Meta's GET verification (``hub.verify_token``/``hub.challenge``) and
  POST message delivery, optionally HMAC-validated against the app secret;
* webhook deliveries are pushed onto the gateway loop thread-safely, so the
  HTTP handler never blocks;
* sends go through ``POST /{phone_number_id}/messages`` with the bearer token;
* media is downloaded in two steps: ``GET /{media_id}`` returns a URL, then
  the bytes are fetched from that URL.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from dream.connectivity.base import OnMessage, PlatformAdapter
from dream.connectivity.models import Attachment, IncomingMessage, utc_now

logger = logging.getLogger(__name__)

GRAPH_API_BASE_URL = "https://graph.facebook.com/v21.0"
DEFAULT_WEBHOOK_PORT = 8478
DEFAULT_WEBHOOK_PATH = "/webhook"
MAX_WEBHOOK_BODY_BYTES = 1024 * 1024


class WhatsAppError(RuntimeError):
    """A WhatsApp Cloud API failure."""


class WhatsAppApi:
    """Standard-library Cloud API client (injectable seam)."""

    def __init__(self, access_token: str, phone_number_id: str) -> None:
        if not access_token:
            raise WhatsAppError("whatsapp access_token is missing")
        if not phone_number_id:
            raise WhatsAppError("whatsapp phone_number_id is missing")
        self.access_token = str(access_token)
        self.phone_number_id = str(phone_number_id)
        self.base_url = GRAPH_API_BASE_URL

    def _call(self, method: str, path: str, payload: Any = None) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urlopen(request, timeout=20) as response:  # nosec B310
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except Exception as exc:
            raise WhatsAppError(f"WhatsApp {method} {path} failed: {exc}") from None

    def send_text(self, recipient: str, text: str) -> dict[str, Any]:
        return self._call(
            "POST",
            f"/{self.phone_number_id}/messages",
            {
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "text",
                "text": {"body": text},
            },
        )

    def download_media(self, media_id: str) -> bytes:
        """Two-step media download: id → URL → bytes."""
        meta = self._call("GET", f"/{media_id}")
        url = str(meta.get("url") or "")
        if not url:
            raise WhatsAppError(f"WhatsApp media {media_id} has no download URL")
        request = Request(
            url, headers={"Authorization": f"Bearer {self.access_token}"}
        )
        try:
            with urlopen(request, timeout=60) as response:  # nosec B310
                return response.read()
        except Exception as exc:
            raise WhatsAppError(f"WhatsApp media download failed: {exc}") from None


class WhatsAppWebhookHandler(BaseHTTPRequestHandler):
    """One webhook HTTP request; deliveries are queued onto the adapter."""

    # Set by the server factory so the handler can reach its adapter.
    adapter: WhatsAppAdapter | None = None

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        logger.debug("whatsapp webhook: " + format, *args)

    def do_GET(self) -> None:  # noqa: N802
        adapter = self.adapter
        if adapter is None:
            self._text(503, "unavailable")
            return
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        mode = query.get("hub.mode", [""])[0]
        token = query.get("hub.verify_token", [""])[0]
        challenge = query.get("hub.challenge", [""])[0]
        expected = str(adapter.config.get("verify_token") or "")
        if mode == "subscribe" and expected and secrets.compare_digest(token, expected):
            self._text(200, challenge)
            return
        self._text(403, "verification failed")

    def do_POST(self) -> None:  # noqa: N802
        adapter = self.adapter
        if adapter is None:
            self._text(503, "unavailable")
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_WEBHOOK_BODY_BYTES:
            self._text(400, "bad payload")
            return
        body = self.rfile.read(length)
        if not adapter.verify_signature(body, self.headers.get("X-Hub-Signature-256", "")):
            self._text(401, "invalid signature")
            return
        try:
            payload = json.loads(body.decode("utf-8"))
        except ValueError:
            self._text(400, "malformed JSON")
            return
        adapter.queue_payload(payload)
        self._text(200, "EVENT_RECEIVED")

    def _text(self, status: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class WhatsAppAdapter(PlatformAdapter):
    """Cloud API webhook listener plus sender."""

    platform_name = "whatsapp"
    max_message_length = 4096
    supports_inline = True
    supports_attachments = True
    privacy = "plaintext"

    def __init__(
        self,
        config: dict[str, Any],
        *,
        on_message: OnMessage,
        api: WhatsAppApi | None = None,
    ) -> None:
        super().__init__(config, on_message=on_message)
        self._api = api
        self._server: ThreadingHTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- config ----------------------------------------------------------- #

    def _build_api(self) -> WhatsAppApi:
        if self._api is not None:
            return self._api
        api = WhatsAppApi(
            str(self._config.get("access_token") or ""),
            str(self._config.get("phone_number_id") or ""),
        )
        self._api = api
        return api

    def _port(self) -> int:
        try:
            return int(self._config.get("port", DEFAULT_WEBHOOK_PORT))
        except (TypeError, ValueError):
            return DEFAULT_WEBHOOK_PORT

    # -- webhook ---------------------------------------------------------- #

    def verify_signature(self, body: bytes, header: str) -> bool:
        """HMAC-SHA256 validation of a webhook body (app secret, if set)."""
        secret = str(self._config.get("app_secret") or "")
        if not secret:
            return True  # validation disabled when no secret is configured
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        header = header.strip()
        if not header.startswith("sha256="):
            return False
        return secrets.compare_digest(expected, header[len("sha256="):])

    def queue_payload(self, payload: dict[str, Any]) -> None:
        """Parse a webhook payload and deliver its messages on the gateway loop."""
        loop = self._loop
        if loop is None:
            logger.warning("whatsapp webhook delivered before the loop was captured")
            return
        asyncio.run_coroutine_threadsafe(self._ingest(payload), loop)

    async def _ingest(self, payload: dict[str, Any]) -> None:
        messages = _extract_messages(payload)
        for message in messages:
            await self._handle_message(message, payload)

    async def _handle_message(self, message: dict[str, Any], payload: dict[str, Any]) -> None:
        from_phone = str(message.get("from") or "")
        message_type = str(message.get("type") or "")
        text = ""
        attachments: list[Attachment] = []
        if message_type == "text":
            text = str(message.get("text", {}).get("body") or "")
        media_types = ("image", "audio", "video", "document", "sticker")
        if message_type in media_types:
            text = str(message.get("caption") or "") or f"[{message_type}]"
            media = message.get(message_type, {}) or {}
            media_id = str(media.get("id") or "")
            mime = str(media.get("mime_type") or "")
            filename = media.get("filename")
            try:
                data = await asyncio.to_thread(self._build_api().download_media, media_id)
            except (WhatsAppError, ValueError):
                data = None
                if media_id:
                    attachments.append(
                        Attachment(mime_type=mime, filename=filename, data=None)
                    )
            else:
                attachments.append(
                    Attachment(
                        mime_type=mime,
                        filename=filename,
                        data=data,
                        size=len(data or b""),
                    )
                )
        if not from_phone or not (text or attachments):
            return
        await self.deliver(
            IncomingMessage(
                platform=self.platform_name,
                platform_user_id=from_phone,
                platform_channel_id=from_phone,
                text=text,
                attachments=attachments,
                message_id=str(message.get("id") or ""),
                timestamp=utc_now(),
                raw={"webhook": payload, "message": message},
            )
        )

    # -- lifecycle -------------------------------------------------------- #

    async def start(self) -> None:
        if self._server is not None:
            return
        try:
            self._build_api()
        except WhatsAppError as exc:
            self._mark_error(str(exc))
            raise
        if not str(self._config.get("verify_token") or ""):
            self._mark_error("whatsapp verify_token is required for webhook verification")
            raise WhatsAppError("whatsapp verify_token is required")
        self._loop = asyncio.get_running_loop()
        handler = type(
            "BoundWhatsAppHandler",
            (WhatsAppWebhookHandler,),
            {"adapter": self},
        )
        path = str(self._config.get("path") or DEFAULT_WEBHOOK_PATH)
        server = ThreadingHTTPServer(("0.0.0.0", self._port()), handler)
        server.daemon_threads = True
        thread = threading.Thread(
            target=server.serve_forever, name="whatsapp-webhook", daemon=True
        )
        thread.start()
        self._server = server
        self._server_thread = thread
        self._status.running = True
        self._status.connected = True
        self._status.error = None
        self._status.detail = f"listening on :{server.server_address[1]}{path}"

    async def stop(self) -> None:
        server = self._server
        thread = self._server_thread
        self._server = None
        self._server_thread = None
        if server is not None:
            await asyncio.to_thread(server.shutdown)
            server.server_close()
        if thread is not None:
            await asyncio.to_thread(thread.join, 5.0)
        self._loop = None
        self._status.running = False
        self._status.connected = False

    # -- outbound ---------------------------------------------------------- #

    async def send_message(self, user_id: str, text: str, attachments: list | None = None) -> None:
        del attachments
        api = self._build_api()
        await asyncio.to_thread(api.send_text, user_id, text)

    async def send_typing_indicator(self, user_id: str) -> None:
        # The Cloud API has no typing endpoint; the webhook response is instant.
        del user_id


def _extract_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Walk the Cloud API webhook shape: entries → changes → value.messages."""
    messages: list[dict[str, Any]] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) if isinstance(change, dict) else {}
            for message in value.get("messages", []) or []:
                if isinstance(message, dict):
                    messages.append(message)
    return messages


__all__ = [
    "WhatsAppAdapter",
    "WhatsAppApi",
    "WhatsAppError",
    "WhatsAppWebhookHandler",
    "_extract_messages",
]
