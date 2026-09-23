"""Real text-to-speech engines — online neural (edge-tts) and offline (Piper).

The honesty rule of this codebase applies here exactly as it does to
:mod:`dream.speech.whisper_stt`: both engines are optional extras
(``pip install ".[tts]"``), availability is reported truthfully, and a
missing engine or model yields a clearly-labelled error — never a beep,
a sine wave, or any other simulated "voice".

Engines
-------

``edge``  — Microsoft neural voices through the ``edge-tts`` client (online,
            free, no API key). Persian voices: Farid (male), Dilara (female).
            Output is MP3 (24 kHz).

``piper`` — fully offline Piper VITS voices (``piper-tts`` package, which
            bundles espeak-ng data). Persian medium voices from the pinned
            ``rhasspy/piper-voices`` revision. Output is WAV (22.05 kHz).

Offline models: before touching the network, ``_bundled_voice_files`` looks
for a pre-downloaded voice next to the interpreter — ``DREAM_TTS_MODELS_DIR``
first, then ``<sys.prefix>/models/piper-voices/`` (exactly where the Windows
*full* installer drops the pinned voice). Otherwise the voice is downloaded
once, atomically, into ``~/.dream/tts/piper-voices/``.
"""

from __future__ import annotations

import asyncio
import base64
import os
import struct
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any

from dream.security.pathsafety import is_sensitive_path

__all__ = [
    "TTSError",
    "list_engines",
    "list_voices",
    "synthesize_speech",
]

#: Hard input limit — keeps synthesis bounded (about 3–5 minutes of audio).
MAX_TEXT_CHARS = 3000
#: Largest audio payload returned inline through the bridge (base64).
MAX_INLINE_AUDIO_BYTES = 8 * 1024 * 1024

SPEED_MIN = 0.5
SPEED_MAX = 2.0

#: Persian neural voices served by the edge-tts client (online).
EDGE_VOICES: dict[str, dict[str, str]] = {
    "farid": {"id": "fa-IR-FaridNeural", "label": "فرید — نورال (مرد)"},
    "dilara": {"id": "fa-IR-DilaraNeural", "label": "دلارا — نورال (زن)"},
}

#: Offline Piper voices from the pinned rhasspy/piper-voices revision.
PIPER_VOICES: dict[str, dict[str, str]] = {
    "reza": {
        "file": "fa_IR-reza_ibrahim-medium.onnx",
        "repo_path": "fa/fa_IR/reza_ibrahim/medium",
        "label": "رضا — آفلاین (مرد)",
    },
    "amir": {
        "file": "fa_IR-amir-medium.onnx",
        "repo_path": "fa/fa_IR/amir/medium",
        "label": "امیر — آفلاین (مرد)",
    },
    "ganji": {
        "file": "fa_IR-ganji-medium.onnx",
        "repo_path": "fa/fa_IR/ganji/medium",
        "label": "گنجی — آفلاین",
    },
    "ganji_adabi": {
        "file": "fa_IR-ganji_adabi-medium.onnx",
        "repo_path": "fa/fa_IR/ganji_adabi/medium",
        "label": "گنجی ادبی — آفلاین",
    },
    "gyro": {
        "file": "fa_IR-gyro-medium.onnx",
        "repo_path": "fa/fa_IR/gyro/medium",
        "label": "گایرو — آفلاین",
    },
}

#: The voice bundled by the Windows *full* installer.
PIPER_BUNDLED_VOICE = "reza"

PIPER_REPO = "rhasspy/piper-voices"
#: Revision pinned at integration time (2026-09-23) so downloads stay
#: reproducible — the same policy as the bundled Whisper model.
PIPER_REVISION = "c10ece1aade47bb51c153c893d14e5bf8e5b7117"
MODELS_DIR_ENV = "DREAM_TTS_MODELS_DIR"

TTS_INSTALL_HINT = 'no TTS engine is installed — install with: pip install ".[tts]"'

