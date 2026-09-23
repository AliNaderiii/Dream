"""``tts.*`` JSON-RPC bridge methods.

Discovered automatically by :mod:`dream.bridge.extensions`.

=================================  ==================================================
``tts.engines``                   Honest engine listing (edge online / piper offline)
``tts.voices``                    Voice catalogue per engine (with on-disk flags)
``tts.synthesize``                Text → real speech file (+ inline audio for playback)
=================================  ==================================================

Both engines are optional extras (``pip install ".[tts]"``). When they are
absent the methods answer honestly with ``available: false`` and an install
hint — never a simulated voice. This is the TTS counterpart of
``stt.transcribe``; the legacy sine-wave "synthesizer" in
:mod:`dream.speech.engine` stays unwired by design.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import Any

from dream.bridge.errors import invalid_params
from dream.security.pathsafety import is_sensitive_path
from dream.speech.tts import (
    MAX_INLINE_AUDIO_BYTES,
    MAX_TEXT_CHARS,
    SPEED_MAX,
    SPEED_MIN,
    TTSError,
    list_engines,
    list_voices,
    synthesize_speech,
)

logger = logging.getLogger(__name__)

__all__ = ["HANDLERS"]

INSTALL_HINT = 'no TTS engine is installed — install with: pip install ".[tts]"'

ENGINES = ("auto", "edge", "piper")


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(params, dict):
        merged.update(params)
    merged.update(kwargs)
    return merged


def _text(data: dict[str, Any]) -> str:
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        raise invalid_params("text must be a non-empty string")
    if len(text) > MAX_TEXT_CHARS:
        raise invalid_params(f"text must be at most {MAX_TEXT_CHARS} characters")
    return text


def _engine(data: dict[str, Any]) -> str:
    engine = data.get("engine", "auto")
    if not isinstance(engine, str) or engine not in ENGINES:
        raise invalid_params("engine must be one of: " + ", ".join(ENGINES))
    return engine


def _voice(data: dict[str, Any]) -> str:
    voice = data.get("voice", "")
    if voice is None:
        voice = ""
    if not isinstance(voice, str) or len(voice) > 64:
        raise invalid_params("voice must be a string of at most 64 characters")
    return voice


def _speed(data: dict[str, Any]) -> float:
    speed = data.get("speed", 1.0)
    if isinstance(speed, bool) or not isinstance(speed, (int, float)):
        raise invalid_params("speed must be a number between 0.5 and 2.0")
    if not SPEED_MIN <= float(speed) <= SPEED_MAX:
        raise invalid_params(f"speed must be between {SPEED_MIN} and {SPEED_MAX}")
    return float(speed)


def _output_path(data: dict[str, Any]) -> str:
    output_path = data.get("output_path", "")
    if output_path is None:
        return ""
    if not isinstance(output_path, str) or len(output_path) > 4096:
        raise invalid_params("output_path must be a string of at most 4096 characters")
    if output_path and is_sensitive_path(output_path):
        raise invalid_params("Permission denied: output_path is a sensitive system path")
    return output_path


async def tts_engines(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """List TTS engines with honest availability flags."""
    _params(params, kwargs)  # accepts an (ignored) params object for symmetry
    return {"success": True, "engines": list_engines()}


async def tts_voices(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """List voices. Params: ``engine`` (optional — empty lists all engines)."""
    data = _params(params, kwargs)
    engine = data.get("engine", "")
    if engine is None:
        engine = ""
    if not isinstance(engine, str) or (engine and engine not in ENGINES):
        raise invalid_params("engine must be one of: " + ", ".join(ENGINES))
    return {"success": True, "voices": list_voices(engine)}


async def tts_synthesize(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Synthesize speech. Params: ``text``, ``engine``, ``voice``, ``speed``,
    ``output_path`` (optional), ``with_audio`` (default true — inline data URI)."""
    data = _params(params, kwargs)
    text = _text(data)
    engine = _engine(data)
    voice = _voice(data)
    speed = _speed(data)
    output_path = _output_path(data)
    with_audio = data.get("with_audio", True)
    if not isinstance(with_audio, bool):
        raise invalid_params("with_audio must be a boolean")

    try:
        result = await asyncio.to_thread(
            synthesize_speech, text, engine, voice, speed, output_path
        )
    except PermissionError as exc:
        return {"success": False, "error": str(exc)}
    except TTSError as exc:
        # Privacy: log the failure reason, never the text itself.
        logger.info("tts.synthesize refused/failed (%s)", exc)
        return {"success": False, "error": str(exc)}

    payload: dict[str, Any] = dict(result)
    if with_audio:
        try:
            audio_bytes = Path(result["audio_path"]).read_bytes()
        except OSError as exc:
            return {"success": False, "error": f"خواندن فایل صوتی ناموفق بود: {exc}"}
        if len(audio_bytes) <= MAX_INLINE_AUDIO_BYTES:
            payload["audio_b64"] = base64.b64encode(audio_bytes).decode("ascii")
        # Larger files stay on disk; the UI plays them via the file path.
    logger.info(
        "tts.synthesize ok (%d chars, engine=%s, voice=%s)",
        result["chars"],
        result["engine"],
        result["voice"],
    )
    return payload


HANDLERS = {
    "tts.engines": tts_engines,
    "tts.voices": tts_voices,
    "tts.synthesize": tts_synthesize,
}
