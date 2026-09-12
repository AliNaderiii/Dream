"""Domain types and data models for Document OCR, Table Parsing, and Key-Value Extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DocumentType(str, Enum):
    """Classified document category for targeted schema extraction."""

    GENERAL = "general"
    INVOICE = "invoice"
    RECEIPT = "receipt"
    ID_CARD = "id_card"
    CONTRACT = "contract"
    FORM = "form"


@dataclass(slots=True)
class BoundingBox:
    """Coordinates of a recognized text region or bounding box."""

    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict[str, int]:
        """Serialize bounding box to dictionary."""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass(slots=True)
class OCRBlock:
    """Individual line or recognized block with spatial position and reading direction."""

    text: str
    confidence: float
    bbox: BoundingBox
    direction: str = "rtl"  # "rtl" for Persian/Arabic, "ltr" for English
    line_number: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize OCR text block to dictionary."""
        return {
            "text": self.text,
            "confidence": round(self.confidence, 3),
            "bbox": self.bbox.to_dict(),
            "direction": self.direction,
            "line_number": self.line_number,
        }


@dataclass(slots=True)
class OCRResult:
    """Extracted text, spatial layout, tables, and structured invoice key-values."""

    file_path: str
    document_type: DocumentType
    raw_text: str
    cleaned_text: str
    language: str = "fa"
    confidence: float = 0.95
    blocks: list[OCRBlock] = field(default_factory=list)
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    tables: list[list[list[str]]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize OCR extraction result to dictionary."""
        return {
            "file_path": self.file_path,
            "document_type": self.document_type.value,
            "cleaned_text": self.cleaned_text,
            "language": self.language,
            "confidence": round(self.confidence, 3),
            "blocks_count": len(self.blocks),
            "blocks": [b.to_dict() for b in self.blocks],
            "extracted_fields": self.extracted_fields,
            "tables": self.tables,
            "metadata": self.metadata,
        }
