"""Tests for Dream Universal Multi-Platform Gateway (Telegram, Discord, Slack, Webhook)."""

from __future__ import annotations

from dream.gateway.delivery import GatewayDeliveryRouter
from dream.gateway.hooks import GatewayHookManager
from dream.gateway.hub import GatewayHub
from dream.gateway.pairing import PairingManager
from dream.gateway.platforms.base import BasePlatformAdapter
from dream.gateway.platforms.discord import DiscordAdapter
from dream.gateway.platforms.slack import SlackAdapter
from dream.gateway.platforms.webhook import WebhookAdapter
from dream.gateway.session import GatewaySessionStore
from dream.gateway.types import (
    ButtonOption,
    DeliveryTarget,
    GatewayStatus,
    IncomingMessage,
    InteractivePrompt,
    OutgoingMessage,
    PlatformType,
)
from dream.memory import MemoryStore


class MockAdapter(BasePlatformAdapter):
    """Mock platform adapter for testing gateway message flows."""

    def __init__(self, platform: PlatformType = PlatformType.TELEGRAM) -> None:
        super().__init__(platform)
        self.sent_messages: list[OutgoingMessage] = []
        self.interactive_prompts: list[tuple[str, InteractivePrompt]] = []

    def connect(self) -> bool:
        self.is_connected = True
        return True

    def disconnect(self) -> None:
        self.is_connected = False

    def send_message(self, message: OutgoingMessage) -> bool:
        self.sent_messages.append(message)
        return True

    def send_interactive_prompt(self, target_id: str, prompt: InteractivePrompt) -> bool:
        self.interactive_prompts.append((target_id, prompt))
        return True


def test_gateway_types_and_delivery_target():
    """Verify data models and target string serialization."""
    target = DeliveryTarget(
        platform=PlatformType.TELEGRAM,
        recipient_id="123456",
        channel_id="-100987654",
    )
    assert target.to_key() == "telegram:123456:-100987654"

    msg = IncomingMessage(
        message_id="msg_001",
        platform=PlatformType.DISCORD,
        sender_id="user_88",
        sender_name="Alice",
        text="Hello Dream",
    )
    assert msg.target.platform == PlatformType.DISCORD
    assert msg.target.recipient_id == "user_88"


def test_gateway_session_store_in_memory():
    """Verify session store lifecycle in memory."""
    store = GatewaySessionStore()
    sess = store.get_or_create_session(
        platform=PlatformType.SLACK,
        user_id="U1234",
        user_name="Bob",
        auto_pair=False,
    )
    assert sess.user_id == "U1234"
    assert sess.is_paired is False

    # Mark paired
    paired = store.mark_paired(PlatformType.SLACK, "U1234")
    assert paired is True

    updated_sess = store.get_or_create_session(
        platform=PlatformType.SLACK,
        user_id="U1234",
        user_name="Bob",
    )
    assert updated_sess.is_paired is True


def test_gateway_session_store_sqlite_persistence(tmp_path):
    """Verify session store persistence in SQLite."""
    db_file = str(tmp_path / "gateway_sessions.db")
    store = GatewaySessionStore(db_path=db_file)

    sess = store.get_or_create_session(
        platform=PlatformType.TELEGRAM,
        user_id="998877",
        user_name="Ali",
        auto_pair=True,
    )
    assert sess.is_paired is True

    # Re-open store from SQLite file
    store2 = GatewaySessionStore(db_path=db_file)
    sess2 = store2.get_or_create_session(
        platform=PlatformType.TELEGRAM,
        user_id="998877",
        user_name="Ali",
    )
    assert sess2.is_paired is True
    assert sess2.user_name == "Ali"


