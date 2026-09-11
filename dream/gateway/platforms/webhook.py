"""Generic HTTP Webhook & REST/SSE platform adapter with HMAC signature verification."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.request import Request, urlopen

from dream.gateway.platforms.base import BasePlatformAdapter
from dream.gateway.types import (
    IncomingMessage,
    InteractivePrompt,
    OutgoingMessage,
    PlatformType,
)

logger = logging.getLogger(__name__)


class WebhookAdapter(BasePlatformAdapter):
    """Adapter for generic inbound and outbound HTTP webhooks with HMAC security."""

    def __init__(
        self,
        listen_host: str = "127.0.0.1",
        listen_port: int = 8765,
        secret_key: str | None = None,
        outbound_webhook_url: str | None = None,
        message_handler: Callable[[IncomingMessage], Any] | None = None,
        interaction_handler: Callable[[Any], Any] | None = None,
    ) -> None:
        super().__init__(PlatformType.WEBHOOK, message_handler, interaction_handler)
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.secret_key = secret_key
        self.outbound_webhook_url = outbound_webhook_url
        self._server: HTTPServer | None = None
        self._server_thread: threading.Thread | None = None

    def connect(self) -> bool:
        """Start local HTTP server listening for inbound webhooks."""
        try:
            adapter_self = self

            class WebhookHTTPHandler(BaseHTTPRequestHandler):
                def do_POST(self) -> None:
                    content_len = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_len)

                    # Verify HMAC signature if secret key is set
                    if adapter_self.secret_key:
                        signature = self.headers.get("X-Dream-Signature", "")
                        if not adapter_self.verify_signature(body, signature):
                            self.send_response(401)
                            self.end_headers()
                            self.wfile.write(b'{"error": "Unauthorized / Invalid Signature"}')
                            return

                    try:
                        data = json.loads(body.decode("utf-8"))
                    except Exception:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b'{"error": "Invalid JSON"}')
                        return

                    # Process incoming payload
                    sender_id = str(data.get("sender_id", "webhook_client"))
                    sender_name = str(data.get("sender_name", "External Webhook"))
                    text = str(data.get("text", ""))
                    hash_id = int(hashlib.md5(body).hexdigest()[:8], 16)
                    msg_id = str(data.get("message_id", f"wh_{hash_id}"))

                    incoming = IncomingMessage(
                        message_id=msg_id,
                        platform=PlatformType.WEBHOOK,
                        sender_id=sender_id,
                        sender_name=sender_name,
                        text=text,
                        raw_payload=data,
                    )

                    if adapter_self.message_handler:
                        adapter_self.message_handler(incoming)

                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status": "received"}')

                def do_GET(self) -> None:
                    # Health check endpoint
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status": "active", "service": "Dream Webhook Gateway"}')

                def log_message(self, format: str, *args: Any) -> None:
                    # Suppress default noisy stdio logging
                    pass

            self._server = HTTPServer((self.listen_host, self.listen_port), WebhookHTTPHandler)
            self._server_thread = threading.Thread(
                target=self._server.serve_forever,
                name="WebhookGatewayServer",
                daemon=True,
            )
            self._server_thread.start()
            self.is_connected = True
            logger.info(f"Webhook gateway listening on http://{self.listen_host}:{self.listen_port}")
            return True
        except Exception as exc:
            logger.error(f"Failed to start webhook server: {exc}")
            return False

    def disconnect(self) -> None:
        """Stop HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        self.is_connected = False

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify HMAC-SHA256 payload signature."""
        if not self.secret_key:
            return True
        expected = hmac.new(self.secret_key.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def sign_payload(self, payload: bytes) -> str:
        """Generate HMAC-SHA256 signature for outgoing payload."""
        if not self.secret_key:
            return ""
        return hmac.new(self.secret_key.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    def send_message(self, message: OutgoingMessage) -> bool:
        """Post message payload to outbound webhook URL."""
        if not self.outbound_webhook_url:
            return False

        payload_dict = {
            "platform": "webhook",
            "recipient_id": message.target.recipient_id,
            "channel_id": message.target.channel_id,
            "text": message.text,
            "message_type": message.message_type.value,
        }
        body = json.dumps(payload_dict).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.secret_key:
            headers["X-Dream-Signature"] = self.sign_payload(body)

        try:
            req = Request(self.outbound_webhook_url, data=body, headers=headers, method="POST")
            with urlopen(req, timeout=15.0) as resp:
                return resp.status in (200, 201, 202, 204)
        except Exception as exc:
            logger.error(f"Outbound webhook delivery failed: {exc}")
            return False

    def send_interactive_prompt(self, target_id: str, prompt: InteractivePrompt) -> bool:
        """Send interactive prompt to outbound webhook."""
        if not self.outbound_webhook_url:
            return False

        payload_dict = {
            "platform": "webhook",
            "recipient_id": target_id,
            "prompt_id": prompt.prompt_id,
            "title": prompt.title,
            "description": prompt.description,
            "options": [
                {
                    "button_id": o.button_id,
                    "label_en": o.label_en,
                    "label_fa": o.label_fa,
                    "payload": o.payload,
                    "style": o.style,
                }
                for o in prompt.options
            ],
        }
        body = json.dumps(payload_dict).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.secret_key:
            headers["X-Dream-Signature"] = self.sign_payload(body)

        try:
            req = Request(self.outbound_webhook_url, data=body, headers=headers, method="POST")
            with urlopen(req, timeout=15.0) as resp:
                return resp.status in (200, 201, 202, 204)
        except Exception as exc:
            logger.error(f"Outbound webhook interactive delivery failed: {exc}")
            return False
