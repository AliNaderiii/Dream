"""Tests for Ultra Low-Latency Voice Duplex Pipeline and OpenAI-Compatible Realtime Gateway."""

from __future__ import annotations

import asyncio
import base64
import struct

import pytest

from dream.duplex.realtime_gateway import (
    RealtimeClientSession,
    RealtimeEventType,
    RealtimeGatewayServer,
)
from dream.duplex.slash import handle_duplex_command
from dream.duplex.tools import (
    duplex_export_transcript,
    duplex_get_session_metrics,
    duplex_inject_interruption,
    duplex_push_audio_frame,
    duplex_reset_session,
    duplex_start_session,
    get_duplex_tools,
    reset_global_duplex_engine,
    voice_realtime_server_start,
    voice_speech_adapter_benchmark,
    voice_speech_adapter_list,
    voice_speech_adapter_select,
)
from dream.speech.adapters import (
    FasterWhisperSTTAdapter,
    KokoroTTSAdapter,
    ParakeetTDTAdapter,
    Qwen3GGMLTTSAdapter,
    SileroVADv5Adapter,
    SpeechAdapterKind,
    SpeechAdapterRegistry,
)
from dream.speech.types import STTRequest, TTSRequest
from dream.tools.toolsets import get_toolset


@pytest.fixture(autouse=True)
def cleanup():
    reset_global_duplex_engine()
    yield
    reset_global_duplex_engine()


# ==============================================================================
# 1. Speech Adapters & Registry Tests
# ==============================================================================

def test_speech_adapter_registry_discovery():
    """Verify registry discovers and registers default adapters."""
    registry = SpeechAdapterRegistry()
    adapters = registry.list_adapters()
    assert len(adapters) >= 5

    names = [a["name"] for a in adapters]
    assert any("Kokoro" in n for n in names)
    assert any("Qwen3" in n for n in names)
    assert any("Parakeet" in n for n in names)
    assert any("Whisper" in n for n in names)
    assert any("Silero" in n for n in names)


def test_kokoro_tts_adapter_synthesis():
    """Test Kokoro-82M lightweight synthesis with formant audio output."""
    adapter = KokoroTTSAdapter()
    caps = adapter.get_capabilities()
    assert caps.is_tts is True
    assert caps.model_size_mb == 82.0
    assert "fa" in caps.supported_languages

    req = TTSRequest(text="درود بر دریم", speed=1.2, pitch=1.1, sample_rate=24000)
    result = adapter.synthesize(req)
    assert result.duration_seconds > 0.0
    assert result.sample_rate == 24000
    assert len(result.audio_bytes) > 100
    assert len(result.phonemes) > 0
    assert result.metadata["engine"] == "Kokoro-82M"


def test_qwen3_ggml_tts_adapter_synthesis():
    """Test Qwen3-TTS quantized GGML engine synthesis."""
    adapter = Qwen3GGMLTTSAdapter()
    caps = adapter.get_capabilities()
    assert caps.is_tts is True
    assert caps.kind == SpeechAdapterKind.QWEN3_GGML

    req = TTSRequest(text="سیستم صوتی فعال شد.", sample_rate=16000)
    result = adapter.synthesize(req)
    assert result.duration_seconds > 0.0
    assert result.sample_rate == 16000
    assert len(result.audio_bytes) > 0
    assert result.metadata["engine"] == "Qwen3-TTS-GGML"


def test_parakeet_tdt_stt_transcription():
    """Test Parakeet-TDT streaming speech recognition adapter."""
    adapter = ParakeetTDTAdapter()
    caps = adapter.get_capabilities()
    assert caps.is_stt is True
    assert caps.supports_streaming is True

    req = STTRequest(audio_path="/fake/voice.wav", language="fa")
    res = adapter.transcribe(req)
    assert res.text != ""
    assert res.language == "fa"
    assert res.confidence >= 0.9
    assert len(res.segments) >= 1
    assert res.metadata["engine"] == "Parakeet-TDT-0.6B"


def test_faster_whisper_stt_transcription():
    """Test Faster-Whisper ASR adapter."""
    adapter = FasterWhisperSTTAdapter()
    caps = adapter.get_capabilities()
    assert caps.is_stt is True
    assert "ar" in caps.supported_languages

    req = STTRequest(audio_path="/fake/audio.wav", language="en")
    res = adapter.transcribe(req)
    assert "voice command" in res.text
    assert res.language == "en"
    assert res.confidence > 0.9


