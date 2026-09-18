"""Tests for Desktop Document OCR Bridge and JSON-RPC Methods."""

from __future__ import annotations

import asyncio

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.extensions import Registry
from dream.bridge.methods_ocr import HANDLERS, ocr_extract, ocr_extract_invoice_bridge


def test_ocr_bridge_extension_discovery():
    """Verify ocr.* methods are automatically registered in the Bridge Registry."""
    handlers = Registry.publish({})
    assert "ocr.extract" in handlers
    assert "ocr.extract_invoice" in handlers
    assert handlers["ocr.extract"] is HANDLERS["ocr.extract"]
    assert handlers["ocr.extract_invoice"] is HANDLERS["ocr.extract_invoice"]


def test_ocr_extract_rejects_invalid_params():
    """file_path must be a non-empty string and document_type a short string."""
    with pytest.raises(BridgeError):
        asyncio.run(ocr_extract({}))
    with pytest.raises(BridgeError):
        asyncio.run(ocr_extract({"file_path": "   "}))
    with pytest.raises(BridgeError):
        asyncio.run(ocr_extract({"file_path": 123}))
    with pytest.raises(BridgeError):
        asyncio.run(ocr_extract({"file_path": "a.png", "document_type": 7}))
    with pytest.raises(BridgeError):
        asyncio.run(ocr_extract_invoice_bridge({}))


def test_ocr_extract_from_text_file(tmp_path):
    """A UTF-8 text file is read, cleaned and profiled as a Persian document."""
    doc = tmp_path / "report.txt"
    doc.write_text("گزارش روزانه پروژه\nمبلغ کل: ۱,۵۰۰,۰۰۰ تومان\n", encoding="utf-8")

    async def _test():
        res = await ocr_extract({"file_path": str(doc)})
        assert res["success"] is True
        assert res["language"] == "fa"
        assert "گزارش" in res["cleaned_text"]
        assert res["blocks_count"] >= 1
        assert res["file_path"] == str(doc)

    asyncio.run(_test())


def test_ocr_extract_invoice_fields(tmp_path):
    """Invoice parsing returns total-amount and date key-value fields."""
    doc = tmp_path / "invoice.txt"
    doc.write_text(
        "فاکتور فروش خدمات\nتاریخ: ۱۴۰۳/۰۶/۲۵\nمبلغ کل: ۱۵,۰۰۰,۰۰۰ تومان\n"
        "مالیات: ۱,۵۰۰,۰۰۰ تومان\nشبا: IR820120000000012345678901\n",
        encoding="utf-8",
    )

    async def _test():
        res = await ocr_extract_invoice_bridge({"file_path": str(doc)})
        assert res["success"] is True
        fields = res["extracted_fields"]
        assert "total_amount" in fields
        assert "date" in fields

    asyncio.run(_test())


def test_ocr_extract_missing_file_returns_unsuccessful(tmp_path):
    """A missing file yields success=False with the error message (no RPC error)."""
    missing = tmp_path / "missing.png"

    async def _test():
        res = await ocr_extract({"file_path": str(missing)})
        assert res["success"] is False
        assert "not found" in res["error"].lower()

    asyncio.run(_test())


def test_ocr_extract_refuses_sensitive_paths():
    """Sensitive paths (e.g. network shares) are refused by the path guard."""

    async def _test():
        res = await ocr_extract({"file_path": "//server/share/secret.png"})
        assert res["success"] is False
        assert "Permission denied" in res["error"]

    asyncio.run(_test())
