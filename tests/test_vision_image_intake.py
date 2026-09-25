"""Truthful v5.13a image-intake tests: metadata only, bounded, no inference."""

from __future__ import annotations

import struct

import pytest

from dream.vision.image_intake import ImageIntakeError, inspect_image_bytes


def png(width: int = 16, height: int = 9) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", width, height) + b"\x00" * 4


def test_png_metadata_is_real_and_never_claims_inference() -> None:
    result = inspect_image_bytes(png(), "screen.png")
    assert result["format"] == "png"
    assert result["width"] == 16
    assert result["height"] == 9
    assert result["metadata_only"] is True
    assert result["pixels_decoded"] is False
    assert result["inference_available"] is False
    assert result["privacy"]["network_sent"] is False


def test_gif_dimensions_are_read_from_header() -> None:
    result = inspect_image_bytes(b"GIF89a" + struct.pack("<HH", 7, 5) + b"\x00" * 16)
    assert (result["width"], result["height"]) == (7, 5)


def test_unknown_signature_is_rejected() -> None:
    with pytest.raises(ImageIntakeError, match="signature"):
        inspect_image_bytes(b"not an image")


def test_empty_image_is_rejected() -> None:
    with pytest.raises(ImageIntakeError, match="empty"):
        inspect_image_bytes(b"")


def test_pixel_limit_is_enforced() -> None:
    with pytest.raises(ImageIntakeError, match="dimensions"):
        inspect_image_bytes(png(10_001, 10_001))
