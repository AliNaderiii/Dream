"""Real-Time Bi-Directional Streaming Audio Duplex Agent Subsystem for Dream."""

from __future__ import annotations

from dream.duplex.engine import DuplexEngine, get_duplex_engine
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
    get_global_duplex_engine,
    reset_global_duplex_engine,
)
from dream.duplex.types import (
    AudioFormat,
    AudioFrame,
    DuplexConfig,
    DuplexMetrics,
    DuplexState,
    DuplexTurn,
    VADState,
)
from dream.duplex.vad import VoiceActivityDetector

__all__ = [
    "AudioFormat",
    "AudioFrame",
    "AudioRingBuffer",
    "DuplexConfig",
    "DuplexEngine",
    "DuplexMetrics",
    "DuplexSession",
    "DuplexState",
    "DuplexTurn",
    "VADState",
    "VoiceActivityDetector",
    "duplex_export_transcript",
    "duplex_get_session_metrics",
    "duplex_inject_interruption",
    "duplex_push_audio_frame",
    "duplex_reset_session",
    "duplex_start_session",
    "get_duplex_engine",
    "get_duplex_tools",
    "get_global_duplex_engine",
    "handle_duplex_command",
    "reset_global_duplex_engine",
]
