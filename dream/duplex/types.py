"""Data models and type definitions for Real-Time Duplex Audio Agent."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DuplexState(str, Enum):
    """Lifecycle states of the real-time duplex streaming session."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    DRAINING = "draining"
    CLOSED = "closed"


class VADState(str, Enum):
    """Voice Activity Detection state."""

    SILENCE = "silence"
    SPEECH_START = "speech_start"
    SPEECH_ONGOING = "speech_ongoing"
    SPEECH_END = "speech_end"


class AudioFormat(str, Enum):
    """Supported PCM streaming audio formats."""

    PCM_16KHZ_16BIT_MONO = "pcm_16000_16_mono"
    PCM_24KHZ_16BIT_MONO = "pcm_24000_16_mono"
    PCM_48KHZ_16BIT_MONO = "pcm_48000_16_mono"


@dataclass
class AudioFrame:
    """Individual chunk/frame of linear PCM audio."""

    frame_id: int
    data: bytes
    timestamp_ms: float = field(default_factory=lambda: time.time() * 1000)
    sample_rate: int = 16000
    channels: int = 1
    sample_width: int = 2  # 16-bit
    energy: float = 0.0
    is_speech: bool = False

    @property
    def duration_ms(self) -> float:
        """Calculate duration of audio frame in milliseconds."""
        bytes_per_sample = self.channels * self.sample_width
        num_samples = len(self.data) / bytes_per_sample if bytes_per_sample > 0 else 0
        return (num_samples / self.sample_rate) * 1000.0 if self.sample_rate > 0 else 0.0


@dataclass
class DuplexTurn:
    """A single conversational dialogue turn in the duplex stream."""

    turn_id: str
    speaker: str  # "user" or "assistant"
    text: str
    audio_duration_ms: float = 0.0
    interrupted: bool = False
    latency_ms: float = 0.0
    emotion_tag: str = "neutral"
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize turn to dictionary."""
        return {
            "turn_id": self.turn_id,
            "speaker": self.speaker,
            "text": self.text,
            "audio_duration_ms": round(self.audio_duration_ms, 2),
            "interrupted": self.interrupted,
            "latency_ms": round(self.latency_ms, 2),
            "emotion_tag": self.emotion_tag,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass
class DuplexMetrics:
    """Real-time performance and latency metrics for the duplex session."""

    total_turns: int = 0
    user_turns: int = 0
    assistant_turns: int = 0
    total_interruptions: int = 0
    avg_ttft_ms: float = 0.0  # Time to first token
    avg_audio_latency_ms: float = 0.0
    total_user_audio_sec: float = 0.0
    total_assistant_audio_sec: float = 0.0
    ring_buffer_underruns: int = 0
    ring_buffer_overruns: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize metrics to dictionary."""
        return {
            "total_turns": self.total_turns,
            "user_turns": self.user_turns,
            "assistant_turns": self.assistant_turns,
            "total_interruptions": self.total_interruptions,
            "avg_ttft_ms": round(self.avg_ttft_ms, 2),
            "avg_audio_latency_ms": round(self.avg_audio_latency_ms, 2),
            "total_user_audio_sec": round(self.total_user_audio_sec, 2),
            "total_assistant_audio_sec": round(self.total_assistant_audio_sec, 2),
            "ring_buffer_underruns": self.ring_buffer_underruns,
            "ring_buffer_overruns": self.ring_buffer_overruns,
        }


@dataclass
class DuplexConfig:
    """Configuration parameters for Duplex streaming session."""

    session_id: str = "default-duplex"
    sample_rate: int = 16000
    frame_size_ms: int = 20  # 20ms frames standard
    vad_energy_threshold: float = 0.015
    vad_hangover_ms: int = 300  # Silence hangover before speech end
    barge_in_enabled: bool = True
    barge_in_min_speech_ms: int = 120  # Minimum user speech to trigger barge-in
    speculative_first_word: bool = True
    emotion_synthesis: bool = True
    preferred_language: str = "fa"  # Persian default
    max_history_turns: int = 50
