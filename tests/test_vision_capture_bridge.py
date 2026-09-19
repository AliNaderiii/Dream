"""Tests for the real screen-capture OCR bridge (``vision.capture_screen``)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from dream.bridge import methods_vision
from dream.bridge.errors import BridgeError
from dream.bridge.extensions import Registry
from dream.bridge.methods_vision import HANDLERS, vision_capture_screen


def test_capture_bridge_extension_discovery():
    """vision.capture_screen must be auto-registered in the Bridge Registry."""
    handlers = Registry.publish({})
    assert "vision.capture_screen" in handlers
    assert handlers["vision.capture_screen"] is HANDLERS["vision.capture_screen"]


def test_capture_rejects_invalid_document_type():
    """document_type, when provided, must be a short non-empty string."""
    with pytest.raises(BridgeError):
        asyncio.run(vision_capture_screen({"document_type": 7}))
    with pytest.raises(BridgeError):
        asyncio.run(vision_capture_screen({"document_type": "   "}))
    with pytest.raises(BridgeError):
        asyncio.run(vision_capture_screen({"document_type": "x" * 65}))


def _fake_capture(text: str):
    """Build a platform-capture stub that writes a UTF-8 text file."""

    def _capture(target: Any) -> dict[str, Any]:
        path = Path(str(target))
        path.write_text(text, encoding="utf-8")
        return {
            "backend": "test-fake",
            "width": 800,
            "height": 600,
            "size_bytes": path.stat().st_size,
        }

    return _capture


def test_capture_runs_ocr_and_deletes_the_temp_file(monkeypatch):
    """A successful capture is OCRed, the temp path never leaks, and the file is gone."""
    captured: dict[str, str] = {}

    def _capture(target: Any) -> dict[str, Any]:
        path = Path(str(target))
        captured["path"] = str(path)
        path.write_text("گزارش اسکرین‌شات صفحه\nمبلغ کل: ۲,۵۰۰,۰۰۰ تومان\n", encoding="utf-8")
        return {"backend": "test-fake", "width": 1920, "height": 1080, "size_bytes": 42}

    monkeypatch.setattr(methods_vision, "capture_screen_to_file", _capture)

    async def _test() -> dict[str, Any]:
        return await vision_capture_screen({"document_type": "general"})

    res = asyncio.run(_test())
    assert res["success"] is True
    assert "گزارش" in res["cleaned_text"]
    assert res["language"] == "fa"
    assert res["file_path"] == "<screen-capture>"  # temp path never leaks
    assert res["screen"]["backend"] == "test-fake"
    assert res["screen"]["temp_deleted"] is True
    # Privacy: the screenshot file itself must not exist anymore.
    assert not Path(captured["path"]).exists()


def test_capture_invoice_document_type(monkeypatch):
    """document_type=invoice routes the screenshot through the invoice parser."""
    monkeypatch.setattr(
        methods_vision,
        "capture_screen_to_file",
        _fake_capture(
            "فاکتور فروش خدمات\nمبلغ کل: ۱۵,۰۰۰,۰۰۰ تومان\nتاریخ: ۱۴۰۳/۰۶/۲۵\n"
        ),
    )

    async def _test() -> dict[str, Any]:
        return await vision_capture_screen({"document_type": "invoice"})

    res = asyncio.run(_test())
    assert res["success"] is True
    assert res["document_type"] == "invoice"
    assert res.get("extracted_fields")


def test_capture_unsupported_platform_is_honest(monkeypatch):
    """Without a real capture backend the result is success:False, never a fake."""
    from dream.vision.capture import ScreenCaptureError

    def _fail(_target: Any) -> dict[str, Any]:
        raise ScreenCaptureError(
            "screen capture is not supported on this platform (detected 'linux')"
        )

    monkeypatch.setattr(methods_vision, "capture_screen_to_file", _fail)

    async def _test() -> dict[str, Any]:
        return await vision_capture_screen({})

    res = asyncio.run(_test())
    assert res["success"] is False
    assert "not supported" in res["error"]


def test_capture_file_is_removed_when_capture_fails(monkeypatch, tmp_path):
    """A failing capture backend must still clean up its temp file."""

    def _fail(target: Any) -> dict[str, Any]:
        raise methods_vision.ScreenCaptureError("BitBlt failed on the primary display")

    # Intercept tempfile.mkstemp so we can observe the created path.
    created: dict[str, str] = {}
    real_mkstemp = methods_vision.tempfile.mkstemp

    def _mkstemp(*args: Any, **kwargs: Any):
        fd, name = real_mkstemp(*args, **kwargs)
        created["path"] = name
        return fd, name

    monkeypatch.setattr(methods_vision.tempfile, "mkstemp", _mkstemp)
    monkeypatch.setattr(methods_vision, "capture_screen_to_file", _fail)

    async def _test() -> dict[str, Any]:
        return await vision_capture_screen({})

    res = asyncio.run(_test())
    assert res["success"] is False
    assert "BitBlt" in res["error"]
    assert not Path(created["path"]).exists()  # temp file cleaned up on failure
    assert tmp_path  # fixture only keeps the tmp dir alive for readability
