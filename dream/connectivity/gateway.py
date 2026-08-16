"""The connectivity gateway: one agent, one memory, every channel.

The gateway owns the six platform adapters, the per-channel session registry,
the auth store, the rate limiter, the message log, and the router that turns
every normalised :class:`IncomingMessage` into a Dream turn. It runs on its
own asyncio event-loop thread, independent of the bridge's loop, so adapter
websockets and webhook servers stay alive between RPC calls.

Threading contract:

* coroutines that touch adapters run **on the gateway loop** (``submit`` /
  ``submit_async`` ferry them there);
* ``route_message`` and ``start_all``/``stop_all`` are coroutines — await them
  directly when already on the gateway loop (e.g. from ``start_all``), never
  via ``run_coroutine_threadsafe(...).result()``;
* synchronous snapshots (``status``, ``adapter_status``, ``logs``) are
  thread-safe and callable from any thread.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import Any

from dream.connectivity.auth import AuthStore
from dream.connectivity.base import PlatformAdapter, split_text
from dream.connectivity.config import ConnectivityConfig
from dream.connectivity.messagelog import MessageLog
from dream.connectivity.models import IncomingMessage, LinkedUser, PlatformStatus
from dream.connectivity.ratelimit import RateLimiter
from dream.connectivity.sessions import SessionRegistry

logger = logging.getLogger(__name__)

#: Default cap on one submit() wait from a foreign thread.
SUBMIT_TIMEOUT_SECONDS = 30.0
#: How long start_loop() waits for the event loop to come up.
LOOP_START_TIMEOUT_SECONDS = 10.0

HELP_TEXT = (
    "Dream gateway commands:\n"
    "/help — show this help\n"
    "/status — session and gateway status\n"
    "/new_session — forget this chat's history and start fresh\n"
    "/link <code> — pair this chat with the desktop app"
)
RATE_LIMITED_TEXT = "You are sending messages too quickly. Please wait a moment."
REFUSAL_TEXT = "This chat is not linked to a Dream desktop. Use /link <code>."
LINK_OK_TEXT = "Linked! You can now talk to Dream."
LINK_BAD_TEXT = "That link code is invalid or expired. Ask the desktop for a new one."


class Gateway:
    """Owns adapters, sessions, auth, rate limiting, and the message log."""

    def __init__(
        self,
        config: ConnectivityConfig,
        *,
        store: Any | None = None,
        sessions_path: str | None = None,
        links_path: str | None = None,
        log_path: str | None = None,
        dream_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.config = config
        self._store = store
        self._dream_factory = dream_factory or self._default_dream_factory
        self._sessions = SessionRegistry(
            sessions_path or "data/connectivity_sessions.json",
            dream_factory=self._dream_factory,
        )
        self._auth = AuthStore(links_path or "data/connectivity_links.json")
        self._log = MessageLog(log_path or "data/connectivity_log.jsonl")
        self._rate = RateLimiter()
        for platform in config.all():
            self._rate.configure(platform, config.rate_limit_per_minute(platform))

        self._adapters: dict[str, PlatformAdapter] = {}
        self._status_lock = threading.RLock()
        self._inbound_total = 0
        self._outbound_total = 0

        # Event-loop-thread plumbing.
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_future: asyncio.Future[None] | None = None
        self._loop_started = threading.Event()
        self._started_at: float | None = None
        self._stop_requested = threading.Event()

    # -- agent construction ------------------------------------------------ #

    def _default_dream_factory(self) -> Any:
        """A Dream over a private in-memory store; the bridge overrides this."""
        from dream.agent import ApprovalPolicy, Dream, EchoBackend
        from dream.memory import MemoryStore

        store = self._store or MemoryStore(":memory:")
        return Dream(store, EchoBackend(), ApprovalPolicy())

    # -- loop thread ------------------------------------------------------- #

    def start_loop(self) -> None:
        """Start the dedicated event-loop thread (idempotent)."""
        with self._status_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._loop_started.clear()
            self._stop_requested.clear()
            thread = threading.Thread(
                target=self._run_loop, name="dream-connectivity", daemon=True
            )
            self._thread = thread
            thread.start()
        if not self._loop_started.wait(LOOP_START_TIMEOUT_SECONDS):
            raise RuntimeError("connectivity event loop failed to start")
        self._started_at = self._started_at or _now()

    def _run_loop(self) -> None:
        asyncio.run(self._loop_main())

    async def _loop_main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_future = self._loop.create_future()
        self._loop_started.set()
        await self._stop_future

    def stop_loop(self) -> None:
        """Stop every adapter, then tear down the loop thread (idempotent)."""
        self._stop_requested.set()
        loop = self._loop
        stop_future = self._stop_future
        if loop is not None and stop_future is not None:
            async def _shutdown() -> None:
                await self.stop_all()
                if not stop_future.done():
                    stop_future.set_result(None)

            try:
                asyncio.run_coroutine_threadsafe(_shutdown(), loop)
            except RuntimeError:
                pass  # loop already gone
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=SUBMIT_TIMEOUT_SECONDS)
        self._loop = None
        self._thread = None

    @property
    def is_running(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
            and not self._stop_requested.is_set()
        )

    # -- cross-thread submission ------------------------------------------- #

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self.start_loop()
        assert self._loop is not None
        return self._loop

    def submit(
        self,
        coro: Awaitable[Any] | Callable[[], Awaitable[Any]],
        timeout: float = SUBMIT_TIMEOUT_SECONDS,
    ) -> Any:
        """Run a coroutine on the gateway loop and return its result.

        Synchronous: call from bridge helper threads or tests. Pass either a
        fresh coroutine or a zero-argument factory that returns one.
        """
        loop = self._ensure_loop()
        if callable(coro):
            coro = coro()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout)

    async def submit_async(self, coro: Awaitable[Any]) -> Any:
        """Await a coroutine on the gateway loop without blocking the caller.

        The async counterpart of :meth:`submit` for coroutines that already
        live on another loop (the bridge's).
        """
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return await asyncio.wrap_future(future)

    # -- adapter registry --------------------------------------------------- #

    def register_adapter(self, adapter: PlatformAdapter) -> None:
        """Register one adapter under its ``platform_name`` (replaces)."""
        with self._status_lock:
            self._adapters[adapter.platform_name] = adapter

    def unregister_adapter(self, platform: str) -> None:
        with self._status_lock:
            self._adapters.pop(platform, None)

    def register_default_adapters(self) -> list[PlatformAdapter]:
        """Build and register the six bundled adapters from the catalog."""
        from dream.connectivity.adapters import build_adapters

        adapters = build_adapters(self.config, on_message=self._on_adapter_message)
        for adapter in adapters:
            self.register_adapter(adapter)
        return adapters

    def adapter(self, platform: str) -> PlatformAdapter | None:
        with self._status_lock:
            return self._adapters.get(platform)

    def adapters(self) -> dict[str, PlatformAdapter]:
        with self._status_lock:
            return dict(self._adapters)

    # -- lifecycle ---------------------------------------------------------- #

    async def start_all(self) -> dict[str, Any]:
        """Start every enabled adapter; unconfigured ones stay dormant."""
        if not self._adapters:
            self.register_default_adapters()
        for name, adapter in self.adapters().items():
            enabled = self.config.enabled(name)
            configured = self.config.configured(name)
            status = adapter.status
            status.error = None
            if not enabled:
                status.running = False
                status.detail = "disabled"
                continue
            if not configured:
                status.running = False
                status.detail = "missing configuration"
                continue
            try:
                await adapter.start()
                status.running = True
                status.detail = ""
            except Exception as exc:
                status.running = False
                status.error = f"{type(exc).__name__}: {exc}"
                status.detail = "failed to start"
                logger.warning("adapter %s failed to start: %s", name, exc)
        return self.status()

    async def stop_all(self) -> None:
        """Stop every adapter, tolerating individual failures."""
        for adapter in self.adapters().values():
            try:
                await adapter.stop()
                adapter.status.running = False
            except Exception as exc:
                logger.warning("adapter %s failed to stop: %s", adapter.platform_name, exc)

    async def start_adapter(self, platform: str) -> dict[str, Any]:
        adapter = self.adapter(platform)
        if adapter is None:
            raise ValueError(f"no adapter for platform {platform!r}")
        if not self.config.enabled(platform):
            raise ValueError(f"platform {platform!r} is disabled in config")
        if not self.config.configured(platform):
            raise ValueError(f"platform {platform!r} is missing required configuration")
        await adapter.start()
        adapter.status.running = True
        return adapter.status.to_dict()

    async def stop_adapter(self, platform: str) -> dict[str, Any]:
        adapter = self.adapter(platform)
        if adapter is None:
            raise ValueError(f"no adapter for platform {platform!r}")
        await adapter.stop()
        adapter.status.running = False
        return adapter.status.to_dict()

    # -- routing ------------------------------------------------------------ #

    async def _on_adapter_message(self, message: IncomingMessage) -> None:
        """Callback every adapter delivers through (runs on the gateway loop)."""
        try:
            await self.route_message(message)
        except Exception:  # a bad message must never kill the gateway loop
            logger.exception("route_message failed for %s", message.platform)

    async def route_message(self, message: IncomingMessage) -> None:
        """The full pipeline: log → pre-auth commands → auth → rate → agent."""
        platform = message.platform
        user_id = message.platform_user_id
        adapter = self.adapter(platform)
        if adapter is None:
            logger.warning("dropped message for unregistered platform %r", platform)
            return
        privacy = adapter.privacy
        log_text = "" if privacy == "e2e" else message.text
        self._log.add(
            platform, "in", user_id, log_text,
            message_id=message.message_id, attachments=len(message.attachments),
        )
        adapter._note_activity()
        self._inbound_total += 1

        # Commands that exist *to get you in* must work before the auth gate:
        # /link pairs the chat, /help explains how. Everything else requires
        # a linked identity when the platform demands one.
        if self._is_pre_auth_command(message.text):
            _, reply = self._run_command(platform, user_id, message.text)
            await self._send_reply(adapter, user_id, reply)
            return

        if self._auth_required(platform) and not self._auth.is_linked(platform, user_id):
            await self._send_reply(adapter, user_id, REFUSAL_TEXT)
            return

        decision = self._rate.check(platform, user_id)
        if not decision.allowed:
            await self._send_reply(adapter, user_id, RATE_LIMITED_TEXT)
            return

        handled, reply = self._run_command(platform, user_id, message.text)
        if not handled:
            reply = await self._agent_reply(adapter, platform, user_id, message.text)
            # Only agent turns count as session messages: /status, /help and
            # friends are bookkeeping, not conversation.
            self._sessions.touch(platform, user_id)

        await self._send_reply(adapter, user_id, reply)

    @staticmethod
    def _is_pre_auth_command(text: str) -> bool:
        stripped = str(text).strip()
        if not stripped.startswith("/"):
            return False
        command = stripped.partition(" ")[0].split("@", 1)[0].lower()
        return command in {"/link", "/help", "/start"}

    def _auth_required(self, platform: str) -> bool:
        return bool(self.config.get(platform).get("require_auth", True))

    def _run_command(self, platform: str, user_id: str, text: str) -> tuple[bool, str]:
        """Handle gateway commands; returns (handled, reply)."""
        stripped = str(text).strip()
        if not stripped.startswith("/"):
            return False, ""
        command, separator, argument = stripped.partition(" ")
        command = command.split("@", 1)[0].lower()
        if command in {"/start", "/help"}:
            return True, HELP_TEXT
        if command == "/status":
            session = self._sessions.stats(platform)
            row = next((s for s in session if s["user_id"] == user_id), None)
            messages = row["message_count"] if row else 0
            linked = self._auth.is_linked(platform, user_id)
            return True, (
                f"Dream gateway — platform: {platform}\n"
                f"linked: {'yes' if linked else 'no'}\n"
                f"session messages: {messages}"
            )
        if command == "/new_session":
            self._sessions.reset(platform, user_id)
            return True, "New session started. History forgotten."
        if command == "/link":
            code = argument.strip()
            redeemed = self._auth.redeem(platform, user_id, code) if code else None
            if redeemed is not None:
                self._auth.link(platform, user_id)
                return True, LINK_OK_TEXT
            return True, LINK_BAD_TEXT
        return False, ""

    async def _agent_reply(
        self, adapter: PlatformAdapter, platform: str, user_id: str, text: str
    ) -> str:
        """Run one Dream turn for the channel, best-effort typing first."""
        try:
            await adapter.send_typing_indicator(user_id)
        except Exception:
            pass  # typing indicators are cosmetic
        dream = self._sessions.get(platform, user_id)
        turn = await asyncio.to_thread(dream.run, text)
        return str(getattr(turn, "reply", "") or "")

    async def _send_reply(self, adapter: PlatformAdapter, user_id: str, reply: str) -> None:
        """Split, send, and log one outbound reply."""
        for chunk in split_text(reply, adapter.max_message_length):
            await adapter.send_message(user_id, chunk)
        log_text = "" if adapter.privacy == "e2e" else reply
        self._log.add(adapter.platform_name, "out", user_id, log_text)
        self._outbound_total += 1

    # -- RPC-facing operations ---------------------------------------------- #

    def link_code(self, platform: str) -> dict[str, Any]:
        """Issue a single-use, time-bounded code for one platform."""
        code = self._auth.issue(platform)
        return code.to_dict()

    def linked_users(self, platform: str | None = None) -> list[dict[str, Any]]:
        return [user.to_dict() for user in self._auth.linked(platform)]

    def unlink_user(self, platform: str, user_id: str) -> dict[str, Any]:
        return {
            "unlinked": self._auth.unlink(platform, user_id),
            "platform": platform,
            "user_id": user_id,
        }

    def logs(self, platform: str | None = None, limit: int | None = None) -> dict[str, Any]:
        return self._log.to_dict(platform, limit)

    def platforms(self) -> list[dict[str, Any]]:
        """The platform catalog joined with redacted public config."""
        from dream.connectivity.platforms import PLATFORM_CATALOG

        public = self.config.public()
        return [
            {
                **{key: value for key, value in catalog.items() if key != "fields"},
                "fields": catalog["fields"],
                "enabled": bool(public.get(name, {}).get("enabled", False)),
                "configured": bool(public.get(name, {}).get("configured", False)),
            }
            for name, catalog in PLATFORM_CATALOG.items()
        ]

    def configure(self, platform: str, values: dict[str, Any]) -> dict[str, Any]:
        """Merge config for one platform, update gating, return the public view."""
        self.config.set(platform, values)
        self._rate.configure(platform, self.config.rate_limit_per_minute(platform))
        return self.config.public(platform)

    def status(self) -> dict[str, Any]:
        """Aggregate status snapshot — safe to call from any thread."""
        adapters: list[dict[str, Any]] = []
        for name, adapter in self.adapters().items():
            row = adapter.status.to_dict()
            if not row["running"] and not row["detail"]:
                enabled = self.config.enabled(name)
                configured = self.config.configured(name)
                if not enabled:
                    row["detail"] = "disabled"
                elif not configured:
                    row["detail"] = "missing configuration"
                else:
                    row["detail"] = "stopped"
            adapters.append(row)
        return {
            "running": self.is_running,
            "started_at": self._started_at,
            "adapters": adapters,
            "linked_users": self.linked_users(),
            "messages": {"inbound": self._inbound_total, "outbound": self._outbound_total},
            "rate_limit": self._rate.to_dict(),
        }

    def adapter_status(self, platform: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
        """One adapter's status dict, or a list of all of them."""
        if platform is not None:
            adapter = self.adapter(platform)
            if adapter is None:
                raise ValueError(f"no adapter for platform {platform!r}")
            return adapter.status.to_dict()
        return [adapter.status.to_dict() for adapter in self.adapters().values()]


def _now() -> float:
    import time

    return time.time()


__all__ = [
    "Gateway",
    "HELP_TEXT",
    "LINK_BAD_TEXT",
    "LINK_OK_TEXT",
    "RATE_LIMITED_TEXT",
    "REFUSAL_TEXT",
    "LinkedUser",
    "PlatformStatus",
    "SUBMIT_TIMEOUT_SECONDS",
]