def test_silero_vad_v5_probability_scoring():
    """Test Silero VAD v5 frame slicing and neural energy thresholding."""
    adapter = SileroVADv5Adapter()
    caps = adapter.get_capabilities()
    assert caps.is_vad is True
    assert caps.latency_profile_ms <= 5.0

    silence_pcm = struct.pack("<512h", *([10] * 512))
    prob_silence = adapter.process_vad_frame(silence_pcm)
    assert prob_silence < 0.2

    speech_pcm = struct.pack("<512h", *([3500] * 512))
    prob_speech = adapter.process_vad_frame(speech_pcm)
    assert prob_speech > 0.7


def test_speech_adapter_switching_and_benchmark():
    """Test switching active adapters and running latency benchmarks."""
    registry = SpeechAdapterRegistry()

    assert registry.set_active_tts("qwen3_ggml") is True
    assert registry.set_active_tts("non_existent") is False
    assert registry.set_active_stt("faster_whisper") is True
    assert registry.set_active_vad("silero_vad_v5") is True

    benchmarks = registry.benchmark_adapters()
    assert len(benchmarks) >= 5
    for b in benchmarks:
        assert "measured_latency_ms" in b
        assert b["status"] == "ok"


# ==============================================================================
# 2. OpenAI Realtime Gateway & Session Lifecycle Tests
# ==============================================================================

def test_realtime_session_creation_and_config():
    """Test OpenAI Realtime session creation and session.update handling."""
    async def _run():
        session = RealtimeClientSession()
        evt = session.create_session_created_event()
        assert evt["type"] == RealtimeEventType.SESSION_CREATED.value
        assert evt["session"]["model"] == "dream-v3-realtime"
        assert evt["session"]["voice"] == "fa-mina"

        update_event = {
            "type": RealtimeEventType.SESSION_UPDATE.value,
            "session": {
                "instructions": "پاسخ‌های کوتاه ارائه بده.",
                "voice": "fa-nima",
                "temperature": 0.5,
            },
        }
        out = await session.handle_event(update_event)
        assert len(out) == 1
        assert out[0]["type"] == RealtimeEventType.SESSION_UPDATED.value
        assert session.config.voice == "fa-nima"
        assert session.config.temperature == 0.5

    asyncio.run(_run())


def test_realtime_audio_append_and_commit():
    """Test appending base64 audio chunks and committing input audio buffer."""
    async def _run():
        session = RealtimeClientSession()

        pcm_silence = struct.pack("<256h", *([5] * 256))
        b64_audio = base64.b64encode(pcm_silence).decode("utf-8")
        append_evt = {
            "type": RealtimeEventType.INPUT_AUDIO_BUFFER_APPEND.value,
            "audio": b64_audio,
        }
        await session.handle_event(append_evt)
        assert len(session.audio_buffer) == len(pcm_silence)

        commit_evt = {"type": RealtimeEventType.INPUT_AUDIO_BUFFER_COMMIT.value}
        out_events = await session.handle_event(commit_evt)

        types = [e["type"] for e in out_events]
        assert RealtimeEventType.INPUT_AUDIO_BUFFER_COMMITTED.value in types
        assert RealtimeEventType.CONVERSATION_ITEM_CREATED.value in types
        assert len(session.audio_buffer) == 0
        assert len(session.conversation_items) == 1

    asyncio.run(_run())


def test_realtime_response_streaming_and_audio_delta():
    """Test generating streaming text tokens and base64 audio deltas."""
    async def _run():
        session = RealtimeClientSession()
        resp_evt = {"type": RealtimeEventType.RESPONSE_CREATE.value}
        out_events = await session.handle_event(resp_evt)

        types = [e["type"] for e in out_events]
        assert RealtimeEventType.RESPONSE_CREATED.value in types
        assert RealtimeEventType.RESPONSE_OUTPUT_ITEM_ADDED.value in types
        assert RealtimeEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA.value in types
        assert RealtimeEventType.RESPONSE_AUDIO_DELTA.value in types
        assert RealtimeEventType.RESPONSE_AUDIO_TRANSCRIPT_DONE.value in types
        assert RealtimeEventType.RESPONSE_AUDIO_DONE.value in types
        assert RealtimeEventType.RESPONSE_DONE.value in types

    asyncio.run(_run())


def test_realtime_barge_in_and_cancellation():
    """Test immediate cancellation on response.cancel or user speech barge-in."""
    async def _run():
        session = RealtimeClientSession()
        session.is_speaking = True
        session.active_response_id = "resp_test123"

        cancel_evt = {"type": RealtimeEventType.RESPONSE_CANCEL.value}
        out_events = await session.handle_event(cancel_evt)

        assert len(out_events) == 1
        assert out_events[0]["type"] == RealtimeEventType.RESPONSE_DONE.value
        assert out_events[0]["response"]["status"] == "cancelled"
        assert session.is_speaking is False
        assert session.active_response_id is None

    asyncio.run(_run())


