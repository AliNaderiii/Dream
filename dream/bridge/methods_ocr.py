"""``ocr.*`` JSON-RPC bridge methods.

Discovered automatically by :mod:`dream.bridge.extensions`.
Exposes the Document OCR and Key-Value Extraction Subsystem:

================================  ================================================
``ocr.extract``                  Extract text, blocks, tables and key-value fields
``ocr.extract_invoice``          Extract invoice fields (amount, date, tax, IBAN)
================================  ================================================
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from dream.bridge.errors import invalid_params
from dream.ocr.tools import ocr_extract_document, ocr_extract_invoice

logger = logging.getLogger("dream.bridge.ocr")

__all__ = ["HANDLERS"]


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(params, dict):
        merged.update(params)
    merged.update(kwargs)
    return merged


def _file_path(data: dict[str, Any]) -> str:
    file_path = data.get("file_path")
    if not isinstance(file_path, str) or not file_path.strip():
        raise invalid_params("file_path must be a non-empty string")
    if len(file_path) > 4096:
        raise invalid_params("file_path must be at most 4096 characters")
    return file_path.strip()


async def ocr_extract(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Extract document text and fields. Params: ``file_path``, ``document_type``."""
    data = _params(params, kwargs)
    file_path = _file_path(data)
    document_type = data.get("document_type", "general")
    if not isinstance(document_type, str) or not document_type.strip():
        raise invalid_params("document_type must be a non-empty string")
    if len(document_type) > 64:
        raise invalid_params("document_type must be at most 64 characters")
    return await asyncio.to_thread(ocr_extract_document, file_path, document_type.strip())


async def ocr_extract_invoice_bridge(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Extract invoice key-value fields. Params: ``file_path``."""
    data = _params(params, kwargs)
    file_path = _file_path(data)
    return await asyncio.to_thread(ocr_extract_invoice, file_path)


HANDLERS = {
    "ocr.extract": ocr_extract,
    "ocr.extract_invoice": ocr_extract_invoice_bridge,
}
