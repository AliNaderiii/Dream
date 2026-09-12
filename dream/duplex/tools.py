"""LLM agent tools and singleton managers for Duplex Streaming Audio and Realtime Gateway."""

from __future__ import annotations

import base64
import logging
from typing import Any

from dream.duplex.engine import DuplexEngine, get_duplex_engine
from dream.duplex.realtime_gateway import get_realtime_gateway_server
from dream.duplex.types import DuplexConfig
from dream.speech.adapters import get_speech_adapter_registry

logger = logging.getLogger(__name__)

_GLOBAL_DUPLEX_ENGINE: DuplexEngine | None = None


def get_global_duplex_engine() -> DuplexEngine:
    global _GLOBAL_DUPLEX_ENGINE
    if _GLOBAL_DUPLEX_ENGINE is None:
        _GLOBAL_DUPLEX_ENGINE = get_duplex_engine()
    return _GLOBAL_DUPLEX_ENGINE


def reset_global_duplex_engine() -> None:
    global _GLOBAL_DUPLEX_ENGINE
    _GLOBAL_DUPLEX_ENGINE = None


async def duplex_start_session(
    session_id: str = "default-duplex",
    sample_rate: int = 16000,
    vad_threshold: float = 0.015,
    barge_in: bool = True,
) -> dict[str, Any]:
    engine = get_global_duplex_engine()
    cfg = DuplexConfig(
        session_id=session_id,
        sample_rate=sample_rate,
        vad_energy_threshold=vad_threshold,
        barge_in_enabled=barge_in,
    )
    session = engine.get_or_create_session(session_id=session_id, config=cfg)
    await session.start()
    return {
        "success": True,
        "status": "success",
        "message": f"🎙️ نشست صوتی زنده (Duplex) با شناسه `{session_id}` با موفقیت آغاز شد.",
        "session_id": session_id,
        "sample_rate": sample_rate,
        "barge_in_enabled": barge_in,
    }


async def duplex_push_audio_frame(
    session_id: str = "default-duplex",
    base64_pcm: str = "",
    user_text: str = "",
) -> dict[str, Any]:
    engine = get_global_duplex_engine()
    session = engine.get_or_create_session(session_id=session_id)

    if user_text:
        session.set_user_text(user_text)

    raw_bytes = b""
    if base64_pcm:
        try:
            raw_bytes = base64.b64decode(base64_pcm)
        except Exception as e:
            return {
                "success": False,
                "status": "error",
                "message": f"خطا در دیکود بیس۶۴: {e}",
            }
    else:
        raw_bytes = b"\x10\x20" * 320

    state, interrupted = await session.push_user_audio(raw_bytes)
    return {
        "success": True,
        "status": "success",
        "session_id": session_id,
        "current_state": state.value,
        "barge_in_triggered": interrupted,
        "total_turns": len(session.turns),
    }


async def duplex_inject_interruption(
    session_id: str = "default-duplex",
    reason: str = "user_barge_in",
) -> dict[str, Any]:
    engine = get_global_duplex_engine()
    session = engine.get_or_create_session(session_id=session_id)
    await session.interrupt_manually(reason=reason)
    return {
        "success": True,
        "status": "success",
        "message": f"⚠️ صحبت مدل در نشست `{session_id}` به صورت آنی قطع شد (Barge-in).",
        "state": session.state.value,
        "total_interruptions": session.metrics.total_interruptions,
    }


async def duplex_get_session_metrics(
    session_id: str = "default-duplex",
) -> dict[str, Any]:
    engine = get_global_duplex_engine()
    session = engine.get_or_create_session(session_id=session_id)
    return {"success": True, **session.get_status()}


async def duplex_export_transcript(
    session_id: str = "default-duplex",
    format: str = "markdown",
) -> dict[str, Any]:
    engine = get_global_duplex_engine()
    if format.lower() == "json":
        data = engine.export_json(session_id)
        return {"success": True, "format": "json", "data": data}
    data_md = engine.export_transcript_markdown(session_id)
    return {"success": True, "format": "markdown", "transcript_markdown": data_md}


async def duplex_reset_session(
    session_id: str = "default-duplex",
) -> dict[str, Any]:
    engine = get_global_duplex_engine()
    closed = await engine.close_session(session_id)
    return {
        "success": True,
        "status": "success",
        "message": f"🔄 نشست `{session_id}` با موفقیت پاکسازی و بازنشانی شد.",
        "was_active": closed,
    }