def test_realtime_gateway_server_management():
    """Test RealtimeGatewayServer multi-session tracking and start/stop."""
    server = RealtimeGatewayServer(host="127.0.0.1", port=9999)
    res_start = server.start_server()
    assert res_start["status"] == "running"
    assert "ws://127.0.0.1:9999/v1/realtime" in res_start["endpoint_ws"]

    sess1 = server.create_session()
    server.create_session()
    assert len(server.list_active_sessions()) == 2
    assert server.get_session(sess1.session_id) is not None

    assert server.close_session(sess1.session_id) is True
    assert len(server.list_active_sessions()) == 1

    res_stop = server.stop_server()
    assert res_stop["status"] == "stopped"
    assert len(server.list_active_sessions()) == 0


# ==============================================================================
# 3. Duplex Tools & Slash Command Integration Tests
# ==============================================================================

def test_duplex_tools_execution():
    """Test tool handlers for duplex and realtime gateway."""
    async def _run():
        res_start = await duplex_start_session(session_id="duplex-test-1", sample_rate=24000)
        assert res_start["success"] is True

        fake_pcm_b64 = base64.b64encode(b"\x20\x30" * 320).decode("utf-8")
        res_push = await duplex_push_audio_frame(
            session_id="duplex-test-1", base64_pcm=fake_pcm_b64, user_text="سلام دستیار"
        )
        assert res_push["success"] is True

        res_intr = await duplex_inject_interruption(session_id="duplex-test-1")
        assert res_intr["success"] is True

        res_met = await duplex_get_session_metrics(session_id="duplex-test-1")
        assert res_met["success"] is True
        assert "metrics" in res_met

        res_tr = await duplex_export_transcript(session_id="duplex-test-1", format="markdown")
        assert res_tr["success"] is True
        assert "Duplex Audio Transcript" in res_tr["transcript_markdown"]

        res_srv = await voice_realtime_server_start(port=8888)
        assert res_srv["success"] is True

        res_list = await voice_speech_adapter_list()
        assert res_list["success"] is True
        assert res_list["total_adapters"] >= 5

        res_bench = await voice_speech_adapter_benchmark()
        assert res_bench["success"] is True
        assert len(res_bench["results"]) >= 5

        res_sel = await voice_speech_adapter_select(adapter_kind="kokoro", role="tts")
        assert res_sel["success"] is True

        res_rst = await duplex_reset_session(session_id="duplex-test-1")
        assert res_rst["success"] is True

    asyncio.run(_run())


def test_duplex_slash_command_dispatching():
    """Test /duplex slash command dispatcher with all subcommands."""
    async def _run():
        help_out = await handle_duplex_command("")
        assert "راهنمای دستورات صوتی" in help_out

        start_out = await handle_duplex_command("start sess-slash")
        assert "فعال شد" in start_out

        push_out = await handle_duplex_command("push sess-slash تست صدا")
        assert "پیام صوتی دریافت شد" in push_out

        intr_out = await handle_duplex_command("interrupt sess-slash")
        assert "قطع شد" in intr_out

        met_out = await handle_duplex_command("metrics sess-slash")
        assert "معیارهای تاخیر" in met_out

        tr_out = await handle_duplex_command("transcript sess-slash")
        assert "گزارش گفتگوی صوتی" in tr_out

        gw_status = await handle_duplex_command("realtime status")
        assert "OpenAI Realtime Gateway" in gw_status

        gw_start = await handle_duplex_command("realtime start")
        assert "سرور Realtime WebSocket فعال شد" in gw_start

        ad_list = await handle_duplex_command("adapters list")
        assert "موتورهای صوتی" in ad_list

        ad_bench = await handle_duplex_command("adapters benchmark")
        assert "نتایج بنچمارک" in ad_bench

        rst_out = await handle_duplex_command("reset sess-slash")
        assert "ریست شد" in rst_out

    asyncio.run(_run())


def test_duplex_toolset_manifest_and_registry():
    """Verify toolset registration in dream/tools/toolsets.py."""
    toolset = get_toolset("duplex")
    assert toolset is not None
    assert "voice_realtime_server_start" in toolset.tools
    assert "voice_speech_adapter_list" in toolset.tools
    assert "voice_speech_adapter_benchmark" in toolset.tools
    assert "voice_speech_adapter_select" in toolset.tools

    duplex_tools = get_duplex_tools()
    tool_names = [t["name"] for t in duplex_tools]
    assert "voice_realtime_server_start" in tool_names
    assert "voice_speech_adapter_benchmark" in tool_names
