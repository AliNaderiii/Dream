"""Document OCR and Key-Value Extraction Subsystem."""

from .engine import OCREngine
from .slash import handle_ocr_command
from .tools import (
    get_global_ocr_engine,
    get_ocr_tools,
    ocr_extract_document,
    ocr_extract_invoice,
    reset_global_ocr_engine,
)
from .types import BoundingBox, DocumentType, OCRBlock, OCRResult

__all__ = [
    "BoundingBox",
    "DocumentType",
    "OCRBlock",
    "OCREngine",
    "OCRResult",
    "get_global_ocr_engine",
    "get_ocr_tools",
    "handle_ocr_command",
    "ocr_extract_document",
    "ocr_extract_invoice",
    "reset_global_ocr_engine",
]