async def voice_realtime_server_start(
    host: str = "127.0.0.1",
    port: int = 8765,
) -> dict[str, Any]:
    server = get_realtime_gateway_server()
    server.host = host
    server.port = port
    res = server.start_server()
    return {
        "success": True,
        "status": "success",
        "message": f"🌐 سرور Realtime Gateway روی آدرس {res['endpoint_ws']} فعال شد.",
        **res,
    }


async def voice_speech_adapter_list() -> dict[str, Any]:
    registry = get_speech_adapter_registry()
    adapters = registry.list_adapters()
    return {
        "success": True,
        "total_adapters": len(adapters),
        "adapters": adapters,
    }


async def voice_speech_adapter_benchmark() -> dict[str, Any]:
    registry = get_speech_adapter_registry()
    results = registry.benchmark_adapters()
    return {
        "success": True,
        "total_benchmarked": len(results),
        "results": results,
    }


async def voice_speech_adapter_select(
    adapter_kind: str,
    role: str = "tts",
) -> dict[str, Any]:
    registry = get_speech_adapter_registry()
    r = role.lower().strip()
    success = False
    if r == "tts":
        success = registry.set_active_tts(adapter_kind)
    elif r == "stt":
        success = registry.set_active_stt(adapter_kind)
    elif r == "vad":
        success = registry.set_active_vad(adapter_kind)

    if not success:
        return {
            "success": False,
            "message": f"موتور صوتی `{adapter_kind}` برای نقش `{role}` یافت نشد یا معتبر نیست.",
        }

    return {
        "success": True,
        "status": "success",
        "message": f"✅ موتور `{adapter_kind}` با موفقیت تنظیم شد.",
    }


def get_duplex_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "duplex_start_session",
            "description": "Start or initialize a real-time duplex streaming audio session",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "default": "default-duplex"},
                    "sample_rate": {"type": "integer", "default": 16000},
                    "vad_threshold": {"type": "number", "default": 0.015},
                    "barge_in": {"type": "boolean", "default": True},
                },
            },
            "handler": duplex_start_session,
        },
        {
            "name": "duplex_push_audio_frame",
            "description": "Ingest a chunk of incoming user PCM audio or recognized speech text",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "default": "default-duplex"},
                    "base64_pcm": {"type": "string"},
                    "user_text": {"type": "string"},
                },
            },
            "handler": duplex_push_audio_frame,
        },
        {
            "name": "duplex_inject_interruption",
            "description": "Manually signal an interruption (Barge-in) to stop speech",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "default": "default-duplex"},
                    "reason": {"type": "string", "default": "user_barge_in"},
                },
            },
            "handler": duplex_inject_interruption,
        },
        {
            "name": "duplex_get_session_metrics",
            "description": "Retrieve latency, TTFT, and metrics for a duplex session",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "default": "default-duplex"},
                },
            },
            "handler": duplex_get_session_metrics,
        },
        {
            "name": "duplex_export_transcript",
            "description": "Export the complete transcript of a duplex voice conversation",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "default": "default-duplex"},
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "default": "markdown",
                    },
                },
            },
            "handler": duplex_export_transcript,
        },
        {
            "name": "duplex_reset_session",
            "description": "Reset and clear all audio buffers and turn histories for a session",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "default": "default-duplex"},
                },
            },
            "handler": duplex_reset_session,
        },
        {
            "name": "voice_realtime_server_start",
            "description": "Start the Realtime WebSocket & WebRTC gateway server",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {"type": "string", "default": "127.0.0.1"},
                    "port": {"type": "integer", "default": 8765},
                },
            },
            "handler": voice_realtime_server_start,
        },
        {
            "name": "voice_speech_adapter_list",
            "description": "List all registered speech synthesis, recognition, and VAD engines",
            "parameters": {"type": "object", "properties": {}},
            "handler": voice_speech_adapter_list,
        },
        {
            "name": "voice_speech_adapter_benchmark",
            "description": "Run real-time latency and throughput benchmarks across speech engines",
            "parameters": {"type": "object", "properties": {}},
            "handler": voice_speech_adapter_benchmark,
        },
        {
            "name": "voice_speech_adapter_select",
            "description": "Switch active default TTS, STT, or VAD adapter",
            "parameters": {
                "type": "object",
                "properties": {
                    "adapter_kind": {"type": "string"},
                    "role": {"type": "string", "enum": ["tts", "stt", "vad"], "default": "tts"},
                },
                "required": ["adapter_kind"],
            },
            "handler": voice_speech_adapter_select,
        },
    ]
