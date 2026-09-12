"""LLM agent tools and singleton managers for Duplex Streaming Audio."""

from __future__ import annotations

import base64
import logging
from typing import Any

from dream.duplex.engine import DuplexEngine, get_duplex_engine
from dream.duplex.types import DuplexConfig

logger = logging.getLogger(__name__)

_GLOBAL_DUPLEX_ENGINE: DuplexEngine | None = None


def get_global_duplex_engine() -> DuplexEngine:
    """Retrieve or initialize singleton DuplexEngine."""
    global _GLOBAL_DUPLEX_ENGINE
    if _GLOBAL_DUPLEX_ENGINE is None:
        _GLOBAL_DUPLEX_ENGINE = get_duplex_engine()
    return _GLOBAL_DUPLEX_ENGINE


def reset_global_duplex_engine() -> None:
    """Reset global DuplexEngine instance for test isolation."""
    global _GLOBAL_DUPLEX_ENGINE
    _GLOBAL_DUPLEX_ENGINE = None


async def duplex_start_session(
    session_id: str = "default-duplex",
    sample_rate: int = 16000,
    vad_threshold: float = 0.015,
    barge_in: bool = True,
) -> dict[str, Any]:
    """Start or initialize a real-time duplex streaming audio session.

    Args:
        session_id: Unique identifier for the duplex session.
        sample_rate: Audio sampling frequency (e.g. 16000 or 24000 Hz).
        vad_threshold: RMS energy threshold for Voice Activity Detection.
        barge_in: Whether to enable automatic user speech interruption.
    """
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
    """Ingest a chunk of incoming user PCM audio (base64-encoded) or recognized speech text.

    Args:
        session_id: Unique identifier for the duplex session.
        base64_pcm: Base64-encoded 16-bit PCM audio frame bytes.
        user_text: Optional text recognized from speech (STT).
    """
    engine = get_global_duplex_engine()
    session = engine.get_or_create_session(session_id=session_id)

    if user_text:
        session.set_user_text(user_text)

    raw_bytes = b""
    if base64_pcm:
        try:
            raw_bytes = base64.b64decode(base64_pcm)
        except Exception as e:
            return {"success": False, "status": "error", "message": f"خطا در دیکود بیس۶۴: {e}"}
    else:
        # Default mock frame with sound energy if no raw bytes passed
        raw_bytes = b"\x10\x20" * 320  # 20ms frame at 16kHz

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
    """Manually signal an interruption (Barge-in) to stop agent speech immediately.

    Args:
        session_id: Unique identifier for the duplex session.
        reason: Explanation or cause for interruption.
    """
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
    """Retrieve latency, TTFT, and conversation metrics for a duplex audio session.

    Args:
        session_id: Unique identifier for the duplex session.
    """
    engine = get_global_duplex_engine()
    session = engine.get_or_create_session(session_id=session_id)
    return {"success": True, **session.get_status()}


async def duplex_export_transcript(
    session_id: str = "default-duplex",
    format: str = "markdown",
) -> dict[str, Any]:
    """Export the complete transcript and turns of a duplex voice conversation.

    Args:
        session_id: Unique identifier for the duplex session.
        format: Output format ('markdown' or 'json').
    """
    engine = get_global_duplex_engine()
    if format.lower() == "json":
        data = engine.export_json(session_id)
        return {"success": True, "format": "json", "data": data}
    data_md = engine.export_transcript_markdown(session_id)
    return {"success": True, "format": "markdown", "transcript_markdown": data_md}


async def duplex_reset_session(
    session_id: str = "default-duplex",
) -> dict[str, Any]:
    """Reset and clear all audio buffers and turn histories for a duplex session.

    Args:
        session_id: Unique identifier for the duplex session.
    """
    engine = get_global_duplex_engine()
    closed = await engine.close_session(session_id)
    return {
        "success": True,
        "status": "success",
        "message": f"🔄 نشست `{session_id}` با موفقیت پاکسازی و بازنشانی شد.",
        "was_active": closed,
    }


def get_duplex_tools() -> list[dict[str, Any]]:
    """Return tool manifests for LLM registration."""
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
    ]
