"""Email adapter: IMAP IDLE (with polling fallback) + SMTP replies.

* inbound: ``imaplib`` over SSL. When the server advertises IDLE the adapter
  uses the raw-socket trick — ``IMAP4._simple_command("IDLE")`` followed by
  draining ``_get_response()`` — with a socket timeout bounding each wait;
  otherwise (or on IDLE failure) it falls back to a ``UNSEEN`` search poll;
* parsing: the ``email`` package splits MIME parts; HTML parts are reduced to
  text with a small :class:`html.parser.HTMLParser` stripper; attachments are
  kept in memory (bounded by a configured size cap);
* replies: ``smtplib`` with ``In-Reply-To``/``References`` threading headers;
  reply loops are avoided twice over — messages from our own address are
  skipped, and a bounded set of already-answered Message-IDs is remembered.
"""

from __future__ import annotations

import asyncio
import email
import email.policy
import html.parser
import imaplib
import logging
import smtplib
import socket
from collections import deque
from email.message import Message
from email.utils import parseaddr
from typing import Any

from dream.connectivity.base import OnMessage, PlatformAdapter
from dream.connectivity.models import Attachment, IncomingMessage, utc_now

logger = logging.getLogger(__name__)

DEFAULT_IMAP_PORT = 993
DEFAULT_SMTP_PORT = 465
DEFAULT_MAILBOX = "INBOX"
DEFAULT_POLL_SECONDS = 60
DEFAULT_MAX_EMAIL_BYTES = 10 * 1024 * 1024
REPLIED_SET_LIMIT = 500
IDLE_SOCKET_TIMEOUT = 29 * 60  # just under the typical 30-minute server timeout


class EmailError(RuntimeError):
    """An IMAP/SMTP transport or configuration failure."""


class _HtmlTextExtractor(html.parser.HTMLParser):
    """Reduce an HTML document to readable plain text."""

    _BLOCK_TAGS = {
        "p", "div", "br", "li", "ul", "ol", "tr", "blockquote", "h1", "h2",
        "h3", "h4", "h5", "h6", "table", "section", "article",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line).strip()


def html_to_text(html_body: str) -> str:
    """Strip markup from an HTML part using the stdlib parser."""
    extractor = _HtmlTextExtractor()
    try:
        extractor.feed(html_body)
        extractor.close()
    except Exception:
        return html_body
    return extractor.text()


class ImapClient:
    """imaplib wrapper — the injectable seam for inbound mail."""

    def __init__(self, host: str, port: int, user: str, password: str, mailbox: str) -> None:
        self.host = str(host)
        self.port = int(port)
        self.user = str(user)
        self.password = str(password)
        self.mailbox = str(mailbox or DEFAULT_MAILBOX)
        self._imap: imaplib.IMAP4_SSL | None = None

    def connect(self) -> None:
        if self._imap is not None:
            return
        try:
            imap = imaplib.IMAP4_SSL(self.host, self.port)
        except (OSError, imaplib.IMAP4.error) as exc:
            raise EmailError(f"IMAP connect failed: {exc}") from None
        try:
            imap.login(self.user, self.password)
            imap.select(self.mailbox)
        except imaplib.IMAP4.error as exc:
            try:
                imap.logout()
            except Exception:
                pass
            raise EmailError(f"IMAP login/select failed: {exc}") from None
        self._imap = imap

    def disconnect(self) -> None:
        imap = self._imap
        self._imap = None
        if imap is None:
            return
        try:
            imap.close()
        except Exception:
            pass
        try:
            imap.logout()
        except Exception:
            pass

    @property
    def socket(self) -> socket.socket:
        imap = self._imap
        if imap is None or imap.sock is None:
            raise EmailError("IMAP is not connected")
        return imap.sock

    def supports_idle(self) -> bool:
        imap = self._imap
        if imap is None:
            return False
        capabilities = imap.capabilities
        if not capabilities:
            capabilities = tuple(c.upper() for c in imap.capability()[0] or ())
        return any(str(cap).upper() == "IDLE" for cap in capabilities)

    def idle_once(self, timeout: int) -> bool:
        """Wait up to *timeout* seconds for new mail; True when it arrived.

        Implements RFC 2177 IDLE with the raw-socket trick: issue ``IDLE``,
        drain the continuation, then watch for an untagged response. A socket
        timeout ends the idle with ``DONE``.
        """
        imap = self._imap
        if imap is None:
            raise EmailError("IMAP is not connected")
        sock = self.socket
        sock.settimeout(min(timeout, IDLE_SOCKET_TIMEOUT) or IDLE_SOCKET_TIMEOUT)
        tag = imap._new_tag().decode()
        try:
            imap.send(f"{tag} IDLE\r\n".encode())
            while True:
                line = imap._get_line()
                if line is None:
                    raise EmailError("IMAP connection closed during IDLE")
                if line.startswith(b"+ "):
                    break  # server is now idling
            while True:
                line = imap._get_line()
                if line.startswith(b"* "):
                    imap.send(b"DONE\r\n")
                    self._drain_until_tagged(tag)
                    return True
        except (TimeoutError, OSError):
            try:
                imap.send(b"DONE\r\n")
                self._drain_until_tagged(tag)
            except Exception:
                self.disconnect()
            return False
        except imaplib.IMAP4.error as exc:
            raise EmailError(f"IMAP IDLE failed: {exc}") from None
        finally:
            try:
                sock.settimeout(None)
            except OSError:
                pass

    def _drain_until_tagged(self, tag: str) -> None:
        imap = self._imap
        if imap is None:
            return
        while True:
            line = imap._get_line()
            if line is None or line.startswith(f"{tag} ".encode()):
                return

    def search_unseen(self) -> list[int]:
        imap = self._imap
        if imap is None:
            raise EmailError("IMAP is not connected")
        status, data = imap.search(None, "UNSEEN")
        if status != "OK" or not data or not data[0]:
            return []
        numbers: list[int] = []
        for token in data[0].split():
            try:
                numbers.append(int(token))
            except ValueError:
                continue
        return numbers

    def fetch_rfc822(self, number: int) -> bytes:
        imap = self._imap
        if imap is None:
            raise EmailError("IMAP is not connected")
        status, data = imap.fetch(str(number), "(RFC822)")
        if status != "OK":
            raise EmailError(f"IMAP fetch failed for message {number}")
        for part in data:
            if isinstance(part, tuple):
                return part[1]
        raise EmailError(f"IMAP fetch returned no body for message {number}")

    def mark_seen(self, number: int) -> None:
        imap = self._imap
        if imap is not None:
            try:
                imap.store(str(number), "+FLAGS", "(\\Seen)")
            except imaplib.IMAP4.error:
                pass