def test_pairing_manager_lifecycle():
    """Verify generation, expiry, and redemption of pairing codes."""
    pm = PairingManager(ttl_minutes=5)
    code = pm.generate_code(PlatformType.TELEGRAM, "user_1", "User One")
    assert code.startswith("DREAM-")

    # Redeem valid code
    success, record, msg = pm.verify_and_redeem(code)
    assert success is True
    assert record is not None
    assert record.user_id == "user_1"
    assert "تایید شد" in msg

    # Re-redeem already used code
    success2, record2, msg2 = pm.verify_and_redeem(code)
    assert success2 is False
    assert "قبلاً استفاده شده" in msg2

    # Invalid code
    success3, _, msg3 = pm.verify_and_redeem("INVALID_CODE")
    assert success3 is False
    assert "نامعتبر" in msg3


def test_gateway_hook_manager():
    """Verify hook subscription, execution, and error isolation."""
    hm = GatewayHookManager()
    events = []

    def hook1(msg):
        events.append(f"hook1:{msg.text}")

    def failing_hook(msg):
        raise ValueError("Hook crashed intentionally")

    hm.register("message_received", hook1)
    hm.register("message_received", failing_hook)

    test_msg = IncomingMessage(
        message_id="1",
        platform=PlatformType.TELEGRAM,
        sender_id="u1",
        sender_name="n1",
        text="test payload",
    )
    hm.on_message_received(test_msg)

    assert events == ["hook1:test payload"]

    # Unregister
    hm.unregister("message_received", hook1)
    events.clear()
    hm.on_message_received(test_msg)
    assert events == []


def test_gateway_delivery_router():
    """Verify queue delivery, immediate send, and broadcast."""
    router = GatewayDeliveryRouter(max_retries=2)
    adapter = MockAdapter(PlatformType.DISCORD)
    router.register_adapter(PlatformType.DISCORD, adapter)
    router.start()

    # Send text
    router.send_text(
        platform=PlatformType.DISCORD,
        recipient_id="ch_123",
        text="Broadcast Hello",
        immediate=True,
    )
    assert len(adapter.sent_messages) == 1
    assert adapter.sent_messages[0].text == "Broadcast Hello"

    # Broadcast
    targets = [
        DeliveryTarget(PlatformType.DISCORD, "user_a"),
        DeliveryTarget(PlatformType.DISCORD, "user_b"),
    ]
    count = router.broadcast("Alert Notice", targets)
    assert count == 2

    router.stop()


def test_gateway_hub_pairing_and_turn_flow(tmp_path):
    """Verify full end-to-end flow: pairing handshake, slash command, and conversation turn."""
    mem_store = MemoryStore(":memory:")
    hub = GatewayHub(memory_store=mem_store, auto_pair=False)
    adapter = MockAdapter(PlatformType.TELEGRAM)
    hub.register_adapter(adapter)
    hub.start()

    # Step 1: Unpaired user sends message -> receives pairing code
    incoming1 = IncomingMessage(
        message_id="m1",
        platform=PlatformType.TELEGRAM,
        sender_id="tg_100",
        sender_name="Reza",
        text="سلام دستیار",
    )
    hub.handle_incoming_message(incoming1)
    assert len(adapter.sent_messages) == 1
    assert "کد اتصال" in adapter.sent_messages[0].text
    assert "DREAM-" in adapter.sent_messages[0].text

    # Extract pairing code from message
    msg_text = adapter.sent_messages[0].text
    code = [w.strip("`") for w in msg_text.split() if "DREAM-" in w][0]

    # Step 2: Send pairing redemption
    adapter.sent_messages.clear()
    incoming2 = IncomingMessage(
        message_id="m2",
        platform=PlatformType.TELEGRAM,
        sender_id="tg_100",
        sender_name="Reza",
        text=f"/pair {code}",
    )
    hub.handle_incoming_message(incoming2)
    assert len(adapter.sent_messages) == 1
    assert "تایید شد" in adapter.sent_messages[0].text

    # Step 3: Paired user executes slash command /stats
    adapter.sent_messages.clear()
    incoming3 = IncomingMessage(
        message_id="m3",
        platform=PlatformType.TELEGRAM,
        sender_id="tg_100",
        sender_name="Reza",
        text="/stats",
    )
    hub.handle_incoming_message(incoming3)
    assert len(adapter.sent_messages) == 1
    assert "Total Memories:" in adapter.sent_messages[0].text

    # Step 4: Paired user sends conversational prompt
    adapter.sent_messages.clear()
    incoming4 = IncomingMessage(
        message_id="m4",
        platform=PlatformType.TELEGRAM,
        sender_id="tg_100",
        sender_name="Reza",
        text="اسم پایتخت فرانسه چیست؟",
    )
    hub.handle_incoming_message(incoming4)
    assert len(adapter.sent_messages) == 1
    assert len(adapter.sent_messages[0].text) > 0

    hub.stop()