_ARABIC_TO_PERSIAN = {
    "ي": "ی",
    "ك": "ک",
    "ۀ": "ه",
    "ة": "ه",
    "ٱ": "ا",
    "إ": "ا",
    "أ": "ا",
    "ؤ": "و",
    "ئ": "ی",
}
_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_DIGIT_MAP = {ord(d): str(i) for i, d in enumerate(_PERSIAN_DIGITS)}
_DIGIT_MAP.update({ord(d): str(i) for i, d in enumerate(_ARABIC_DIGITS)})
#: Emoji / symbol / variation-selector ranges espeak cannot speak.
_DROP_RANGES = (
    (0x1F000, 0x1FAFF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF),
    (0xFE00, 0xFE0F),
    (0x200B, 0x200D),
)


class TTSError(RuntimeError):
    """A safe-to-display text-to-speech failure."""


def normalize_speech_text(text: str) -> str:
    """Normalise text for speech: unify Arabic letters, digits, strip emoji.

    Pure function (unit-tested): NFKC → Arabic→Persian letter fixes →
    Persian/Arabic digits to Latin → drop emoji/symbols/ZWNJ → collapse
    whitespace.
    """
    text = unicodedata.normalize("NFKC", text)
    for src, dst in _ARABIC_TO_PERSIAN.items():
        text = text.replace(src, dst)
    text = text.translate(_DIGIT_MAP)
    cleaned: list[str] = []
    for ch in text:
        if any(lo <= ord(ch) <= hi for lo, hi in _DROP_RANGES):
            cleaned.append(" ")
        else:
            cleaned.append(ch)
    return " ".join("".join(cleaned).split()).strip()


def _clamp_speed(speed: float) -> float:
    return min(SPEED_MAX, max(SPEED_MIN, float(speed)))


