"""``pdf.*`` JSON-RPC bridge methods.

Discovered automatically by :mod:`dream.bridge.extensions`.

=================================  ==================================================
``pdf.export_report``             Render a structured report to a Persian PDF file
=================================  ==================================================
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from dream.bridge.errors import invalid_params
from dream.reporting.pdf import ReportError, build_report_pdf, validate_report
from dream.security.pathsafety import is_sensitive_path

logger = logging.getLogger("dream.bridge.pdf")

__all__ = ["HANDLERS"]


def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(params, dict):
        merged.update(params)
    merged.update(kwargs)
    return merged


def _output_path(data: dict[str, Any]) -> str:
    output_path = data.get("output_path")
    if not isinstance(output_path, str) or not output_path.strip():
        raise invalid_params("output_path must be a non-empty string")
    if len(output_path) > 4096:
        raise invalid_params("output_path must be at most 4096 characters")
    output_path = output_path.strip()
    if not output_path.lower().endswith(".pdf"):
        raise invalid_params("output_path must end with .pdf")
    if is_sensitive_path(output_path):
        raise invalid_params("Permission denied: output_path is a sensitive system path")
    return output_path


async def pdf_export_report(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Render a report to a Persian PDF. Params: ``report``, ``output_path``."""
    data = _params(params, kwargs)
    report = data.get("report")
    if not isinstance(report, dict):
        raise invalid_params("report must be an object with a title and sections")
    output_path = _output_path(data)

    def _build() -> dict[str, Any]:
        validate_report(report)  # raises ReportError on invalid content
        parent = Path(output_path).parent
        if str(parent) and not parent.exists():
            os.makedirs(parent, exist_ok=True)
        return build_report_pdf(report, output_path)

    try:
        result = await asyncio.to_thread(_build)
        # Privacy: only the final path is logged, never report content.
        logger.info("pdf.export_report wrote %s", result.get("file_path"))
        return {"success": True, **result}
    except ReportError as exc:
        raise invalid_params(f"invalid report: {exc}") from exc
    except OSError as exc:
        return {"success": False, "error": f"could not write PDF file: {exc}"}


HANDLERS = {
    "pdf.export_report": pdf_export_report,
}
