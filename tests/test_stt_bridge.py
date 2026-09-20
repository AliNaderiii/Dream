"""Tests for the ``stt.transcribe`` bridge method.

The transcriber is resolved at test runtime through ``importlib`` (the
extension-seam tests evict ``dream.bridge.methods_*`` from ``sys.modules``).
"""

from __future__ import annotations

import asyncio
import importlib

import pytest

from dream.bridge.errors import BridgeError
from dream.speech.whisper_stt import WhisperSTTError


class FakeTranscriber:
    def __init__(self, available: bool = True, fail: bool = False) -> None:
        self.available = available
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def is_available(self) -> bool:
        return self.available

    def transcribe_file(self, path: str, language: str = "fa") -> dict:
        self.calls.append((path, language))
        if self.fail:
            raise WhisperSTTError("audio file 'x.oga' not found")
        return {
            "text": "سلام گزارش صوتی واقعی",
            "duration": 4.0,
            "language": "fa",
            "engine": "faster-whisper (base)",
            "simulated": False,
        }


@pytest.fixture()
def transcriber(monkeypatch: pytest.MonkeyPatch) -> FakeTranscriber:
    module = importlib.import_module("dream.bridge.methods_stt")
    fake = FakeTranscriber()
    monkeypatch.setattr(module, "get_whisper_transcriber", lambda: fake)
    return fake


def run(coro):
    return asyncio.run(coro)


def test_handlers_registered() -> None:
    module = importlib.import_module("dream.bridge.methods_stt")
    assert set(module.HANDLERS) == {"stt.transcribe"}


def test_file_path_validation(transcriber: FakeTranscriber) -> None:
    module = importlib.import_module("dream.bridge.methods_stt")
    with pytest.raises(BridgeError, match="non-empty string"):
        run(module.stt_transcribe({}))
    with pytest.raises(BridgeError, match="at most 4096"):
        run(module.stt_transcribe({"file_path": "x" * 4097}))
    with pytest.raises(BridgeError, match="sensitive system path"):
        run(module.stt_transcribe({"file_path": "\\\\server\\share\\voice.oga"}))
    assert transcriber.calls == []


def test_language_validation(transcriber: FakeTranscriber) -> None:
    module = importlib.import_module("dream.bridge.methods_stt")
    with pytest.raises(BridgeError, match="fa, en, auto"):
        run(module.stt_transcribe({"file_path": "voice.oga", "language": "ar"}))
    assert transcriber.calls == []


def test_unavailable_engine_answers_honestly(transcriber: FakeTranscriber) -> None:
    module = importlib.import_module("dream.bridge.methods_stt")
    transcriber.available = False
    result = run(module.stt_transcribe({"file_path": "voice.oga"}))
    assert result["success"] is False
    assert result["available"] is False
    assert "pip install" in result["error"]
    assert transcriber.calls == []


def test_transcription_success_passthrough(transcriber: FakeTranscriber) -> None:
    module = importlib.import_module("dream.bridge.methods_stt")
    result = run(
        module.stt_transcribe({"file_path": "C:\\Users\\alina\\voice.oga", "language": "fa"})
    )
    assert result["success"] is True
    assert result["available"] is True
    assert result["engine"] == "faster-whisper (base)"
    assert result["text"] == "سلام گزارش صوتی واقعی"
    assert transcriber.calls == [("C:\\Users\\alina\\voice.oga", "fa")]


def test_engine_failure_maps_to_success_false(transcriber: FakeTranscriber) -> None:
    module = importlib.import_module("dream.bridge.methods_stt")
    transcriber.fail = True
    result = run(module.stt_transcribe({"file_path": "voice.oga"}))
    assert result["success"] is False
    assert result["available"] is True
    assert "not found" in result["error"]
