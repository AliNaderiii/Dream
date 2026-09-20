"""``stt.*`` JSON-RPC bridge methods.

Discovered automatically by :mod:`dream.bridge.extensions`.

=================================  ==================================================
``stt.transcribe``                Transcribe one audio file (faster-whisper, optional)
=================================  ==================================================

faster-whisper is an optional extra (``pip install ".[stt]"``). When it is
absent the method answers honestly with ``available: false`` and an install
hint instead of a simulated transcript.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from dream.bridge.errors import invalid_params
from dream.security.pathsafety import is_sensitive_path
from dream.speech.whisper_stt import WhisperSTTError, get_whisper_transcriber

logger = logging.getLogger(__name__)

__all__ = ["HANDLERS"]

INSTALL_HINT = 'faster-whisper is not installed — install with: pip install ".[stt]"'


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(params, dict):
        merged.update(params)
    merged.update(kwargs)
    return merged


def _file_path(data: dict[str, Any]) -> str:
    file_path = data.get("file_path")
    if not isinstance(file_path, str) or not file_path.strip():
        raise invalid_params("file_path must be a non-empty string")
    if len(file_path) > 4096:
        raise invalid_params("file_path must be at most 4096 characters")
    file_path = file_path.strip()
    if is_sensitive_path(file_path):
        raise invalid_params("Permission denied: file_path is a sensitive system path")
    return file_path


def _language(data: dict[str, Any]) -> str:
    language = data.get("language", "fa")
    if not isinstance(language, str) or language not in ("fa", "en", "auto"):
        raise invalid_params("language must be one of: fa, en, auto")
    return language


async def stt_transcribe(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Transcribe an audio file. Params: ``file_path``, ``language`` (fa/en/auto)."""
    data = _params(params, kwargs)
    file_path = _file_path(data)
    language = _language(data)
    transcriber = get_whisper_transcriber()
    if not transcriber.is_available():
        logger.info("stt.transcribe refused: faster-whisper not installed")
        return {"success": False, "available": False, "engine": None, "error": INSTALL_HINT}
    try:
        result = await asyncio.to_thread(transcriber.transcribe_file, file_path, language)
    except WhisperSTTError as exc:
        return {"success": False, "available": True, "error": str(exc)}
    # Privacy: never log the transcript itself, only its length.
    logger.info("stt.transcribe ok (%d chars)", len(result.get("text", "")))
    return {"success": True, "available": True, **result}


HANDLERS = {
    "stt.transcribe": stt_transcribe,
}