def _run_async(coro: Any) -> Any:
    """Run a coroutine from worker threads (the bridge calls via to_thread)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise TTSError("edge-tts cannot run inside a running event loop")


# --------------------------------------------------------------------------- #
# Availability
# --------------------------------------------------------------------------- #


def _edge_available() -> bool:
    try:
        import edge_tts  # noqa: F401
    except Exception:
        return False
    return True


def _piper_available() -> bool:
    try:
        import piper  # noqa: F401
    except Exception:
        return False
    return True


def _piper_user_dir() -> Path:
    return Path.home() / ".dream" / "tts" / "piper-voices"


def _bundled_voice_files(voice_key: str) -> Path | None:
    """Return the bundled model directory for a Piper voice, if complete."""
    meta = PIPER_VOICES[voice_key]
    roots: list[Path] = []
    override = os.environ.get(MODELS_DIR_ENV, "").strip()
    if override:
        roots.append(Path(override) / "piper-voices")
    roots.append(Path(sys.prefix) / "models" / "piper-voices")
    for root in roots:
        candidate = root / meta["repo_path"]
        if (candidate / meta["file"]).is_file() and (
            candidate / f"{meta['file']}.json"
        ).is_file():
            return candidate
    return None


def _download_piper_voice(voice_key: str) -> Path:
    """Download the pinned voice files atomically into the user directory."""
    meta = PIPER_VOICES[voice_key]
    target_dir = _piper_user_dir() / meta["repo_path"]
    target_dir.mkdir(parents=True, exist_ok=True)
    base = f"https://huggingface.co/{PIPER_REPO}/resolve/{PIPER_REVISION}/{meta['repo_path']}"
    for filename in (meta["file"], f"{meta['file']}.json"):
        dest = target_dir / filename
        if dest.is_file() and dest.stat().st_size > 0:
            continue
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with urllib.request.urlopen(f"{base}/{filename}", timeout=120) as resp:
                with open(tmp, "wb") as fh:
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        fh.write(chunk)
            tmp.replace(dest)
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            raise TTSError(
                f"دانلود صدای آفلاین '{voice_key}' ناموفق بود ({exc}) — "
                "اینترنت لازم است، یا نصاب full دریم را نصب کنید"
            ) from None
    return target_dir


# --------------------------------------------------------------------------- #
# Engines
# --------------------------------------------------------------------------- #


def _edge_synth(text: str, voice_key: str, speed: float, out_path: str) -> dict[str, Any]:
    """Synthesize with edge-tts (online neural). Writes MP3 to *out_path*."""
    import edge_tts

    voice_id = EDGE_VOICES[voice_key]["id"]
    rate = f"{round((_clamp_speed(speed) - 1.0) * 100):+d}%"

    async def _run() -> None:
        communicate = edge_tts.Communicate(text, voice_id, rate=rate)
        await communicate.save(out_path)

    try:
        _run_async(_run())
    except TTSError:
        raise
    except Exception as exc:
        raise TTSError(
            f"سرویس صدای آنلاین پاسخ نداد ({exc}) — اتصال اینترنت را بررسی کنید"
        ) from None
    return {"mime": "audio/mpeg", "sample_rate": None}


_piper_cache: dict[str, Any] = {}
_piper_lock = threading.Lock()


def _piper_voice(voice_key: str) -> Any:
    """Load (and cache) a Piper voice, downloading the pinned files if needed."""
    with _piper_lock:
        cached = _piper_cache.get(voice_key)
        if cached is not None:
            return cached
        model_dir = _bundled_voice_files(voice_key) or _download_piper_voice(voice_key)
        try:
            import piper
        except Exception as exc:  # pragma: no cover - optional dependency
            raise TTSError(
                f"piper-tts is not installed ({exc}) — install with: pip install \".[tts]\""
            ) from None
        try:
            voice = piper.PiperVoice.load(str(model_dir / PIPER_VOICES[voice_key]["file"]))
        except Exception as exc:
            raise TTSError(f"بارگذاری صدای آفلاین '{voice_key}' ناموفق بود: {exc}") from None
        _piper_cache[voice_key] = voice
        return voice


def _wav_bytes(pcm_int16: bytes, sample_rate: int) -> bytes:
    """Wrap raw 16-bit mono PCM in a RIFF/WAVE container."""
    byte_rate = sample_rate * 2
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm_int16),
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        byte_rate,
        2,
        16,
        b"data",
        len(pcm_int16),
    )
    return header + pcm_int16


def _piper_synth(text: str, voice_key: str, speed: float, out_path: str) -> dict[str, Any]:
    """Synthesize with Piper (offline VITS). Writes WAV to *out_path*."""
    voice = _piper_voice(voice_key)
    import piper

    config = piper.SynthesisConfig(length_scale=1.0 / _clamp_speed(speed))
    try:
        chunks = list(voice.synthesize(text, config))
    except Exception as exc:
        raise TTSError(f"ساخت صدا با موتور آفلاین ناموفق بود: {exc}") from None
    if not chunks:
        raise TTSError("موتور آفلاین صدا‌ای تولید نکرد — متن را کوتاه‌تر یا ساده‌تر کنید")
    pcm = b"".join(chunk.audio_int16_bytes for chunk in chunks)
    sample_rate = chunks[0].sample_rate
    wav = _wav_bytes(pcm, sample_rate)
    with open(out_path, "wb") as fh:
        fh.write(wav)
    return {
        "mime": "audio/wav",
        "sample_rate": sample_rate,
        "duration": round(len(pcm) / (2 * sample_rate), 2),
    }


def _resolve_engine(engine: str) -> str:
    if engine in ("", "auto"):
        if _edge_available():
            return "edge"
        if _piper_available():
            return "piper"
        raise TTSError(TTS_INSTALL_HINT)
    if engine in ("edge", "piper"):
        return engine
    raise TTSError(f"موتور صحبت ناشناخته: '{engine}' (edge | piper | auto)")


def _default_voice(engine: str) -> str:
    return "farid" if engine == "edge" else PIPER_BUNDLED_VOICE


# --------------------------------------------------------------------------- #
# Public API (used by the bridge)
# --------------------------------------------------------------------------- #


def list_engines() -> list[dict[str, Any]]:
    """Honest engine listing — availability reflects what is importable."""
    engines = [
        {
            "id": "edge",
            "name": "نورال آنلاین",
            "kind": "online",
            "available": _edge_available(),
            "note": "مایکروسافت (edge-tts) — رایگان و بدون کلید، اینترنت لازم است",
        },
        {
            "id": "piper",
            "name": "آفلاین محلی",
            "kind": "offline",
            "available": _piper_available(),
            "note": "Piper VITS — کاملاً آفلاین، صدای فارسی روی همین دستگاه",
        },
    ]
    return engines


def list_voices(engine: str = "") -> list[dict[str, Any]]:
    """Voice catalogue. Piper voices report whether the model is on disk."""
    target = _resolve_engine(engine) if engine else ""
    out: list[dict[str, Any]] = []
    if target in ("", "edge"):
        for key, meta in EDGE_VOICES.items():
            out.append(
                {
                    "id": key,
                    "label": meta["label"],
                    "engine": "edge",
                    "available": _edge_available(),
                    "downloaded": None,
                }
            )
    if target in ("", "piper"):
        for key, meta in PIPER_VOICES.items():
            downloaded = _bundled_voice_files(key) is not None or (
                _piper_user_dir() / meta["repo_path"] / meta["file"]
            ).is_file()
            out.append(
                {
                    "id": key,
                    "label": meta["label"],
                    "engine": "piper",
                    "available": _piper_available(),
                    "downloaded": downloaded,
                }
            )
    return out


def synthesize_speech(
    text: str,
    engine: str = "auto",
    voice: str = "",
    speed: float = 1.0,
    output_path: str = "",
) -> dict[str, Any]:
    """Synthesize *text* into an audio file. Returns the honest result.

    The result always carries ``simulated: False`` — this module refuses to
    ship anything that is not real speech.
    """
    if not isinstance(text, str) or not text.strip():
        raise TTSError("متنی برای گفتن نیست")
    if len(text) > MAX_TEXT_CHARS:
        raise TTSError(f"متن طولانی‌تر از حد مجاز است ({MAX_TEXT_CHARS} نویسه)")
    if output_path and is_sensitive_path(output_path):
        raise PermissionError(f"Permission denied: '{output_path}' is a sensitive system path.")

    resolved = _resolve_engine(engine)
    if resolved == "edge" and not _edge_available():
        raise TTSError('edge-tts نصب نیست — نصب با: pip install ".[tts]"')
    if resolved == "piper" and not _piper_available():
        raise TTSError('piper-tts نصب نیست — نصب با: pip install ".[tts]"')

    voice_key = voice if voice else _default_voice(resolved)
    if resolved == "edge" and voice_key not in EDGE_VOICES:
        raise TTSError(f"صدای ناشناخته: '{voice_key}' — یکی از: {', '.join(EDGE_VOICES)}")
    if resolved == "piper" and voice_key not in PIPER_VOICES:
        raise TTSError(f"صدای ناشناخته: '{voice_key}' — یکی از: {', '.join(PIPER_VOICES)}")

    label = (
        EDGE_VOICES[voice_key]["label"] if resolved == "edge" else PIPER_VOICES[voice_key]["label"]
    )
    clean = normalize_speech_text(text)
    if not clean:
        raise TTSError("بعد از پاک‌سازی متن، چیزی برای گفتن نماند")

    suffix = ".mp3" if resolved == "edge" else ".wav"
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
    else:
        with tempfile.NamedTemporaryFile(
            prefix="dream-tts-", suffix=suffix, delete=False
        ) as tmp:
            out = Path(tmp.name)

    started = time.perf_counter()
    if resolved == "edge":
        extra = _edge_synth(clean, voice_key, speed, str(out))
    else:
        extra = _piper_synth(clean, voice_key, speed, str(out))
    latency_ms = round((time.perf_counter() - started) * 1000)

    return {
        "success": True,
        "simulated": False,
        "engine": resolved,
        "engine_kind": "online" if resolved == "edge" else "offline",
        "voice": voice_key,
        "voice_label": label,
        "audio_path": str(out),
        "mime": extra["mime"],
        "sample_rate": extra.get("sample_rate"),
        "duration": extra.get("duration"),
        "bytes": out.stat().st_size,
        "latency_ms": latency_ms,
        "chars": len(clean),
    }


def audio_to_data_uri(audio_path: str, mime: str) -> str:
    """Inline small audio files as a data: URI for WebView playback."""
    data = Path(audio_path).read_bytes()
    if len(data) > MAX_INLINE_AUDIO_BYTES:
        raise TTSError("فایل صوتی برای پخش درون‌برنامه‌ای بزرگ است — از فایل روی دیسک استفاده کنید")
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
