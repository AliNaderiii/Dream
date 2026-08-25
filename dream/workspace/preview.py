"""Safe file preview: whitelist types, never execute, sanitize HTML."""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from dream.workspace.errors import WorkspaceError, WorkspaceSecurityError
from dream.workspace.files import classify
from dream.workspace.paths import resolve_inside

PREVIEW_BYTES = 64 * 1024
CSV_ROWS = 200
TEXT_CHARS = 24_000

_SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_ON_ATTR = re.compile(r"""\son\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.IGNORECASE)
_JS = re.compile(r"javascript:", re.IGNORECASE)
_SECRET = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|\btoken\b|password|secret|bearer)\s*[:=]\s*\S+"
)

_WHITELIST = frozenset(
    {
        "markdown",
        "text",
        "csv",
        "tsv",
        "json",
        "code",
        "html",
        "pdf",
        "image",
        "video",
        "docx",
        "xlsx",
        "pptx",
        "jupyter",
        "file",
    }
)


def redact(text: str) -> str:
    return _SECRET.sub("[REDACTED]", text)


def sanitize_html(text: str) -> str:
    text = _SCRIPT_STYLE.sub("", text)
    text = _ON_ATTR.sub("", text)
    text = _JS.sub("", text)
    return text


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in {"script", "style"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        return "\n".join(line.strip() for line in "".join(self.parts).splitlines() if line.strip())


def _read_capped(path: Path, cap: int = PREVIEW_BYTES) -> tuple[bytes, bool]:
    with path.open("rb") as handle:
        data = handle.read(cap + 1)
    return data[:cap], len(data) > cap


def _csv_preview(text: str, dialect: str) -> dict[str, Any]:
    reader = csv.reader(io.StringIO(text), delimiter="\t" if dialect == "tsv" else ",")
    rows = []
    for index, row in enumerate(reader):
        if index > CSV_ROWS:
            break
        rows.append([redact(cell) for cell in row])
    header = rows[0] if rows else []
    body = rows[1:] if len(rows) > 1 else []
    chart = _chart_from_rows(header, body)
    return {
        "columns": header,
        "rows": body[:50],
        "row_count": len(body),
        "chart": chart,
    }


def _chart_from_rows(header: list[str], body: list[list[str]]) -> dict[str, Any] | None:
    if len(header) < 2 or not body:
        return None
    numeric_index = None
    for index in range(1, len(header)):
        values = []
        ok = True
        for row in body:
            if index >= len(row):
                ok = False
                break
            try:
                values.append(float(row[index].replace(",", "")))
            except (TypeError, ValueError):
                ok = False
                break
        if ok and values:
            numeric_index = index
            break
    if numeric_index is None:
        return None
    labels = [row[0] if row else "" for row in body[:20]]
    values = []
    for row in body[:20]:
        try:
            values.append(float(row[numeric_index].replace(",", "")))
        except (TypeError, ValueError, IndexError):
            values.append(0.0)
    return {
        "kind": "bar",
        "x": header[0],
        "y": header[numeric_index],
        "labels": labels,
        "values": values,
    }


def _xml_text(payload: bytes) -> str:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return ""
    bits = [node.text or "" for node in root.iter() if node.text]
    return redact(" ".join(bit.strip() for bit in bits if bit.strip()))


def _office_text(path: Path, member: str) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            if member not in archive.namelist():
                return ""
            with archive.open(member) as handle:
                payload = handle.read(PREVIEW_BYTES + 1)
            return _xml_text(payload[:PREVIEW_BYTES])
    except (OSError, zipfile.BadZipFile):
        return ""


def preview_file(root: Path, rel: str) -> dict[str, Any]:
    """Return a sanitized preview. Never executes the file."""
    path = resolve_inside(root, rel)
    if path.is_symlink() or path.is_dir():
        raise WorkspaceSecurityError("preview is limited to regular files")
    if not path.is_file():
        raise WorkspaceError("path not found")
    kind = classify(path, False)
    if kind not in _WHITELIST:
        kind = "file"
    payload: dict[str, Any] = {
        "path": str(path.relative_to(root)).replace("\\", "/"),
        "name": path.name,
        "type": kind,
        "size": path.stat().st_size,
        "executed": False,
        "truncated": False,
        "text": "",
        "html": "",
        "chart": None,
        "table": None,
        "warning": "",
    }
    if kind in {"text", "markdown", "code", "json"}:
        raw, truncated = _read_capped(path)
        text = redact(raw.decode("utf-8", "replace"))[:TEXT_CHARS]
        payload["text"] = text
        payload["truncated"] = truncated or len(text) >= TEXT_CHARS
        return payload
    if kind in {"csv", "tsv"}:
        raw, truncated = _read_capped(path)
        text = raw.decode("utf-8", "replace")
        table = _csv_preview(text, kind)
        payload["table"] = table
        payload["chart"] = table.get("chart")
        payload["text"] = redact(text[:4_000])
        payload["truncated"] = truncated
        return payload
    if kind == "html":
        raw, truncated = _read_capped(path)
        html = sanitize_html(raw.decode("utf-8", "replace"))
        extractor = _TextExtractor()
        extractor.feed(html)
        extractor.close()
        payload["html"] = html[:TEXT_CHARS]
        payload["text"] = extractor.text()[:TEXT_CHARS]
        payload["truncated"] = truncated
        payload["warning"] = "Scripts and event handlers were stripped."
        return payload
    if kind == "jupyter":
        raw, truncated = _read_capped(path, 128 * 1024)
        try:
            notebook = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            raise WorkspaceError("notebook is not valid JSON") from None
        cells = notebook.get("cells") if isinstance(notebook, dict) else None
        lines: list[str] = []
        if isinstance(cells, list):
            for cell in cells[:40]:
                if not isinstance(cell, dict):
                    continue
                source = cell.get("source", "")
                if isinstance(source, list):
                    source = "".join(str(bit) for bit in source)
                lines.append(redact(str(source)))
        payload["text"] = "\n\n".join(lines)[:TEXT_CHARS]
        payload["truncated"] = truncated
        payload["warning"] = "Notebook cells are shown as text; nothing is executed."
        return payload
    if kind == "docx":
        payload["text"] = _office_text(path, "word/document.xml")[:TEXT_CHARS]
        return payload
    if kind == "xlsx":
        payload["text"] = _office_text(path, "xl/sharedStrings.xml")[:TEXT_CHARS]
        payload["warning"] = "Spreadsheet preview is text-only."
        return payload
    if kind == "pptx":
        payload["text"] = _office_text(path, "ppt/slides/slide1.xml")[:TEXT_CHARS]
        return payload
    if kind in {"pdf", "image", "video", "file"}:
        payload["warning"] = f"{kind} preview is metadata-only; the file is never executed."
        return payload
    return payload
