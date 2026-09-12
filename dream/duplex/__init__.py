"""Real-Time Bi-Directional Streaming Audio Duplex Agent Subsystem for Dream."""

from __future__ import annotations

from dream.duplex.engine import DuplexEngine, get_duplex_engine
from dream.duplex.realtime_gateway import (
    ConversationItem,
    RealtimeClientSession,
    RealtimeEventType,
    RealtimeGatewayServer,
    RealtimeSessionConfig,
    get_realtime_gateway_server,
)
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
    voice_realtime_server_start,
    voice_speech_adapter_benchmark,
    voice_speech_adapter_list,
    voice_speech_adapter_select,
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
    "ConversationItem",
    "DuplexConfig",
    "DuplexEngine",
    "DuplexMetrics",
    "DuplexSession",
    "DuplexState",
    "DuplexTurn",
    "RealtimeClientSession",
    "RealtimeEventType",
    "RealtimeGatewayServer",
    "RealtimeSessionConfig",
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
    "get_realtime_gateway_server",
    "handle_duplex_command",
    "reset_global_duplex_engine",
    "voice_realtime_server_start",
    "voice_speech_adapter_benchmark",
    "voice_speech_adapter_list",
    "voice_speech_adapter_select",
]
