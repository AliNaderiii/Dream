"""Honesty tests for the ``tts.*`` bridge and the real TTS engines.

Everything here runs against fakes for the engines themselves (no network,
no onnxruntime): the contract under test is that availability is reported
truthfully, inputs are validated, and a failure surfaces as a clear error —
never as simulated audio.
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import pytest

from dream.bridge import methods_tts as mt
from dream.bridge.errors import BridgeError
from dream.bridge.methods_tts import HANDLERS
from dream.speech import tts as tts_mod


def run(handler, **params):
    return asyncio.run(handler(params))


# --------------------------------------------------------------------------- #
# Text normalisation (pure)
# --------------------------------------------------------------------------- #


def test_normalize_unifies_arabic_letters():
    # Arabic yeh/kaf (ي ك) become their Persian equivalents (ی ک)
    out = tts_mod.normalize_speech_text("ي.read كتب")
    assert "ی" in out and "ک" in out
    assert "ي" not in out and "ك" not in out


def test_normalize_letters_digits_zwnj_emoji():
    src = "سلام\n\nدنیا   ۱۲۳"
    out = tts_mod.normalize_speech_text(src)
    assert out == "سلام دنیا 123"

    # Arabic yeh/kaf become Persian, ZWNJ and emoji vanish, whitespace collapses
    out = tts_mod.normalize_speech_text("كتابِ يِ من\u200cمی‌خوانم 🎙️😊")
    assert "ک" in out and "ی" in out
    assert "\u200c" not in out and "🎙" not in out and "😊" not in out
    assert "  " not in out


def test_normalize_strips_various_emoji_ranges():
    out = tts_mod.normalize_speech_text("به\u200dخیر ⭐ مطلع")
    assert out == "به خیر مطلع"


# --------------------------------------------------------------------------- #
# Engine / voice listing honesty
# --------------------------------------------------------------------------- #


def test_engines_listing_is_honest(monkeypatch):
    monkeypatch.setattr(tts_mod, "_edge_available", lambda: False)
    monkeypatch.setattr(tts_mod, "_piper_available", lambda: False)
    res = run(HANDLERS["tts.engines"])
    assert res["success"] is True
    assert [e["id"] for e in res["engines"]] == ["edge", "piper"]
    assert all(e["available"] is False for e in res["engines"])
    assert res["engines"][0]["kind"] == "online"
    assert res["engines"][1]["kind"] == "offline"


def test_voices_listing_marks_downloaded(monkeypatch, tmp_path):
    monkeypatch.setattr(tts_mod, "_piper_available", lambda: True)
    monkeypatch.setattr(tts_mod, "_edge_available", lambda: False)

    def fake_bundled(key):
        return tmp_path if key == "reza" else None

    monkeypatch.setattr(tts_mod, "_bundled_voice_files", fake_bundled)
    res = run(HANDLERS["tts.voices"], engine="piper")
    voices = {v["id"]: v for v in res["voices"]}
    assert set(voices) == set(tts_mod.PIPER_VOICES)
    assert voices["reza"]["downloaded"] is True
    assert voices["ganji"]["downloaded"] is False


def test_voices_rejects_unknown_engine():
    with pytest.raises(BridgeError):
        run(HANDLERS["tts.voices"], engine="siri")


# --------------------------------------------------------------------------- #
# Parameter validation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "params",
    [
        {"text": ""},
        {"text": "   "},
        {"text": None},
        {"text": 123},
        {"text": "x" * (tts_mod.MAX_TEXT_CHARS + 1)},
        {"text": "سلام", "engine": "siri"},
        {"text": "سلام", "speed": 0.1},
        {"text": "سلام", "speed": 5},
        {"text": "سلام", "speed": "fast"},
        {"text": "سلام", "with_audio": "yes"},
    ],
)
def test_synthesize_rejects_bad_params(params):
    with pytest.raises(BridgeError):
        run(HANDLERS["tts.synthesize"], **params)


def test_synthesize_rejects_sensitive_output_path():
    with pytest.raises(BridgeError):
        run(HANDLERS["tts.synthesize"], text="سلام", output_path="C:\\Windows\\system32\\x.wav")


# --------------------------------------------------------------------------- #
# Synthesis routing (faked engines)
# --------------------------------------------------------------------------- #


@pytest.fixture()
def fake_engine(monkeypatch, tmp_path):
    """Replace both engine backends with deterministic fakes."""
    calls: dict[str, object] = {}

    def fake_synth(text, engine, voice, speed, output_path):
        calls.update(text=text, engine=engine, voice=voice, speed=speed)
        resolved = "edge" if engine in ("", "auto", "edge") else engine
        suffix = ".mp3" if resolved == "edge" else ".wav"
        target = Path(output_path) if output_path else tmp_path / f"out{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"FAKE-AUDIO-" + text.encode("utf-8"))
        return {
            "success": True,
            "simulated": False,
            "engine": resolved,
            "engine_kind": "online" if resolved == "edge" else "offline",
            "voice": voice or ("farid" if resolved == "edge" else "reza"),
            "voice_label": "fake",
            "audio_path": str(target),
            "mime": "audio/mpeg" if resolved == "edge" else "audio/wav",
            "sample_rate": 22050 if resolved != "edge" else None,
            "duration": 1.25 if resolved != "edge" else None,
            "bytes": target.stat().st_size,
            "latency_ms": 42,
            "chars": len(text),
        }

    monkeypatch.setattr(tts_mod, "synthesize_speech", fake_synth)
    # Patch the bridge module's own binding too — it imported the symbol
    # directly. NOTE: mt is imported at module top so it is the very module
    # object HANDLERS was built from, even if some other test reloads it.
    monkeypatch.setattr(mt, "synthesize_speech", fake_synth)
    return calls


def test_synthesize_returns_inline_audio(fake_engine):
    res = run(HANDLERS["tts.synthesize"], text="سلام رویا", engine="piper", voice="reza")
    assert res["success"] is True
    assert res["simulated"] is False
    assert res["engine"] == "piper"
    assert res["voice"] == "reza"
    assert base64.b64decode(res["audio_b64"]).startswith(b"FAKE-AUDIO-")
    assert fake_engine["speed"] == 1.0


def test_synthesize_can_skip_inline_audio(fake_engine):
    res = run(HANDLERS["tts.synthesize"], text="سلام", with_audio=False)
    assert res["success"] is True
    assert "audio_b64" not in res
    assert res["audio_path"].endswith((".mp3", ".wav"))


def test_synthesize_failure_is_honest(monkeypatch):
    def boom(*a, **k):
        raise tts_mod.TTSError("سرویس صدای آنلاین پاسخ نداد")

    monkeypatch.setattr(mt, "synthesize_speech", boom)
    res = run(HANDLERS["tts.synthesize"], text="سلام")
    assert res["success"] is False
    assert "پاسخ نداد" in res["error"]


def test_synthesize_without_any_engine_is_honest(monkeypatch):
    monkeypatch.setattr(tts_mod, "_edge_available", lambda: False)
    monkeypatch.setattr(tts_mod, "_piper_available", lambda: False)
    res = run(HANDLERS["tts.synthesize"], text="سلام")
    assert res["success"] is False
    assert "pip install" in res["error"]


def test_synthesize_rejects_unknown_voice_for_engine():
    with pytest.raises(tts_mod.TTSError):
        tts_mod.synthesize_speech("سلام", engine="edge", voice="reza")
    with pytest.raises(tts_mod.TTSError):
        tts_mod.synthesize_speech("سلام", engine="piper", voice="farid")


# --------------------------------------------------------------------------- #
# Data-URI helper
# --------------------------------------------------------------------------- #


def test_audio_to_data_uri(tmp_path):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"ID3xxxxx")
    uri = tts_mod.audio_to_data_uri(str(f), "audio/mpeg")
    assert uri.startswith("data:audio/mpeg;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == b"ID3xxxxx"


def test_audio_to_data_uri_size_cap(tmp_path, monkeypatch):
    f = tmp_path / "big.wav"
    f.write_bytes(b"x" * 128)
    monkeypatch.setattr(tts_mod, "MAX_INLINE_AUDIO_BYTES", 8)
    with pytest.raises(tts_mod.TTSError):
        tts_mod.audio_to_data_uri(str(f), "audio/wav")


def test_wav_container_is_valid_riff():
    pcm = bytes(range(256)) * 2
    wav = tts_mod._wav_bytes(pcm, 22050)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    assert wav[36:40] == b"data"
    assert int.from_bytes(wav[40:44], "little") == len(pcm)
    assert wav[44:] == pcm


def test_handlers_registered_with_expected_names():
    assert set(HANDLERS) == {"tts.engines", "tts.voices", "tts.synthesize"}


def test_result_is_json_serialisable(fake_engine):
    res = run(HANDLERS["tts.synthesize"], text="سلام")
    json.dumps(res)  # must not raise — the bridge transports JSON
