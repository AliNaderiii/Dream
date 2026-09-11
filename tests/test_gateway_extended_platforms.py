"""Tests for extended platform adapters in Universal Gateway (Matrix, WhatsApp, Email, Signal)."""

from __future__ import annotations

from dream.gateway import (
    ButtonOption,
    DeliveryTarget,
    EmailAdapter,
    GatewayHub,
    InteractivePrompt,
    MatrixAdapter,
    OutgoingMessage,
    PlatformType,
    SignalAdapter,
    WhatsAppAdapter,
)


def test_matrix_adapter_lifecycle():
    received = []
    adapter = MatrixAdapter(
        homeserver_url="https://matrix.org",
        user_id="@bot:matrix.org",
        message_handler=received.append,
    )

    assert adapter.connect() is True
    assert adapter.is_connected is True

    # Parse inbound message
    event = {
        "event_id": "$12345",
        "sender": "@user:matrix.org",
        "room_id": "!room:matrix.org",
        "content": {"body": "Hello Matrix"},
    }
    msg = adapter.parse_inbound_event(event)
    assert msg is not None
    assert msg.text == "Hello Matrix"
    assert msg.platform == PlatformType.MATRIX
    assert len(received) == 1

    # Outbound message
    out = OutgoingMessage(
        target=DeliveryTarget(PlatformType.MATRIX, "@user:matrix.org", "!room:matrix.org"),
        text="Reply Matrix",
    )
    assert adapter.send_message(out) is True

    # Interactive prompt
    prompt = InteractivePrompt(
        prompt_id="p1",
        title="Confirm",
        description="Proceed?",
        options=[ButtonOption("yes", "Yes", "بله", "yes")],
    )
    assert adapter.send_interactive_prompt("!room:matrix.org", prompt) is True

    health = adapter.health_check()
    assert health["connected"] is True
    assert health["sent_count"] == 2

    adapter.disconnect()
    assert adapter.is_connected is False


def test_whatsapp_adapter_lifecycle():
    received = []
    adapter = WhatsAppAdapter(
        phone_number_id="123456",
        message_handler=received.append,
    )
    assert adapter.connect() is True

    # Webhook payload parsing
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": "989120000000", "profile": {"name": "Ali"}}],
                            "messages": [
                                {
                                    "id": "wa_001",
                                    "from": "989120000000",
                                    "type": "text",
                                    "text": {"body": "سلام از واتساپ"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    msgs = adapter.parse_webhook_payload(payload)
    assert len(msgs) == 1
    assert msgs[0].text == "سلام از واتساپ"
    assert msgs[0].sender_name == "Ali"
    assert len(received) == 1

    # Outbound message
    out = OutgoingMessage(
        target=DeliveryTarget(PlatformType.WHATSAPP, "989120000000"),
        text="پاسخ به واتساپ",
    )
    assert adapter.send_message(out) is True

    # Interactive prompt
    prompt = InteractivePrompt(
        prompt_id="p2",
        title="تایید عملیات",
        description="آیا تایید میکنید؟",
        options=[
            ButtonOption("approve", "Approve", "تایید", "approve"),
            ButtonOption("cancel", "Cancel", "لغو", "cancel"),
        ],
    )
    assert adapter.send_interactive_prompt("989120000000", prompt) is True

    health = adapter.health_check()
    assert health["connected"] is True
    assert health["sent_count"] == 2

    adapter.disconnect()
    assert adapter.is_connected is False


def test_email_adapter_lifecycle():
    received = []
    adapter = EmailAdapter(
        sender_email="dream@example.com",
        message_handler=received.append,
    )
    assert adapter.connect() is True

    email_data = {
        "message_id": "em_001",
        "from": "User <user@example.com>",
        "subject": "Task Update",
        "body": "Please process the report.",
    }
    msg = adapter.parse_inbound_email(email_data)
    assert msg is not None
    assert "Task Update" in msg.text
    assert msg.platform == PlatformType.EMAIL
    assert len(received) == 1

    out = OutgoingMessage(
        target=DeliveryTarget(PlatformType.EMAIL, "user@example.com"),
        text="Report processed successfully.",
    )
    assert adapter.send_message(out) is True

    prompt = InteractivePrompt(
        prompt_id="p3",
        title="Approve Deployment",
        description="Deploy to production?",
        options=[ButtonOption("yes", "Yes", "بله", "yes")],
    )
    assert adapter.send_interactive_prompt("user@example.com", prompt) is True

    health = adapter.health_check()
    assert health["connected"] is True
    assert health["sent_count"] == 2

    adapter.disconnect()
    assert adapter.is_connected is False


def test_signal_adapter_lifecycle():
    received = []
    adapter = SignalAdapter(
        phone_number="+989123456789",
        message_handler=received.append,
    )
    assert adapter.connect() is True

    payload = {
        "envelope": {
            "source": "+989123456789",
            "sourceName": "Tester",
            "dataMessage": {
                "message": "Secure ping",
                "timestamp": 1700000000000,
            },
        }
    }
    msg = adapter.parse_inbound_signal(payload)
    assert msg is not None
    assert msg.text == "Secure ping"
    assert msg.platform == PlatformType.SIGNAL
    assert len(received) == 1

    out = OutgoingMessage(
        target=DeliveryTarget(PlatformType.SIGNAL, "+989123456789"),
        text="Secure pong",
    )
    assert adapter.send_message(out) is True

    prompt = InteractivePrompt(
        prompt_id="p4",
        title="2FA Code",
        description="Verify login",
        options=[ButtonOption("allow", "Allow", "اجازه", "allow")],
    )
    assert adapter.send_interactive_prompt("+989123456789", prompt) is True

    health = adapter.health_check()
    assert health["connected"] is True
    assert health["sent_count"] == 2

    adapter.disconnect()
    assert adapter.is_connected is False


def test_gateway_hub_multiplatform_routing():
    hub = GatewayHub()

    mat = MatrixAdapter()
    wa = WhatsAppAdapter()
    em = EmailAdapter()
    sig = SignalAdapter()

    hub.register_adapter(mat)
    hub.register_adapter(wa)
    hub.register_adapter(em)
    hub.register_adapter(sig)

    assert hub.start() is True

    status = hub.get_status()
    assert PlatformType.MATRIX in status.active_platforms
    assert PlatformType.WHATSAPP in status.active_platforms
    assert PlatformType.EMAIL in status.active_platforms
    assert PlatformType.SIGNAL in status.active_platforms

    # Deliver to each platform
    msg_mat = OutgoingMessage(
        target=DeliveryTarget(PlatformType.MATRIX, "@u:m.org", "!r:m.org"),
        text="hi matrix",
    )
    assert hub.delivery_router.send(msg_mat, immediate=True) is True

    msg_wa = OutgoingMessage(
        target=DeliveryTarget(PlatformType.WHATSAPP, "12345"),
        text="hi wa",
    )
    assert hub.delivery_router.send(msg_wa, immediate=True) is True

    msg_em = OutgoingMessage(
        target=DeliveryTarget(PlatformType.EMAIL, "a@b.com"),
        text="hi email",
    )
    assert hub.delivery_router.send(msg_em, immediate=True) is True

    msg_sig = OutgoingMessage(
        target=DeliveryTarget(PlatformType.SIGNAL, "+123"),
        text="hi signal",
    )
    assert hub.delivery_router.send(msg_sig, immediate=True) is True

    hub.stop()
    assert hub.is_running is False
