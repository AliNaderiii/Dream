"""Tests for Desktop Live Voice Bridge, Telephony VoIP Gateway, and Visual Stream Ingestion."""

from __future__ import annotations

import asyncio
import base64
import json
import struct

import pytest

from dream.duplex.desktop_bridge import DesktopVoiceBridge
from dream.telephony.engine import (
    TelephonyEngine,
    reset_global_telephony_engine,
)
from dream.telephony.sip_adapter import SIPAdapter
from dream.telephony.slash import handle_telephony_command
from dream.telephony.tools import (
    telephony_export_call_record,
    telephony_get_call_status,
    telephony_hangup_call,
    telephony_initiate_call,
)
from dream.telephony.twilio_gateway import TwilioMediaGateway
from dream.telephony.types import CallDirection, CallStatus, TelephonyCallRecord
from dream.tools.toolsets import get_toolset
from dream.vision.multimodal_sync import MultiModalStreamSynchronizer
from dream.vision.slash import handle_vision_command
from dream.vision.stream_engine import RealtimeVisualStreamEngine
from dream.vision.tools import (
    vision_get_multimodal_context,
    vision_ingest_stream_frame,
    vision_query_live_stream,
    vision_start_live_stream,
    vision_stop_live_stream,
)


@pytest.fixture(autouse=True)
def cleanup():
    reset_global_telephony_engine()
    yield
    reset_global_telephony_engine()


# ==============================================================================
# 1. Desktop Voice Bridge & Visualizer Tests
# ==============================================================================

def test_desktop_voice_bridge_lifecycle_and_visualizer():
    """Test desktop audio stream bridge and waveform computation."""
    async def _run():
        bridge = DesktopVoiceBridge(session_id="test-desktop-session")
        res_start = await bridge.start()
        assert res_start["status"] == "connected"
        assert bridge.is_active is True

        # Process mic chunk
        pcm = struct.pack("<320h", *([1200] * 320))
        b64_pcm = base64.b64encode(pcm).decode("ascii")
        res_chunk = await bridge.process_incoming_mic_chunk(b64_pcm)

        assert res_chunk["status"] == "ok"
        assert "visualizer" in res_chunk
        v = res_chunk["visualizer"]
        assert v["rms_volume"] > 0.0
        assert len(v["waveform_peaks"]) == 16
        assert len(v["frequency_bins"]) == 8

        # Query visualizer
        latest = bridge.get_latest_visualizer()
        assert "rms_volume" in latest

        # Stop
        res_stop = await bridge.stop()
        assert res_stop["status"] == "disconnected"
        assert bridge.is_active is False

    asyncio.run(_run())


# ==============================================================================
# 2. Telephony Engine, Twilio Media Stream & SIP Gateway Tests
# ==============================================================================

def test_telephony_outbound_and_inbound_calls():
    """Test initiating outbound phone calls and processing inbound webhooks."""
    engine = TelephonyEngine()

    # Outbound call
    call = engine.initiate_outbound_call(to_number="+989120000000")
    assert call.to_number == "+989120000000"
    assert call.status == CallStatus.IN_PROGRESS
    assert call.direction == CallDirection.OUTBOUND

    # Inbound call
    in_call, twiml = engine.handle_inbound_webhook(
        from_number="+989121111111", to_number="+982191000000"
    )
    assert in_call.direction == CallDirection.INBOUND
    assert "<Stream" in twiml

    # Hangup
    assert engine.hangup_call(call.call_id) is True
    assert call.status == CallStatus.COMPLETED
    assert call.duration_sec >= 0.0

    # Export report
    report = engine.export_call_record(call.call_id, format="markdown")
    assert "گزارش تماس صوتی" in report


def test_twilio_media_streams_gateway():
    """Test bi-directional Twilio WebSocket audio transcoding and events."""
    record = TelephonyCallRecord(
        call_id="call-tw-123",
        from_number="+123456789",
        to_number="+987654321",
    )
    gw = TwilioMediaGateway(record)

    # 1. Start event
    start_payload = json.dumps({"event": "start", "streamSid": "MZ12345"})
    res1 = gw.handle_twilio_message(start_payload)
    assert len(res1) == 1
    assert res1[0]["event"] == "mark"
    assert gw.is_connected is True

    # 2. Media event (mulaw audio)
    fake_mulaw = b"\xFF\x80" * 160
    media_payload = json.dumps({
        "event": "media",
        "streamSid": "MZ12345",
        "media": {"payload": base64.b64encode(fake_mulaw).decode("utf-8")},
    })
    gw.handle_twilio_message(media_payload)

    # 3. DTMF event
    dtmf_payload = json.dumps({"event": "dtmf", "dtmf": {"digit": "5"}})
    gw.handle_twilio_message(dtmf_payload)
    assert record.dtmf_digits == "5"

    # 4. Outbound media synthesis
    out_pcm = struct.pack("<320h", *([500] * 320))
    media_msg = gw.synthesize_outbound_media(out_pcm)
    assert media_msg["event"] == "media"
    assert "payload" in media_msg["media"]

    # 5. Clear message (barge-in)
    clear_msg = gw.create_clear_message()
    assert clear_msg["event"] == "clear"


