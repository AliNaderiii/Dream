"""Comprehensive tests for Real-Time Duplex Streaming Audio Subsystem."""

from __future__ import annotations

import asyncio
import base64
import json

from dream.duplex.engine import DuplexEngine
from dream.duplex.ring_buffer import AudioRingBuffer
from dream.duplex.session import DuplexSession
from dream.duplex.slash import handle_duplex_command
from dream.duplex.tools import (
    duplex_export_transcript,
    duplex_get_session_metrics,
    duplex_inject_interruption,
    duplex_push_audio_frame,
    duplex_reset_session,
    duplex_start_session,
    get_duplex_tools,
)
from dream.duplex.types import (
    DuplexConfig,
    DuplexState,
    VADState,
)
from dream.duplex.vad import VoiceActivityDetector
from dream.tools.toolsets import get_toolset


def test_toolset_includes_duplex() -> None:
    """Verify duplex toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("duplex")
    assert ts is not None
    assert ts.name == "duplex"
    assert "duplex_start_session" in ts.tools
    assert "duplex_push_audio_frame" in ts.tools
    assert "duplex_inject_interruption" in ts.tools


def test_vad_energy_and_barge_in() -> None:
    """Test VoiceActivityDetector energy calculations and speech state tracking."""
    vad = VoiceActivityDetector(energy_threshold=0.01, hangover_ms=100)
    assert vad.current_state == VADState.SILENCE

    # 1. Silence frame (zeros)
    silence_pcm = b"\x00\x00" * 320
    frame1 = vad.process_frame(silence_pcm)
    assert frame1.energy == 0.0
    assert not frame1.is_speech
    assert vad.current_state == VADState.SILENCE

    # 2. Loud frame (simulated speech)
    loud_pcm = b"\x20\x40" * 320
    frame2 = vad.process_frame(loud_pcm)
    assert frame2.energy > 0.01
    assert frame2.is_speech
    assert vad.current_state == VADState.SPEECH_START

    # 3. Check barge in qualification
    assert vad.check_barge_in(frame2, min_speech_ms=10)


def test_audio_ring_buffer() -> None:
    """Test circular AudioRingBuffer write, read, flush, and over/underruns."""
    async def _run() -> None:
        buf = AudioRingBuffer(capacity_bytes=100)
        assert buf.available_read == 0
        assert buf.available_write == 100

        # Write 40 bytes
        written = await buf.write(b"a" * 40)
        assert written == 40
        assert buf.available_read == 40

        # Read 20 bytes
        read_data = await buf.read(20)
        assert read_data == b"a" * 20
        assert buf.available_read == 20

        # Flush remaining
        flushed = await buf.flush()
        assert flushed == b"a" * 20
        assert buf.available_read == 0

        # Read from empty buffer triggers underrun
        empty = await buf.read(10)
        assert empty == b""
        assert buf.underruns == 1

    asyncio.run(_run())


def test_duplex_session_lifecycle_and_barge_in() -> None:
    """Test DuplexSession state transitions, speech finalize, and barge-in cutoffs."""
    async def _run() -> None:
        cfg = DuplexConfig(session_id="test-session", vad_energy_threshold=0.01)
        session = DuplexSession(cfg)
        await session.start()
        assert session.state == DuplexState.LISTENING

        # 1. Push user speech frame
        speech_pcm = b"\x40\x40" * 320
        state, interrupted = await session.push_user_audio(speech_pcm)
        assert state == DuplexState.LISTENING
        assert not interrupted

        # 2. Simulate model speech stream
        tokens = ["سلام", "، ", "من ", "دستیار ", "دریم ", "هستم."]
        chunks = []
        async for chunk in session.stream_assistant_response(tokens, emotion_tag="calm"):
            chunks.append(chunk)

        assert len(chunks) == len(tokens)
        assert len(session.turns) >= 1
        assert session.turns[-1].speaker == "assistant"
        assert "دریم" in session.turns[-1].text

        # 3. Test manual interruption (Barge-in)
        session.state = DuplexState.SPEAKING
        session._current_assistant_text = "در حال توضیح مسئله طولانی..."
        await session.interrupt_manually("user_spoke")
        assert session.metrics.total_interruptions == 1
        assert session.turns[-1].interrupted is True
        assert "[قطع شد]" in session.turns[-1].text

    asyncio.run(_run())


def test_duplex_engine_and_transcripts() -> None:
    """Test DuplexEngine multi-session management and Markdown/JSON transcripts."""
    async def _run() -> None:
        engine = DuplexEngine()
        session = engine.get_or_create_session("sess-100")
        await session.start()

        # Ingest speech
        speech_pcm = b"\x40\x40" * 320
        await session.push_user_audio(speech_pcm)
        session.set_user_text("چطور می‌توانم یک ایجنت هوشمند بسازم؟")
        await session._finalize_user_speech()

        # Markdown export
        md = engine.export_transcript_markdown("sess-100")
        assert "گزارش گفتگوی صوتی بلادرنگ" in md
        assert "چطور می‌توانم یک ایجنت هوشمند بسازم؟" in md

        # JSON export
        js = engine.export_json("sess-100")
        data = json.loads(js)
        assert "transcript" in data
        assert len(data["transcript"]) >= 1

        # Close session
        closed = await engine.close_session("sess-100")
        assert closed is True

    asyncio.run(_run())


def test_duplex_tools_and_slash() -> None:
    """Test Duplex LLM tool handlers and slash commands."""
    async def _run() -> None:
        tools = get_duplex_tools()
        assert len(tools) >= 6

        # 1. Start session tool
        data_start = await duplex_start_session("tool-sess", sample_rate=16000)
        assert data_start["success"] is True

        # 2. Push frame tool (base64)
        raw_frame = b"\x30\x30" * 320
        b64 = base64.b64encode(raw_frame).decode("ascii")
        data_push = await duplex_push_audio_frame("tool-sess", base64_pcm=b64, user_text="تست صدا")
        assert data_push["success"] is True

        # 3. Interruption tool
        data_intr = await duplex_inject_interruption("tool-sess", reason="test")
        assert data_intr["success"] is True

        # 4. Metrics & transcript tools
        res_metrics = await duplex_get_session_metrics("tool-sess")
        assert res_metrics["session_id"] == "tool-sess"

        res_transcript = await duplex_export_transcript("tool-sess", format="markdown")
        assert "گزارش گفتگوی صوتی" in res_transcript["transcript_markdown"]

        # 5. Reset tool
        data_reset = await duplex_reset_session("tool-sess")
        assert data_reset["success"] is True

        # 6. Slash commands
        slash_help = await handle_duplex_command("")
        assert "راهنمای دستورات صوتی" in slash_help

        slash_start = await handle_duplex_command("start slash-sess")
        assert "با موفقیت فعال شد" in slash_start

        slash_push = await handle_duplex_command("push slash-sess سلام دریم")
        assert "پیام صوتی دریافت شد" in slash_push

        slash_metrics = await handle_duplex_command("metrics slash-sess")
        assert "معیارهای تاخیر" in slash_metrics

        slash_reset = await handle_duplex_command("reset slash-sess")
        assert "به طور کامل ریست شد" in slash_reset

    asyncio.run(_run())
