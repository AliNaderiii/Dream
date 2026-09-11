"""Speech Synthesis (TTS), Recognition (STT), and Emotion Modeling Subsystem."""

from .engine import BUILTIN_VOICES, SpeechEngine
from .slash import handle_speech_command
from .tools import (
    get_global_speech_engine,
    get_speech_tools,
    reset_global_speech_engine,
    speech_analyze_voice_emotion,
    speech_list_voices,
    speech_speech_to_text,
    speech_text_to_speech,
)
from .types import (
    AudioFormat,
    EmotionBlend,
    EmotionTrajectorySegment,
    EmotionType,
    STTRequest,
    STTResult,
    STTSegment,
    TTSRequest,
    TTSResult,
    VoicePersona,
)

__all__ = [
    "BUILTIN_VOICES",
    "AudioFormat",
    "EmotionBlend",
    "EmotionTrajectorySegment",
    "EmotionType",
    "STTRequest",
    "STTResult",
    "STTSegment",
    "SpeechEngine",
    "TTSRequest",
    "TTSResult",
    "VoicePersona",
    "get_global_speech_engine",
    "get_speech_tools",
    "handle_speech_command",
    "reset_global_speech_engine",
    "speech_analyze_voice_emotion",
    "speech_list_voices",
    "speech_speech_to_text",
    "speech_text_to_speech",
]
