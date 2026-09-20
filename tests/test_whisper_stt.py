"""Tests for the optional faster-whisper STT wrapper.

No test here needs faster-whisper installed: availability, model resolution,
and failure caching are all exercised through deterministic seams.
"""

from __future__ import annotations

import pytest

from dream.speech.whisper_stt import (
    DEFAULT_WHISPER_MODEL,
    WHISPER_MODEL_ENV,
    WhisperSTTError,
    WhisperTranscriber,
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
