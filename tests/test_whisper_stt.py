"""Tests for the optional faster-whisper STT wrapper.

No test here needs faster-whisper installed: availability, model resolution,
and failure caching are all exercised through deterministic seams.
"""

from __future__ import annotations

import sys
import types

import pytest

from dream.speech.whisper_stt import (
    DEFAULT_WHISPER_MODEL,
    MODELS_DIR_ENV,
    WHISPER_MODEL_ENV,
    WhisperSTTError,
    WhisperTranscriber,
    _bundled_model_path,
    _resolve_model_id,
)


class TestModelResolution:
    def test_default_model_is_base(self) -> None:
        assert DEFAULT_WHISPER_MODEL == "base"
        assert _resolve_model_id(None) == "base"

    def test_explicit_model_overrides_default(self) -> None:
        assert _resolve_model_id("tiny") == "tiny"

    def test_environment_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(WHISPER_MODEL_ENV, "small")
        assert _resolve_model_id(None) == "small"
        # An explicit argument still wins over the environment.
        assert _resolve_model_id("tiny") == "tiny"

    def test_unknown_model_is_rejected(self) -> None:
        with pytest.raises(WhisperSTTError, match="unknown whisper model"):
            _resolve_model_id("gpt-4o-audio")


class TestTranscriber:
    def test_unknown_model_rejected_at_construction(self) -> None:
        with pytest.raises(WhisperSTTError, match="unknown whisper model"):
            WhisperTranscriber("bogus")

    def test_missing_audio_file_raises_before_model_load(self, tmp_path) -> None:
        transcriber = WhisperTranscriber("tiny")
        with pytest.raises(WhisperSTTError, match="not found"):
            transcriber.transcribe_file(str(tmp_path / "missing.wav"))
        # The model was never touched, so a later call can still attempt a load.
        assert transcriber._model is None

    def test_oversized_audio_is_refused(self, tmp_path) -> None:
        big = tmp_path / "big.wav"
        big.write_bytes(b"\0" * (25 * 1024 * 1024 + 1))
        transcriber = WhisperTranscriber("tiny")
        with pytest.raises(WhisperSTTError, match="25 MB"):
            transcriber.transcribe_file(str(big))

    def test_load_failure_is_cached_and_raised_again(self) -> None:
        transcriber = WhisperTranscriber("tiny")
        transcriber._load_failed = "whisper model 'tiny' failed to load: boom"
        with pytest.raises(WhisperSTTError, match="boom"):
            transcriber._load()
        # Second call raises the cached message without retrying.
        with pytest.raises(WhisperSTTError, match="boom"):
            transcriber._load()

    def test_availability_is_a_plain_boolean(self) -> None:
        # Whatever the environment (faster-whisper installed or not), the
        # answer must be a bool and never raise.
        assert isinstance(WhisperTranscriber("tiny").is_available(), bool)


class TestBundledModelPath:
    def _make_model(self, root, model_id: str = "base") -> None:
        model_dir = root / "models" / f"faster-whisper-{model_id}"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "model.bin").write_bytes(b"x" * 16)

    def test_env_override_wins(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._make_model(tmp_path)
        monkeypatch.setenv(MODELS_DIR_ENV, str(tmp_path / "models"))
        resolved = _bundled_model_path("base")
        assert resolved == tmp_path / "models" / "faster-whisper-base"

    def test_sys_prefix_fallback(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._make_model(tmp_path, "tiny")
        monkeypatch.delenv(MODELS_DIR_ENV, raising=False)
        monkeypatch.setattr(sys, "prefix", str(tmp_path))
        # The bundled layout is <python>/models/faster-whisper-<id>.
        assert _bundled_model_path("tiny") == tmp_path / "models" / "faster-whisper-tiny"
        # A different model id has no bundled directory -> falls back to None.
        assert _bundled_model_path("base") is None

    def test_incomplete_download_does_not_count(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        partial = tmp_path / "models" / "faster-whisper-base"
        partial.mkdir(parents=True)
        (partial / "model.bin").write_bytes(b"")  # exists but empty dir would also do
        monkeypatch.setenv(MODELS_DIR_ENV, str(tmp_path / "models"))
        monkeypatch.setattr(sys, "prefix", str(tmp_path / "elsewhere"))
        # model.bin must be a real file; an empty one still counts as present,
        # but a *missing* file must not:
        (partial / "model.bin").unlink()
        assert _bundled_model_path("base") is None

    def test_no_bundled_models_returns_none(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(MODELS_DIR_ENV, raising=False)
        monkeypatch.setattr(sys, "prefix", str(tmp_path))
        assert _bundled_model_path("base") is None

    def test_load_prefers_the_bundled_directory(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._make_model(tmp_path)
        monkeypatch.setenv(MODELS_DIR_ENV, str(tmp_path / "models"))
        created: dict[str, object] = {}

        class _FakeWhisperModel:
            def __init__(self, model: str, device: str, compute_type: str) -> None:
                created["model"] = model
                created["device"] = device
                created["compute_type"] = compute_type

        fake_module = types.ModuleType("faster_whisper")
        fake_module.WhisperModel = _FakeWhisperModel
        monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)

        transcriber = WhisperTranscriber()
        transcriber._load()
        assert created["model"] == str(tmp_path / "models" / "faster-whisper-base")
        assert created["device"] == "cpu"
        assert created["compute_type"] == "int8"
