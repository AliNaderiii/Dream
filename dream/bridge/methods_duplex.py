"""``duplex.*`` RPC surface, registered through the P0 extension seam.

This module is discovered automatically by :mod:`dream.bridge.extensions`.
It exposes the real-time audio duplex voice bridge and visualizer state to
the desktop UI and JSON-RPC clients:

===========================  =================================================
``duplex.start``             start or reconfigure a live desktop duplex voice session
``duplex.push_mic_chunk``    ingest a microphone PCM audio chunk and get visualizer metrics
``duplex.get_visualizer``    poll the latest 16-peak waveform and 8-band spectrum metrics
``duplex.inject_interruption`` force a manual barge-in cut-off on speech output
``duplex.get_metrics``       retrieve turn metrics, VAD confidence, and latencies
``duplex.export_transcript`` export the duplex conversation history as text/markdown
``duplex.stop``              gracefully stop and terminate the voice session
===========================  =================================================
"""

from __future__ import annotations

import logging
from typing import Any

from dream.bridge.errors import invalid_params
from dream.duplex.desktop_bridge import get_desktop_voice_bridge
from dream.duplex.engine import get_duplex_engine
from dream.duplex.types import DuplexConfig

logger = logging.getLogger("dream.bridge.duplex")

__all__ = ["HANDLERS"]


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(params, dict):
        merged.update(params)
    merged.update(kwargs)
    return merged


async def duplex_start(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Start or configure a live desktop duplex voice session."""
    data = _params(params, kwargs)
    session_id = str(data.get("session_id") or "desktop-live-voice").strip()
    sample_rate = int(data.get("sample_rate") or 16000)
    vad_threshold = float(data.get("vad_threshold") or data.get("vad_energy_threshold") or 0.015)

    if sample_rate not in (8000, 16000, 24000, 48000):
        raise invalid_params("sample_rate must be 8000, 16000, 24000, or 48000 Hz")

    bridge = get_desktop_voice_bridge()
    bridge.session_id = session_id
    bridge.sample_rate = sample_rate

    cfg = DuplexConfig(
        session_id=session_id,
        sample_rate=sample_rate,
        vad_energy_threshold=vad_threshold,
    )
    res = await bridge.start(cfg)
    return {
        "status": "connected",
        "session_id": session_id,
        "sample_rate": sample_rate,
        "frame_size_ms": 20,
        "details": res,
    }


async def duplex_push_mic_chunk(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Ingest base64 PCM audio chunk from microphone and return visualizer metrics."""
    data = _params(params, kwargs)
    base64_pcm = str(data.get("chunk_b64") or data.get("base64_pcm") or "").strip()

    bridge = get_desktop_voice_bridge()
    try:
        result = await bridge.process_incoming_mic_chunk(base64_pcm)
        return result
    except Exception as exc:
        raise invalid_params(f"Failed to process mic audio chunk: {exc}") from exc


def duplex_get_visualizer(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Return the latest waveform peaks, frequency spectrum bins, and speaking state."""
    bridge = get_desktop_voice_bridge()
    return bridge.get_latest_visualizer()


async def duplex_inject_interruption(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Force manual barge-in interruption on active speech playback."""
    data = _params(params, kwargs)
    session_id = str(data.get("session_id") or "desktop-live-voice").strip()
    engine = get_duplex_engine()
    session = engine.get_or_create_session(session_id)
    await session.interrupt_manually(reason="desktop_ui_barge_in")
    return {
        "status": "interrupted",
        "session_id": session_id,
        "interrupted": True,
    }


def duplex_get_metrics(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Retrieve latency, turn counts, and audio metrics for active session."""
    data = _params(params, kwargs)
    session_id = str(data.get("session_id") or "desktop-live-voice").strip()
    engine = get_duplex_engine()
    session = engine.get_or_create_session(session_id)
    status = session.get_status()
    return {
        "session_id": session_id,
        "status": "ok",
        "stats": status.get("metrics", {}),
    }


def duplex_export_transcript(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Export the conversation transcript of the duplex session."""
    data = _params(params, kwargs)
    session_id = str(data.get("session_id") or "desktop-live-voice").strip()
    format_type = str(data.get("format") or "markdown").lower()
    engine = get_duplex_engine()
    session = engine.get_or_create_session(session_id)
    turns = session.get_transcript()

    if format_type == "json":
        import json
        transcript_text = json.dumps(turns, ensure_ascii=False, indent=2)
    else:
        lines = ["# گزارش مکالمه صوتی زنده (Desktop Live Voice Transcript)\n"]
        for t in turns:
            speaker = "کاربر" if t.get("speaker") == "user" else "دریم (Dream)"
            lines.append(f"**{speaker}:** {t.get('text', '')}\n")
        transcript_text = "\n".join(lines) if turns else "هنوز مکالمه‌ای ثبت نشده است."

    return {
        "session_id": session_id,
        "format": format_type,
        "transcript": transcript_text,
    }


async def duplex_stop(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Gracefully terminate desktop voice session."""
    bridge = get_desktop_voice_bridge()
    return await bridge.stop()


HANDLERS = {
    "duplex.start": duplex_start,
    "duplex.push_mic_chunk": duplex_push_mic_chunk,
    "duplex.get_visualizer": duplex_get_visualizer,
    "duplex.inject_interruption": duplex_inject_interruption,
    "duplex.get_metrics": duplex_get_metrics,
    "duplex.export_transcript": duplex_export_transcript,
    "duplex.stop": duplex_stop,
}
