"""Bounded, dependency-free image intake metadata inspection.

This module intentionally does not decode pixels or perform inference. It only
validates a file's magic bytes and extracts dimensions from common image
headers. That makes the v5.13a readiness layer useful and honest while a real
multimodal backend is still absent.
"""

from __future__ import annotations

import struct
from typing import Any

MAX_IMAGE_BYTES = 20 * 1024 * 1024
_MAX_PIXELS = 100_000_000


class ImageIntakeError(ValueError):
    """The selected file is not a supported, bounded image."""


def _dimensions(data: bytes, fmt: str) -> tuple[int, int]:
    if fmt == "png":
        if len(data) < 24:
            raise ImageIntakeError("PNG header is truncated")
        return struct.unpack(">II", data[16:24])
    if fmt == "gif":
        if len(data) < 10:
            raise ImageIntakeError("GIF header is truncated")
        return struct.unpack("<HH", data[6:10])
    if fmt == "bmp":
        if len(data) < 26:
            raise ImageIntakeError("BMP header is truncated")
        return struct.unpack("<ii", data[18:26])
    if fmt == "webp":
        if len(data) < 30 or data[12:16] != b"VP8X":
            raise ImageIntakeError("only extended WEBP headers are supported")
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if fmt == "jpeg":
        pos = 2
        while pos + 3 < len(data):
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            pos += 2
            if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                continue
            if pos + 2 > len(data):
                break
            length = int.from_bytes(data[pos : pos + 2], "big")
            if length < 2 or pos + length > len(data):
                break
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }:
                if length < 7:
                    break
                height = int.from_bytes(data[pos + 3 : pos + 5], "big")
                width = int.from_bytes(data[pos + 5 : pos + 7], "big")
                return width, height
            pos += length
        raise ImageIntakeError("JPEG dimensions were not found")
    raise ImageIntakeError("unsupported image format")


def inspect_image_bytes(data: bytes, name: str = "image") -> dict[str, Any]:
    """Validate magic bytes and return metadata; never claims image understanding."""
    if not isinstance(data, (bytes, bytearray)):
        raise ImageIntakeError("image payload must be bytes")
    raw = bytes(data)
    if not raw:
        raise ImageIntakeError("image is empty")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ImageIntakeError(f"image exceeds the {MAX_IMAGE_BYTES} byte limit")

    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        fmt, mime = "png", "image/png"
    elif raw.startswith(b"\xff\xd8\xff"):
        fmt, mime = "jpeg", "image/jpeg"
    elif raw[:6] in {b"GIF87a", b"GIF89a"}:
        fmt, mime = "gif", "image/gif"
    elif raw.startswith(b"BM"):
        fmt, mime = "bmp", "image/bmp"
    elif raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        fmt, mime = "webp", "image/webp"
    else:
        raise ImageIntakeError("file signature is not a supported raster image")

    width, height = _dimensions(raw, fmt)
    if width < 1 or height < 1 or width * height > _MAX_PIXELS:
        raise ImageIntakeError("image dimensions exceed the safe pixel limit")
    return {
        "valid": True,
        "name": str(name)[:255],
        "format": fmt,
        "mime": mime,
        "bytes": len(raw),
        "width": width,
        "height": height,
        "pixels": width * height,
        "metadata_only": True,
        "pixels_decoded": False,
        "inference_available": False,
        "privacy": {
            "network_sent": False,
            "persisted_copy_created": False,
            "absolute_path_returned": False,
        },
    }