def test_gateway_hub_approval_request():
    """Verify security approval prompt generation and interaction handling."""
    hub = GatewayHub(auto_pair=True)
    adapter = MockAdapter(PlatformType.TELEGRAM)
    hub.register_adapter(adapter)

    prompt_id = hub.request_approval(
        platform=PlatformType.TELEGRAM,
        recipient_id="admin_user",
        tool_name="terminal_tool",
        command_preview="rm -rf /tmp/test",
    )
    assert prompt_id.startswith("appr_")
    assert len(adapter.interactive_prompts) == 1
    target, prompt = adapter.interactive_prompts[0]
    assert target == "admin_user"
    assert len(prompt.options) == 3
    assert any(o.label_en == "Allow Once" for o in prompt.options)

    # Handle approval interaction callback
    adapter.sent_messages.clear()
    hub.handle_interaction({
        "platform": "telegram",
        "sender_id": "admin_user",
        "payload": f"approve_once:{prompt_id}",
    })
    assert len(adapter.sent_messages) == 1
    assert "تایید شد" in adapter.sent_messages[0].text


def test_webhook_adapter_hmac_and_post():
    """Verify Webhook adapter HMAC signature calculation and verification."""
    adapter = WebhookAdapter(secret_key="my_secret_token_123")
    payload = b'{"sender_id": "iot_sensor", "text": "temperature 28C"}'
    sig = adapter.sign_payload(payload)
    assert len(sig) == 64
    assert adapter.verify_signature(payload, sig) is True
    assert adapter.verify_signature(payload, "invalid_signature") is False


def test_slack_block_kit_construction():
    """Verify Slack adapter Block Kit construction."""
    adapter = SlackAdapter(webhook_url="https://hooks.slack.com/services/test")
    prompt = InteractivePrompt(
        prompt_id="p1",
        title="Security Confirmation",
        description="Do you authorize data export?",
        options=[
            ButtonOption("btn1", "Yes", "بله", "approve", style="primary"),
            ButtonOption("btn2", "No", "خیر", "deny", style="danger"),
        ],
    )
    blocks = adapter._build_block_kit(prompt)
    assert len(blocks) == 2
    assert blocks[0]["type"] == "section"
    assert blocks[1]["type"] == "actions"
    assert len(blocks[1]["elements"]) == 2


def test_discord_action_row_construction():
    """Verify Discord adapter action row generation."""
    adapter = DiscordAdapter(webhook_url="https://discord.com/api/webhooks/test")
    options = [
        ButtonOption("b1", "Confirm", "تایید", "confirm_payload", style="primary"),
        ButtonOption("b2", "Cancel", "انصراف", "cancel_payload", style="danger"),
    ]
    rows = adapter._build_action_rows(options)
    assert len(rows) == 1
    assert rows[0]["type"] == 1
    assert len(rows[0]["components"]) == 2
    assert rows[0]["components"][0]["custom_id"] == "confirm_payload"


def test_gateway_hub_telemetry_status():
    """Verify GatewayStatus metrics."""
    hub = GatewayHub(auto_pair=True)
    adapter = MockAdapter(PlatformType.TELEGRAM)
    hub.register_adapter(adapter)
    hub.start()

    status = hub.get_status()
    assert isinstance(status, GatewayStatus)
    assert status.is_running is True
    assert PlatformType.TELEGRAM in status.active_platforms
    assert "telegram" in status.platform_details

    hub.stop()
