"""LLM Tool bindings for Text-to-Speech (TTS), Speech-to-Text (STT), and Emotion Recognition."""

from __future__ import annotations

from typing import Any

from dream.security.pathsafety import is_sensitive_path
from dream.speech.engine import SpeechEngine
from dream.speech.types import EmotionType, STTRequest, TTSRequest

_GLOBAL_SPEECH_ENGINE: SpeechEngine | None = None


def get_global_speech_engine() -> SpeechEngine:
    """Get or initialize singleton SpeechEngine."""
    global _GLOBAL_SPEECH_ENGINE
    if _GLOBAL_SPEECH_ENGINE is None:
        _GLOBAL_SPEECH_ENGINE = SpeechEngine()
    return _GLOBAL_SPEECH_ENGINE


def reset_global_speech_engine() -> None:
    """Reset SpeechEngine singleton instance."""
    global _GLOBAL_SPEECH_ENGINE
    _GLOBAL_SPEECH_ENGINE = None


def speech_text_to_speech(
    text: str,
    voice_id: str = "fa-mina",
    emotion: str = "neutral",
    speed: float = 1.0,
    pitch: float = 1.0,
    output_path: str = "",
) -> dict[str, Any]:
    """Synthesize text into speech audio with optional emotional modulation."""
    if output_path and is_sensitive_path(output_path):
        return {
            "success": False,
            "error": f"Permission denied: '{output_path}' is a sensitive system path.",
        }

    engine = get_global_speech_engine()

    # Parse emotion
    em_enum = EmotionType.NEUTRAL
    try:
        em_enum = EmotionType(emotion.lower())
    except ValueError:
        pass

    req = TTSRequest(
        text=text,
        voice_id=voice_id,
        emotion=em_enum,
        speed=speed,
        pitch=pitch,
        output_path=output_path or None,
    )

    try:
        res = engine.synthesize(req)
        return {"success": True, **res.to_dict()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def speech_speech_to_text(audio_path: str, language: str = "auto") -> dict[str, Any]:
    """Transcribe speech audio into normalized text and classify voice emotion."""
    if is_sensitive_path(audio_path):
        return {
            "success": False,
            "error": f"Permission denied: '{audio_path}' is a sensitive system path.",
        }

    engine = get_global_speech_engine()
    req = STTRequest(audio_path=audio_path, language=language)

    try:
        res = engine.transcribe(req)
        return {"success": True, **res.to_dict()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def speech_analyze_voice_emotion(audio_path: str) -> dict[str, Any]:
    """Analyze acoustic features in audio to detect emotion trajectory and blend."""
    if is_sensitive_path(audio_path):
        return {
            "success": False,
            "error": f"Permission denied: '{audio_path}' is a sensitive system path.",
        }

    engine = get_global_speech_engine()
    req = STTRequest(audio_path=audio_path, detect_emotion=True)

    try:
        res = engine.transcribe(req)
        blend_d = res.emotion_blend.to_dict() if res.emotion_blend else None
        return {
            "success": True,
            "overall_emotion": res.overall_emotion.value,
            "emotion_blend": blend_d,
            "duration": round(res.duration, 3),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def speech_list_voices(language: str = "") -> dict[str, Any]:
    """List available voice personas (Persian, English, Soprano, HybridEmo)."""
    engine = get_global_speech_engine()
    voices = engine.list_voices(language=language or None)
    return {"success": True, "voices": [v.to_dict() for v in voices]}


def get_speech_tools() -> list[Any]:
    """Return speech tool functions for agent registration."""
    return [
        speech_text_to_speech,
        speech_speech_to_text,
        speech_analyze_voice_emotion,
        speech_list_voices,
    ]
