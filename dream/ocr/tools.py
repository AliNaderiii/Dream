"""LLM Tool bindings for Document OCR and Financial Invoice/Receipt extraction."""

from __future__ import annotations

from typing import Any

from dream.ocr.engine import OCREngine
from dream.ocr.types import DocumentType
from dream.security.pathsafety import is_sensitive_path

_GLOBAL_OCR_ENGINE: OCREngine | None = None


def get_global_ocr_engine() -> OCREngine:
    """Get or initialize singleton OCREngine."""
    global _GLOBAL_OCR_ENGINE
    if _GLOBAL_OCR_ENGINE is None:
        _GLOBAL_OCR_ENGINE = OCREngine()
    return _GLOBAL_OCR_ENGINE


def reset_global_ocr_engine() -> None:
    """Reset OCREngine singleton instance."""
    global _GLOBAL_OCR_ENGINE
    _GLOBAL_OCR_ENGINE = None


def ocr_extract_document(
    file_path: str,
    document_type: str = "general",
) -> dict[str, Any]:
    """Extract text, tables, and key-values from a document or image file."""
    if is_sensitive_path(file_path):
        return {
            "success": False,
            "error": f"Permission denied: '{file_path}' is a sensitive system path.",
        }

    engine = get_global_ocr_engine()

    doc_enum = DocumentType.GENERAL
    try:
        doc_enum = DocumentType(document_type.lower())
    except ValueError:
        pass

    try:
        res = engine.extract_document(file_path, doc_enum)
        return {"success": True, **res.to_dict()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def ocr_extract_invoice(file_path: str) -> dict[str, Any]:
    """Extract invoice fields (Total Amount, Date, Tax, IBAN, Tracking Code)."""
    return ocr_extract_document(file_path, document_type="invoice")


def get_ocr_tools() -> list[Any]:
    """Return OCR tool functions for agent registration."""
    return [
        ocr_extract_document,
        ocr_extract_invoice,
    ]
