"""Real-time Duplex Session Controller and streaming state machine."""

from __future__ import annotations

import asyncio
import math
import struct
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from dream.duplex.ring_buffer import AudioRingBuffer
from dream.duplex.types import (
    DuplexConfig,
    DuplexMetrics,
    DuplexState,
    DuplexTurn,
    VADState,
)
from dream.duplex.vad import VoiceActivityDetector


class DuplexSession:
    """Manages an active real-time bi-directional streaming duplex conversation."""

    def __init__(self, config: DuplexConfig | None = None) -> None:
        self.config = config or DuplexConfig()
        self.session_id = self.config.session_id or f"duplex-{uuid.uuid4().hex[:8]}"
        self.state: DuplexState = DuplexState.IDLE
        self.vad = VoiceActivityDetector(
            energy_threshold=self.config.vad_energy_threshold,
            hangover_ms=self.config.vad_hangover_ms,
            sample_rate=self.config.sample_rate,
            frame_size_ms=self.config.frame_size_ms,
        )
        self.input_buffer = AudioRingBuffer(capacity_bytes=self.config.sample_rate * 2 * 15)
        self.output_buffer = AudioRingBuffer(capacity_bytes=self.config.sample_rate * 2 * 15)
        self.turns: list[DuplexTurn] = []
        self.metrics = DuplexMetrics()

        self._active_tts_task: asyncio.Task[Any] | None = None
        self._user_turn_audio_bytes: bytearray = bytearray()
        self._current_user_text: str = ""
        self._current_assistant_text: str = ""
        self._speech_start_time: float = 0.0
        self._response_start_time: float = 0.0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Initialize and start the duplex listening session."""
        async with self._lock:
            self.state = DuplexState.LISTENING
            self.vad.reset()
            await self.input_buffer.clear()
            await self.output_buffer.clear()

    async def push_user_audio(self, pcm_chunk: bytes) -> tuple[DuplexState, bool]:
        """Ingest incoming user PCM chunk, update VAD, and handle potential barge-in.

        Returns:
            Tuple of (current_state, was_interrupted_flag)
        """
        async with self._lock:
            if self.state == DuplexState.CLOSED:
                return DuplexState.CLOSED, False

            frame = self.vad.process_frame(pcm_chunk)
            await self.input_buffer.write(pcm_chunk)
            was_interrupted = False

            # Check Barge-In if agent is speaking
            if self.state == DuplexState.SPEAKING and self.config.barge_in_enabled:
                if self.vad.check_barge_in(frame, min_speech_ms=self.config.barge_in_min_speech_ms):
                    was_interrupted = True
                    await self._handle_barge_in()

            # Handle user speech accumulation
            if frame.is_speech or self.vad.current_state in (
                VADState.SPEECH_START,
                VADState.SPEECH_ONGOING,
            ):
                if not self._user_turn_audio_bytes:
                    self._speech_start_time = time.time()
                self._user_turn_audio_bytes.extend(pcm_chunk)
                if self.state != DuplexState.INTERRUPTED:
                    self.state = DuplexState.LISTENING

            elif self.vad.current_state == VADState.SPEECH_END:
                # Speech ended, transition to THINKING
                if self._user_turn_audio_bytes:
                    await self._finalize_user_speech()

            return self.state, was_interrupted

    async def _handle_barge_in(self) -> None:
        """Handle user barge-in interruption by immediately cutting off bot audio."""
        self.state = DuplexState.INTERRUPTED
        self.metrics.total_interruptions += 1

        # Cancel current speaking task if active
        if self._active_tts_task and not self._active_tts_task.done():
            self._active_tts_task.cancel()
            self._active_tts_task = None

        # Drop remaining unplayed bot audio in output buffer
        await self.output_buffer.clear()

        # Record assistant turn as interrupted
        if self._current_assistant_text:
            interrupted_turn = DuplexTurn(
                turn_id=f"turn-{uuid.uuid4().hex[:6]}",
                speaker="assistant",
                text=self._current_assistant_text + " [قطع شد]",
                interrupted=True,
                latency_ms=0.0,
                emotion_tag="alert",
            )
            self.turns.append(interrupted_turn)
            self.metrics.total_turns += 1
            self.metrics.assistant_turns += 1
            self._current_assistant_text = ""

        self.state = DuplexState.LISTENING

    async def _finalize_user_speech(self) -> None:
        """Finalize accumulated user audio and record user turn."""
        duration_sec = len(self._user_turn_audio_bytes) / (self.config.sample_rate * 2)
        duration_ms = duration_sec * 1000.0

        user_text = (
            self._current_user_text
            if self._current_user_text
            else f"[ورودی صوتی کاربر به مدت {duration_sec:.1f} ثانیه]"
        )

        turn = DuplexTurn(
            turn_id=f"turn-{uuid.uuid4().hex[:6]}",
            speaker="user",
            text=user_text,
            audio_duration_ms=duration_ms,
            interrupted=False,
            latency_ms=0.0,
        )
        self.turns.append(turn)
        self.metrics.total_turns += 1
        self.metrics.user_turns += 1
        self.metrics.total_user_audio_sec += duration_sec

        # Reset user accumulator
        self._user_turn_audio_bytes.clear()
        self._current_user_text = ""
        self.state = DuplexState.THINKING
        self._response_start_time = time.time()

    async def stream_assistant_response(
        self,
        text_tokens: AsyncGenerator[str, None] | list[str],
        emotion_tag: str = "calm",
    ) -> AsyncGenerator[bytes, None]:
        """Stream LLM response tokens and synthesize audio chunks concurrently."""
        self.state = DuplexState.SPEAKING
        self._current_assistant_text = ""
        full_text_list: list[str] = []
        first_token_received = False
        ttft_ms = 0.0

        if isinstance(text_tokens, list):
            async def _iter_list() -> AsyncGenerator[str, None]:
                for t in text_tokens:
                    yield t
            token_gen = _iter_list()
        else:
            token_gen = text_tokens

        try:
            async for token in token_gen:
                if self.state == DuplexState.INTERRUPTED:
                    break

                if not first_token_received:
                    first_token_received = True
                    ttft_ms = (time.time() - self._response_start_time) * 1000.0
                    self._update_ttft(ttft_ms)

                full_text_list.append(token)
                self._current_assistant_text = "".join(full_text_list)

                # Generate simulated / actual PCM audio packet for token (20ms frame)
                pcm_chunk = self._generate_pcm_frame(token)
                await self.output_buffer.write(pcm_chunk)
                yield pcm_chunk
                await asyncio.sleep(0.01)  # Micro yield

        except asyncio.CancelledError:
            self.state = DuplexState.INTERRUPTED
            raise

        finally:
            if self.state != DuplexState.INTERRUPTED:
                bot_turn = DuplexTurn(
                    turn_id=f"turn-{uuid.uuid4().hex[:6]}",
                    speaker="assistant",
                    text=self._current_assistant_text,
                    audio_duration_ms=len(full_text_list) * 200.0,
                    interrupted=False,
                    latency_ms=ttft_ms,
                    emotion_tag=emotion_tag,
                )
                self.turns.append(bot_turn)
                self.metrics.total_turns += 1
                self.metrics.assistant_turns += 1
                self.metrics.total_assistant_audio_sec += len(full_text_list) * 0.2
                self._current_assistant_text = ""
                self.state = DuplexState.LISTENING

    def _generate_pcm_frame(self, token: str) -> bytes:
        """Synthesize a standard 20ms mono 16-bit PCM block for streaming."""
        num_samples = int(self.config.sample_rate * 0.02)
        data = bytearray(num_samples * 2)
        char_val = ord(token[0]) if token else 65
        for i in range(num_samples):
            val = int(500 * math.sin(2 * math.pi * 440 * (i / self.config.sample_rate) + char_val))
            val = max(-32767, min(32767, val))
            struct.pack_into("<h", data, i * 2, val)
        return bytes(data)

    def _update_ttft(self, ttft_ms: float) -> None:
        """Update running average of Time To First Token."""
        if self.metrics.assistant_turns == 0:
            self.metrics.avg_ttft_ms = ttft_ms
        else:
            self.metrics.avg_ttft_ms = (self.metrics.avg_ttft_ms * 0.8) + (ttft_ms * 0.2)

    def set_user_text(self, text: str) -> None:
        """Set recognized user text from STT stream."""
        self._current_user_text = text

    async def interrupt_manually(self, reason: str = "user_barge_in") -> None:
        """Manually trigger an interruption event."""
        async with self._lock:
            await self._handle_barge_in()

    async def close(self) -> None:
        """Safely terminate the duplex session and flush buffers."""
        async with self._lock:
            self.state = DuplexState.CLOSED
            if self._active_tts_task and not self._active_tts_task.done():
                self._active_tts_task.cancel()
            await self.input_buffer.clear()
            await self.output_buffer.clear()

    def get_transcript(self) -> list[dict[str, Any]]:
        """Return full conversation transcript as structured dictionaries."""
        return [turn.to_dict() for turn in self.turns]

    def get_status(self) -> dict[str, Any]:
        """Return diagnostic status of the session."""
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "vad_state": self.vad.current_state.value,
            "total_turns": len(self.turns),
            "metrics": self.metrics.to_dict(),
            "input_buffer": self.input_buffer.get_stats(),
            "output_buffer": self.output_buffer.get_stats(),
        }