def test_sip_adapter_dialog_lifecycle():
    """Test SIP INVITE and BYE signaling emulation."""
    sip = SIPAdapter()
    record, headers = sip.handle_invite(
        from_uri="sip:alice@domain.com",
        to_uri="sip:dream@domain.com",
    )
    assert record.status == CallStatus.IN_PROGRESS
    assert headers["Status"] == "SIP/2.0 200 OK"

    assert sip.handle_bye(record.call_id) is True
    assert record.status == CallStatus.COMPLETED


def test_telephony_tools_and_slash():
    """Test Telephony LLM tools and /call slash commands."""
    async def _run():
        # Tools
        res_call = await telephony_initiate_call(to_number="+989129999999")
        assert res_call["success"] is True
        call_id = res_call["call"]["call_id"]

        res_status = await telephony_get_call_status(call_id)
        assert res_status["success"] is True

        res_hang = await telephony_hangup_call(call_id)
        assert res_hang["success"] is True

        res_rec = await telephony_export_call_record(call_id)
        assert res_rec["success"] is True

        # Slash commands
        help_out = await handle_telephony_command("")
        assert "راهنمای دستورات تلفن" in help_out

        dial_out = await handle_telephony_command("dial +989125555555")
        assert "تماس برقرار شد" in dial_out

        list_out = await handle_telephony_command("list")
        assert "لیست تماس‌های اخیر" in list_out

    asyncio.run(_run())


# ==============================================================================
# 3. Realtime Visual Stream Ingestion & Multi-Modal Sync Tests
# ==============================================================================

def test_visual_stream_engine_ingestion_and_context():
    """Test continuous screen frame ingestion and optical delta extraction."""
    engine = RealtimeVisualStreamEngine()
    res_start = engine.start_stream("screen-test")
    assert res_start["status"] == "active"

    # Ingest frames
    fake_frame_b64 = base64.b64encode(b"PNG_DATA_STREAM_SIMULATION").decode("utf-8")
    frame1 = engine.ingest_frame("screen-test", fake_frame_b64, 1920, 1080)
    assert frame1.frame_id.startswith("frm_")

    # Query context
    ctx = engine.query_recent_visual_context("screen-test", window_sec=3.0)
    assert ctx["frames_analyzed"] >= 1
    assert len(ctx["visible_texts"]) > 0

    assert engine.stop_stream("screen-test") is True


def test_multimodal_audio_visual_synchronization():
    """Test synchronizing conversational speech with live screen frames."""
    sync = MultiModalStreamSynchronizer()
    ctx = sync.get_unified_multimodal_context()
    assert "multimodal_reasoning_prompt" in ctx
    assert "visual_context" in ctx
    assert "duplex_state" in ctx


def test_vision_streaming_tools_and_slash():
    """Test Vision streaming tools and slash commands."""
    res_start = vision_start_live_stream("screen-live-tool")
    assert res_start["success"] is True

    fake_b64 = base64.b64encode(b"SAMPLE_FRAME_DATA").decode("utf-8")
    res_ingest = vision_ingest_stream_frame("screen-live-tool", fake_b64)
    assert res_ingest["success"] is True

    res_query = vision_query_live_stream("screen-live-tool")
    assert res_query["success"] is True

    res_mm = vision_get_multimodal_context(visual_stream_id="screen-live-tool")
    assert res_mm["success"] is True

    res_stop = vision_stop_live_stream("screen-live-tool")
    assert res_stop["success"] is True

    # Slash
    help_out = handle_vision_command("")
    assert "راهنمای دستورات بینایی" in help_out

    stream_start_out = handle_vision_command("stream start")
    assert "فعال شد" in stream_start_out

    stream_sync_out = handle_vision_command("stream sync")
    assert "همگام‌سازی صوت و تصویر" in stream_sync_out


def test_toolset_manifests_include_telephony_and_vision_streaming():
    """Verify toolsets contain all new telephony and visual stream tools."""
    ts_telephony = get_toolset("telephony")
    assert ts_telephony is not None
    assert "telephony_initiate_call" in ts_telephony.tools
    assert "telephony_hangup_call" in ts_telephony.tools

    ts_vision = get_toolset("vision")
    assert ts_vision is not None
    assert "vision_start_live_stream" in ts_vision.tools
    assert "vision_get_multimodal_context" in ts_vision.tools
