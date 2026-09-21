"""Real speech-to-text via faster-whisper (optional dependency).

faster-whisper is an *optional* extra (``pip install ".[stt]"``): the module
imports it lazily, loads one model per process behind a lock, and reports
availability honestly. Callers (the Telegram report bot, the ``stt.transcribe``
bridge) degrade to clearly-labelled fallbacks when it is absent — the honesty
rule of this codebase: never present a simulated transcript as a real one.

Telegram voice notes are OGG/Opus; faster-whisper decodes them through PyAV,
so no transcoding step is needed on this path.

Offline models: before touching the network, ``_bundled_model_path`` looks for
a pre-downloaded model directory — ``DREAM_WHISPER_MODELS_DIR`` first, then
``<sys.prefix>/models/`` (exactly where the Windows *full* installer drops the
pinned ``base`` model next to the embedded interpreter). A directory only
counts when it holds ``model.bin``, so a partial download never shadows the
Hugging Face fallback.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_WHISPER_MODEL",
    "MODELS_DIR_ENV",
    "WHISPER_MODEL_ENV",
    "WhisperSTTError",
    "WhisperTranscriber",
    "get_whisper_transcriber",
    "reset_whisper_transcriber",
]

#: Model id used unless the environment overrides it (tiny/base/small/…).
DEFAULT_WHISPER_MODEL = "base"
WHISPER_MODEL_ENV = "DREAM_WHISPER_MODEL"
#: Optional override pointing at a directory of pre-downloaded models
#: (``<root>/faster-whisper-<id>``). The Windows full installer ships one.
MODELS_DIR_ENV = "DREAM_WHISPER_MODELS_DIR"
ALLOWED_MODELS = {"tiny", "base", "small", "medium", "large-v3", "distil-small.en"}
MAX_AUDIO_BYTES = 25 * 1024 * 1024


class WhisperSTTError(RuntimeError):
    """A safe-to-display speech-to-text failure."""


def _resolve_model_id(raw: str | None = None) -> str:
    configured = os.environ.get(WHISPER_MODEL_ENV, "") if raw is None else raw
    model = configured.strip() or DEFAULT_WHISPER_MODEL
    if model not in ALLOWED_MODELS:
        raise WhisperSTTError(
            f"unknown whisper model '{model}' (set {WHISPER_MODEL_ENV} to one of "
            + ", ".join(sorted(ALLOWED_MODELS))
            + ")"
        )
    return model


def _bundled_model_path(model_id: str) -> Path | None:
    """Return a locally bundled model directory for *model_id*, if present.

    Lookup order: ``DREAM_WHISPER_MODELS_DIR`` (explicit override), then
    ``<sys.prefix>/models`` — the layout the Windows full installer bakes in
    next to the embedded CPython. Returns ``None`` when nothing complete is
    found, leaving the normal Hugging Face download path in charge.
    """
    candidate_roots: list[Path] = []
    override = os.environ.get(MODELS_DIR_ENV, "").strip()
    if override:
        candidate_roots.append(Path(override))
    candidate_roots.append(Path(sys.prefix) / "models")
    for root in candidate_roots:
        candidate = root / f"faster-whisper-{model_id}"
        if (candidate / "model.bin").is_file():
            return candidate
    return None


class Transcriber(Protocol):
    """The seam the report bot and tests program against."""

    def is_available(self) -> bool: ...

    def transcribe_file(self, path: str, language: str = "fa") -> dict[str, Any]: ...


class WhisperTranscriber:
    """Lazy, process-wide faster-whisper wrapper.

    The heavy import and the model load happen once, on first use, behind a
    lock — a missing library costs one import attempt, nothing more.
    """

    def __init__(self, model_id: str | None = None) -> None:
        self._model_id = _resolve_model_id(model_id)
        self._lock = threading.Lock()
        self._model: Any = None
        self._load_failed: str | None = None

    @property
    def model_id(self) -> str:
        return self._model_id

    def is_available(self) -> bool:
        """True when faster-whisper is importable on this machine."""
        try:
            import faster_whisper  # noqa: F401
        except Exception:  # pragma: no cover - depends on the environment
            return False
        return True

    def _load(self) -> Any:
        with self._lock:
            if self._model is not None:
                return self._model
            if self._load_failed is not None:
                raise WhisperSTTError(self._load_failed)
            try:
                from faster_whisper import WhisperModel
            except Exception as exc:  # pragma: no cover - optional dependency
                self._load_failed = f"faster-whisper is not installed ({exc})"
                raise WhisperSTTError(
                    "faster-whisper is not installed — install with: pip install \".[stt]\""
                ) from None
            try:
                bundled = _bundled_model_path(self._model_id)
                if bundled is not None:
                    logger.info("using bundled whisper model at %s", bundled)
                    self._model = WhisperModel(str(bundled), device="cpu", compute_type="int8")
                else:
                    logger.info("loading whisper model '%s' (first use)", self._model_id)
                    self._model = WhisperModel(self._model_id, device="cpu", compute_type="int8")
            except Exception as exc:
                self._load_failed = f"whisper model '{self._model_id}' failed to load: {exc}"
                raise WhisperSTTError(self._load_failed) from None
            return self._model

    def transcribe_file(self, path: str, language: str = "fa") -> dict[str, Any]:
        """Transcribe one audio file. Returns text/duration/language/engine.

        Raises :class:`WhisperSTTError` for missing files, undecodable audio,
        or a missing/failed model — all safe to display.
        """
        audio = Path(path)
        if not audio.is_file():
            raise WhisperSTTError(f"audio file '{path}' not found")
        if audio.stat().st_size > MAX_AUDIO_BYTES:
            raise WhisperSTTError("audio file exceeds the 25 MB transcription limit")
        lang = language if language in ("fa", "en", "auto") else "fa"
        model = self._load()
        try:
            segments, info = model.transcribe(
                str(audio),
                language=None if lang == "auto" else lang,
                vad_filter=True,
            )
            texts: list[str] = []
            duration = 0.0
            for segment in segments:
                texts.append(segment.text.strip())
                duration = max(duration, float(segment.end))
            text = " ".join(part for part in texts if part).strip()
        except WhisperSTTError:
            raise
        except Exception as exc:
            raise WhisperSTTError(f"whisper transcription failed: {exc}") from None
        return {
            "text": text,
            "duration": round(duration, 2),
            "language": getattr(info, "language", lang),
            "engine": f"faster-whisper ({self._model_id})",
            "simulated": False,
        }


_transcriber: WhisperTranscriber | None = None
_transcriber_lock = threading.Lock()


def get_whisper_transcriber() -> WhisperTranscriber:
    global _transcriber
    with _transcriber_lock:
        if _transcriber is None:
            _transcriber = WhisperTranscriber()
        return _transcriber


def reset_whisper_transcriber() -> None:
    """Test isolation: drop the cached transcriber/model."""
    global _transcriber
    with _transcriber_lock:
        _transcriber = None
