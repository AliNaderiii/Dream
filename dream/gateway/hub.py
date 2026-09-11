"""Central Hub coordinating multi-platform adapters, session lifecycle, and Dream turns."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from dream.agent import Dream
from dream.cli.commands import dispatch_command
from dream.gateway.delivery import GatewayDeliveryRouter
from dream.gateway.hooks import GatewayHookManager
from dream.gateway.pairing import PairingManager
from dream.gateway.platforms.base import BasePlatformAdapter
from dream.gateway.session import GatewaySessionStore, PlatformSession
from dream.gateway.types import (
    ButtonOption,
    GatewayStatus,
    IncomingMessage,
    InteractivePrompt,
    PlatformType,
)
from dream.memory import MemoryStore
from dream.providers import BuiltInMemoryProvider, ProviderManager

logger = logging.getLogger(__name__)


class GatewayHub:
    """Central orchestrator for all Dream gateway communication channels."""

    def __init__(
        self,
        memory_store: MemoryStore | None = None,
        provider_manager: ProviderManager | None = None,
        db_path: str | None = None,
        auto_pair: bool = False,
    ) -> None:
        self.memory_store = memory_store or MemoryStore(":memory:")
        if provider_manager is not None:
            self.provider_manager = provider_manager
        else:
            self.provider_manager = ProviderManager()
            self.provider_manager.register(BuiltInMemoryProvider(self.memory_store))
        self.session_store = GatewaySessionStore(db_path=db_path)
        self.pairing_manager = PairingManager()
        self.delivery_router = GatewayDeliveryRouter()
        self.hook_manager = GatewayHookManager()
        self.auto_pair = auto_pair

        self._adapters: dict[PlatformType, BasePlatformAdapter] = {}
        self._lock = threading.RLock()
        self._is_running = False
        self._start_time = 0.0
        self._messages_received = 0
        self._reminder_thread: threading.Thread | None = None

    def register_adapter(self, adapter: BasePlatformAdapter) -> None:
        """Register and bind an external platform adapter to the Hub."""
        with self._lock:
            adapter.message_handler = self.handle_incoming_message
            adapter.interaction_handler = self.handle_interaction
            self._adapters[adapter.platform] = adapter
            self.delivery_router.register_adapter(adapter.platform, adapter)
            logger.info(f"Registered gateway adapter: {adapter.platform.value}")

    def start(self) -> bool:
        """Start all registered adapters and background workers."""
        with self._lock:
            if self._is_running:
                return True

            self._is_running = True
            self._start_time = time.time()
            self.delivery_router.start()

            # Connect each platform adapter
            for platform, adapter in self._adapters.items():
                try:
                    ok = adapter.connect()
                    if not ok:
                        logger.warning(f"Failed to connect adapter for {platform.value}")
                except Exception as exc:
                    logger.error(f"Exception connecting adapter {platform.value}: {exc}")

            # Start background reminder scheduler
            self._reminder_thread = threading.Thread(
                target=self._reminder_worker,
                name="GatewayReminderScheduler",
                daemon=True,
            )
            self._reminder_thread.start()
            logger.info("Gateway Hub started successfully.")
            return True

    def stop(self) -> None:
        """Gracefully terminate all platform connections and background loops."""
        with self._lock:
            self._is_running = False

        self.delivery_router.stop()

    @property
    def is_running(self) -> bool:
        """Return True if gateway hub is active."""
        return self._is_running

        for platform, adapter in list(self._adapters.items()):
            try:
                adapter.disconnect()
            except Exception as exc:
                logger.error(f"Error disconnecting adapter {platform.value}: {exc}")

        if self._reminder_thread and self._reminder_thread.is_alive():
            self._reminder_thread.join(timeout=2.0)

        logger.info("Gateway Hub stopped.")

    def handle_incoming_message(self, message: IncomingMessage) -> None:
        """Process incoming user input from any platform channel."""
        with self._lock:
            self._messages_received += 1

        self.hook_manager.on_message_received(message)

        # Retrieve or create session
        session = self.session_store.get_or_create_session(
            platform=message.platform,
            user_id=message.sender_id,
            user_name=message.sender_name,
            channel_id=message.channel_id,
            auto_pair=self.auto_pair,
        )

        text = message.text.strip()
        if not text:
            return

        # 1. Handle pairing code if session is not yet paired
        if not session.is_paired:
            if text.startswith("/pair ") or text.startswith("DREAM-"):
                code = text.replace("/pair", "").strip()
                success, record, reply = self.pairing_manager.verify_and_redeem(code)
                if success and record:
                    self.session_store.mark_paired(message.platform, message.sender_id)
                self.delivery_router.send_text(
                    platform=message.platform,
                    recipient_id=message.sender_id,
                    channel_id=message.channel_id,
                    thread_id=message.thread_id,
                    text=reply,
                    immediate=True,
                )
                return
            else:
                # Issue new pairing code
                code = self.pairing_manager.generate_code(
                    platform=message.platform,
                    user_id=message.sender_id,
                    user_name=message.sender_name,
                )
                pairing_msg = (
                    "🔒 **احراز هویت Dream**\n\n"
                    "برای اتصال به دستیار، کد اتصال زیر را وارد کنید:\n\n"
                    f"`{code}`\n\n"
                    "⏳ اعتبار کد: ۱۰ دقیقه\n\n"
                    f"Or send: `/pair {code}`"
                )
                self.delivery_router.send_text(
                    platform=message.platform,
                    recipient_id=message.sender_id,
                    channel_id=message.channel_id,
                    thread_id=message.thread_id,
                    text=pairing_msg,
                    immediate=True,
                )
                return

        # 2. Handle slash command
        if text.startswith("/"):
            outputs: list[str] = []
            handled = dispatch_command(
                text,
                self._get_dream_instance(session),
                output=outputs.append,
                quiet=False,
            )
            if handled:
                response = (
                    "\n".join(outputs)
                    if outputs
                    else "دستور با موفقیت اجرا شد. / Command executed."
                )
                self.delivery_router.send_text(
                    platform=message.platform,
                    recipient_id=message.sender_id,
                    channel_id=message.channel_id,
                    thread_id=message.thread_id,
                    text=response,
                    immediate=True,
                )
                return

        # 3. Standard conversational Turn execution
        self.hook_manager.on_before_turn(message, session)
        agent = self._get_dream_instance(session)

        turn = agent.run(text)
        reply_text = turn.reply if turn.reply else "درخواست شما انجام شد."

        self.hook_manager.on_turn_completed(message, reply_text)
        self.delivery_router.send_text(
            platform=message.platform,
            recipient_id=message.sender_id,
            channel_id=message.channel_id,
            thread_id=message.thread_id,
            text=reply_text,
            immediate=True,
        )

    def handle_interaction(self, payload: dict[str, Any]) -> None:
        """Process interactive button clicks and security confirmations."""
        platform = payload.get("platform")
        sender_id = payload.get("sender_id")
        action = payload.get("payload", "")

        logger.info(f"Interaction received from {platform} user {sender_id}: {action}")

        # Handle security approval callbacks (e.g. approve_once:cmd_id)
        if action.startswith("approve_"):
            reply = f"✅ اقدام تایید شد: `{action}` / Action approved."
        elif action.startswith("deny_"):
            reply = f"❌ اقدام رد شد: `{action}` / Action denied."
        else:
            reply = f"انتخاب دریافت شد: `{action}` / Selection received."

        if platform and sender_id:
            self.delivery_router.send_text(
                platform=PlatformType(platform),
                recipient_id=sender_id,
                text=reply,
                immediate=True,
            )

    def request_approval(
        self,
        platform: PlatformType,
        recipient_id: str,
        tool_name: str,
        command_preview: str,
        channel_id: str | None = None,
    ) -> str:
        """Send a 3-button security confirmation prompt to the user."""
        prompt_id = f"appr_{int(time.time() * 1000)}"
        prompt = InteractivePrompt(
            prompt_id=prompt_id,
            title="⚠️ تایید اجرای ابزار امنیتی / Tool Execution Approval",
            description=(
                f"ابزار: `{tool_name}`\n"
                f"دستور: `{command_preview}`\n\n"
                f"آیا با اجرای این دستور موافقت می‌کنید؟"
            ),
            options=[
                ButtonOption(
                    button_id="opt_allow_once",
                    label_en="Allow Once",
                    label_fa="یک‌بار تایید",
                    payload=f"approve_once:{prompt_id}",
                    style="primary",
                ),
                ButtonOption(
                    button_id="opt_always_allow",
                    label_en="Always Allow",
                    label_fa="همیشه تایید",
                    payload=f"approve_always:{prompt_id}",
                    style="default",
                ),
                ButtonOption(
                    button_id="opt_deny",
                    label_en="Deny",
                    label_fa="رد کردن",
                    payload=f"deny:{prompt_id}",
                    style="danger",
                ),
            ],
        )

        self.hook_manager.on_approval_requested(prompt)
        adapter = self._adapters.get(platform)
        if adapter:
            target_dest = channel_id or recipient_id
            adapter.send_interactive_prompt(target_dest, prompt)

        return prompt_id

    def get_status(self) -> GatewayStatus:
        """Return runtime diagnostic telemetry of all gateway channels."""
        with self._lock:
            uptime = time.time() - self._start_time if self._is_running else 0.0
            sessions = self.session_store.list_all_sessions()
            details = {p.value: ad.health_check() for p, ad in self._adapters.items()}

            return GatewayStatus(
                is_running=self._is_running,
                active_platforms=list(self._adapters.keys()),
                connected_sessions=len(sessions),
                pending_deliveries=self.delivery_router.pending_count,
                messages_received=self._messages_received,
                messages_sent=self.delivery_router.sent_count,
                uptime_seconds=uptime,
                platform_details=details,
            )

    def _get_dream_instance(self, session: PlatformSession) -> Dream:
        """Build or retrieve configured Dream agent for this user."""
        return Dream(
            store=self.memory_store,
            manager=self.provider_manager,
        )

    def _reminder_worker(self) -> None:
        """Periodic background check for due reminders and notifications."""
        while self._is_running:
            try:
                # Check for due reminders in memory store if method exists
                if hasattr(self.memory_store, "get_due_reminders"):
                    due = self.memory_store.get_due_reminders()
                    for item in due:
                        # Deliver reminder to registered paired sessions
                        for sess in self.session_store.list_all_sessions():
                            if sess.is_paired:
                                self.delivery_router.send_text(
                                    platform=sess.platform,
                                    recipient_id=sess.user_id,
                                    channel_id=sess.channel_id,
                                    text=f"⏰ **یادآوری:** {item.get('text', '')}",
                                )
            except Exception as exc:
                logger.error(f"Error in gateway reminder worker: {exc}")

            time.sleep(15.0)
