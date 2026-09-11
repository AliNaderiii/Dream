"""Domain types and data models for Speech (TTS), Recognition (STT), and Emotion."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EmotionType(str, Enum):
    """Supported voice emotional states inspired by HybridEmo multi-emotion modeling."""

    NEUTRAL = "neutral"
    JOYFUL = "joyful"
    EMPATHETIC = "empathetic"
    CALM = "calm"
    ENTHUSIASTIC = "enthusiastic"
    SERIOUS = "serious"
    SURPRISED = "surprised"
    CURIOUS = "curious"
    MELANCHOLIC = "melancholic"


class AudioFormat(str, Enum):
    """Supported audio container formats."""

    WAV = "wav"
    MP3 = "mp3"
    OGG = "ogg"
    PCM = "pcm"


@dataclass(slots=True)
class EmotionTrajectorySegment:
    """Sequential emotional trajectory stage (start emotion to end emotion with duration)."""

    start_emotion: EmotionType
    end_emotion: EmotionType
    start_time: float = 0.0
    end_time: float = 1.0
    intensity: float = 1.0
    transition_curve: str = "smooth"  # "linear", "smooth", "step"

    def get_intensity_at(self, t: float) -> float:
        """Calculate emotion intensity at time offset t within the segment."""
        if t <= self.start_time:
            return self.intensity
        if t >= self.end_time or self.end_time <= self.start_time:
            return self.intensity
        ratio = (t - self.start_time) / (self.end_time - self.start_time)
        if self.transition_curve == "smooth":
            # Cosine ease-in-out
            ratio = (1.0 - math.cos(ratio * math.pi)) / 2.0
        return self.intensity * ratio

    def to_dict(self) -> dict[str, Any]:
        """Serialize trajectory segment to dictionary."""
        return {
            "start_emotion": self.start_emotion.value,
            "end_emotion": self.end_emotion.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "intensity": self.intensity,
            "transition_curve": self.transition_curve,
        }


@dataclass(slots=True)
class EmotionBlend:
    """Simultaneous blending of multiple emotions with relative ratio and intensity."""

    primary_emotion: EmotionType = EmotionType.NEUTRAL
    secondary_emotion: EmotionType = EmotionType.CALM
    blend_ratio: float = 0.7  # 1.0 = 100% primary, 0.0 = 100% secondary
    intensity: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize emotion blend configuration to dictionary."""
        return {
            "primary_emotion": self.primary_emotion.value,
            "secondary_emotion": self.secondary_emotion.value,
            "blend_ratio": round(self.blend_ratio, 3),
            "intensity": round(self.intensity, 3),
        }


@dataclass(slots=True)
class VoicePersona:
    """Profile describing a voice speaker, accent, language, and emotional characteristics."""

    voice_id: str
    name: str
    language: str = "fa"  # "fa", "en", "ar", etc.
    gender: str = "neutral"  # "male", "female", "neutral"
    description: str = ""
    sample_rate: int = 24000
    default_emotion: EmotionType = EmotionType.NEUTRAL
    supported_emotions: list[EmotionType] = field(
        default_factory=lambda: list(EmotionType)
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize voice persona to dictionary."""
        return {
            "voice_id": self.voice_id,
            "name": self.name,
            "language": self.language,
            "gender": self.gender,
            "description": self.description,
            "sample_rate": self.sample_rate,
            "default_emotion": self.default_emotion.value,
            "supported_emotions": [e.value for e in self.supported_emotions],
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class TTSRequest:
    """Request payload for synthesizing speech from text."""

    text: str
    voice_id: str = "fa-mina"
    emotion: EmotionType | EmotionBlend | None = None
    trajectory: list[EmotionTrajectorySegment] | None = None
    speed: float = 1.0
    pitch: float = 1.0
    sample_rate: int = 24000
    output_format: AudioFormat = AudioFormat.WAV
    output_path: str | None = None


@dataclass(slots=True)
class TTSResult:
    """Generated audio synthesis result and metadata."""

    audio_path: str
    duration_seconds: float
    sample_rate: int
    format: str
    text: str
    voice_id: str
    emotion_applied: str
    audio_bytes: bytes = b""
    phonemes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize TTS result to dictionary."""
        return {
            "audio_path": self.audio_path,
            "duration_seconds": round(self.duration_seconds, 3),
            "sample_rate": self.sample_rate,
            "format": self.format,
            "text": self.text,
            "voice_id": self.voice_id,
            "emotion_applied": self.emotion_applied,
            "phonemes_count": len(self.phonemes),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class STTSegment:
    """Transcribed text segment with timestamp alignment and detected emotion."""

    start: float
    end: float
    text: str
    confidence: float = 0.95
    emotion: EmotionType = EmotionType.NEUTRAL

    def to_dict(self) -> dict[str, Any]:
        """Serialize STT segment to dictionary."""
        return {
            "start": round(self.start, 2),
            "end": round(self.end, 2),
            "text": self.text,
            "confidence": round(self.confidence, 3),
            "emotion": self.emotion.value,
        }


@dataclass(slots=True)
class STTRequest:
    """Request payload for audio speech-to-text recognition."""

    audio_path: str
    language: str = "auto"  # "fa", "en", "auto"
    prompt_hint: str = ""
    detect_emotion: bool = True
    timestamps: bool = True


@dataclass(slots=True)
class STTResult:
    """Audio recognition and emotion transcription outcome."""

    text: str
    language: str
    duration: float
    confidence: float
    segments: list[STTSegment] = field(default_factory=list)
    overall_emotion: EmotionType = EmotionType.NEUTRAL
    emotion_blend: EmotionBlend | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize STT outcome to dictionary."""
        blend_d = self.emotion_blend.to_dict() if self.emotion_blend else None
        return {
            "text": self.text,
            "language": self.language,
            "duration": round(self.duration, 3),
            "confidence": round(self.confidence, 3),
            "segments": [s.to_dict() for s in self.segments],
            "overall_emotion": self.overall_emotion.value,
            "emotion_blend": blend_d,
            "metadata": self.metadata,
        }