class SmtpClient:
    """smtplib wrapper — the injectable seam for outbound mail."""

    def __init__(self, host: str, port: int, user: str | None, password: str | None) -> None:
        self.host = str(host)
        self.port = int(port)
        self.user = user or None
        self.password = password or None

    def send(
        self,
        from_addr: str,
        to_addr: str,
        subject: str,
        body: str,
        *,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> None:
        message = email.message.EmailMessage()
        message["From"] = from_addr
        message["To"] = to_addr
        message["Subject"] = subject
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
        if references:
            message["References"] = references
        message.set_content(body)
        try:
            if self.port == 465:
                client = smtplib.SMTP_SSL(self.host, self.port, timeout=30)
            else:
                client = smtplib.SMTP(self.host, self.port, timeout=30)
            with client:
                client.ehlo()
                if self.port != 465:
                    client.starttls()
                    client.ehlo()
                if self.user:
                    client.login(self.user, self.password or "")
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailError(f"SMTP send failed: {exc}") from None


def _first_header(message: Message, name: str) -> str:
    value = message.get(name)
    return str(value).strip() if value else ""


class EmailAdapter(PlatformAdapter):
    """IMAP IDLE (or polling) inbox watcher with threaded SMTP replies."""

    platform_name = "email"
    max_message_length = 4000
    supports_inline = False
    supports_attachments = True
    privacy = "plaintext"

    def __init__(
        self,
        config: dict[str, Any],
        *,
        on_message: OnMessage,
        imap: ImapClient | None = None,
        smtp: SmtpClient | None = None,
    ) -> None:
        super().__init__(config, on_message=on_message)
        self._imap = imap
        self._smtp = smtp
        self._task: asyncio.Task[Any] | None = None
        self._stop_event = asyncio.Event()
        self._replied: deque[str] = deque(maxlen=REPLIED_SET_LIMIT)
        #: user_id -> last inbound Message-ID (for In-Reply-To threading).
        self._last_message_ids: dict[str, str] = {}

    # -- config ----------------------------------------------------------- #

    def _required(self, key: str) -> str:
        value = str(self._config.get(key) or "").strip()
        if not value:
            raise EmailError(f"email config requires {key}")
        return value

    def _build_imap(self) -> ImapClient:
        if self._imap is not None:
            return self._imap
        imap = ImapClient(
            self._required("imap_host"),
            int(self._config.get("imap_port") or DEFAULT_IMAP_PORT),
            self._required("imap_user"),
            str(self._config.get("imap_password") or ""),
            str(self._config.get("mailbox") or DEFAULT_MAILBOX),
        )
        self._imap = imap
        return imap

    def _build_smtp(self) -> SmtpClient:
        if self._smtp is not None:
            return self._smtp
        smtp = SmtpClient(
            self._required("smtp_host"),
            int(self._config.get("smtp_port") or DEFAULT_SMTP_PORT),
            str(self._config.get("smtp_user") or "") or None,
            str(self._config.get("smtp_password") or "") or None,
        )
        self._smtp = smtp
        return smtp

    def _poll_seconds(self) -> float:
        try:
            return max(0.05, float(self._config.get("poll_seconds", DEFAULT_POLL_SECONDS)))
        except (TypeError, ValueError):
            return DEFAULT_POLL_SECONDS

    def _own_address(self) -> str:
        return (
            str(self._config.get("smtp_user") or "")
            or self._required("imap_user")
        ).lower()

    # -- lifecycle -------------------------------------------------------- #

    async def start(self) -> None:
        if self._task is not None:
            return
        try:
            self._required("imap_password")
            imap = self._build_imap()
            self._build_smtp()
            await asyncio.to_thread(imap.connect)
        except (EmailError, OSError) as exc:
            self._mark_error(str(exc))
            raise
        self._stop_event.clear()
        self._status.running = True
        self._status.connected = True
        self._status.error = None
        self._task = asyncio.create_task(self._watch_loop(), name="email-watch")

    async def stop(self) -> None:
        self._stop_event.set()
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        if self._imap is not None:
            await asyncio.to_thread(self._imap.disconnect)
        self._status.running = False
        self._status.connected = False

    async def _watch_loop(self) -> None:
        imap = self._build_imap()
        use_idle = bool(self._config.get("use_idle", True))
        if use_idle:
            try:
                supports = await asyncio.to_thread(imap.supports_idle)
            except EmailError:
                supports = False
        else:
            supports = False
        while not self._stop_event.is_set():
            try:
                if supports:
                    arrived = await asyncio.to_thread(
                        imap.idle_once, int(self._poll_seconds())
                    )
                    if arrived:
                        await self._process_unseen()
                else:
                    await asyncio.sleep(self._poll_seconds())
                    await self._process_unseen()
            except asyncio.CancelledError:
                raise
            except (EmailError, OSError) as exc:
                self._mark_error(str(exc), running=True)
                try:
                    await asyncio.to_thread(imap.disconnect)
                except Exception:
                    pass
                try:
                    await asyncio.to_thread(imap.connect)
                except (EmailError, OSError):
                    await asyncio.sleep(5.0)

    async def _process_unseen(self) -> None:
        imap = self._build_imap()
        try:
            numbers = await asyncio.to_thread(imap.search_unseen)
        except (EmailError, OSError):
            return
        for number in numbers:
            try:
                raw = await asyncio.to_thread(imap.fetch_rfc822, number)
            except (EmailError, OSError):
                continue
            await self._handle_raw(raw)
            await asyncio.to_thread(imap.mark_seen, number)

    async def _handle_raw(self, raw: bytes) -> None:
        max_bytes = int(self._config.get("max_email_bytes", DEFAULT_MAX_EMAIL_BYTES))
        if len(raw) > max_bytes:
            logger.info("skipping oversized email (%d bytes)", len(raw))
            return
        try:
            message = email.message_from_bytes(raw, policy=email.policy.default)
        except Exception as exc:
            logger.warning("unparseable email skipped: %s", exc)
            return
        sender = str(parseaddr(str(message.get("From") or ""))[1] or "").strip().lower()
        if not sender or sender == self._own_address():
            return  # reply-loop guard: never answer ourselves
        message_id = _first_header(message, "Message-ID")
        if message_id and message_id in self._replied:
            return  # already answered
        body, attachments = _extract_body_and_attachments(message)
        if not body.strip():
            return
        if message_id:
            self._replied.append(message_id)
            self._last_message_ids[sender] = message_id
        await self.deliver(
            IncomingMessage(
                platform=self.platform_name,
                platform_user_id=sender,
                platform_channel_id=None,
                text=body,
                attachments=attachments,
                message_id=message_id or None,
                timestamp=utc_now(),
                raw={"subject": str(message.get("Subject") or "")},
            )
        )

    # -- outbound ---------------------------------------------------------- #

    async def send_message(self, user_id: str, text: str, attachments: list | None = None) -> None:
        del attachments  # text replies only; attachments stay inbound
        smtp = self._build_smtp()
        from_addr = self._own_address()
        in_reply_to = self._last_message_ids.get(user_id)
        await asyncio.to_thread(
            smtp.send,
            from_addr,
            user_id,
            "Re: Dream",
            text,
            in_reply_to=in_reply_to,
            references=in_reply_to,
        )

    async def send_typing_indicator(self, user_id: str) -> None:
        del user_id  # email has no typing indicator


def _extract_body_and_attachments(message: Message) -> tuple[str, list[Attachment]]:
    """Pull readable text and in-memory attachments out of a MIME message."""
    text_parts: list[str] = []
    attachments: list[Attachment] = []
    for part in message.walk():
        if part.is_multipart():
            continue
        content_type = part.get_content_type()
        disposition = str(part.get("Content-Disposition") or "")
        try:
            payload = part.get_payload(decode=True)
        except Exception:
            payload = None
        if "attachment" in disposition or content_type not in {"text/plain", "text/html"}:
            if payload is not None:
                attachments.append(
                    Attachment(
                        mime_type=content_type,
                        filename=part.get_filename(),
                        data=payload,
                        size=len(payload),
                    )
                )
            continue
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            decoded = payload.decode(charset, "replace")
        except LookupError:
            decoded = payload.decode("utf-8", "replace")
        if content_type == "text/html":
            decoded = html_to_text(decoded)
        if decoded.strip():
            text_parts.append(decoded.strip())
    return "\n\n".join(text_parts), attachments


__all__ = [
    "EmailAdapter",
    "EmailError",
    "ImapClient",
    "SmtpClient",
    "html_to_text",
]
