"""Dependency-free screen capture for the vision subsystem.

Captures the real screen without any third-party package:

- Windows: native GDI (``user32``/``gdi32``) via :mod:`ctypes` — primary
  display, 32-bpp BMP output, layered windows included via ``CAPTUREBLT``.
- macOS: the system ``screencapture`` utility (PNG output).
- Any other platform: an honest :class:`ScreenCaptureError` — never a silent
  fallback.

Privacy contract (P-14 spirit): the capture writes real screen pixels to a
temporary file. The caller must delete that file immediately after use —
screen pixels must never persist on disk, and capture paths are never logged.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


class ScreenCaptureError(RuntimeError):
    """Raised when a real screen capture is unavailable or fails."""


def capture_extension() -> str:
    """File extension the platform capture produces (``.bmp`` or ``.png``)."""
    if sys.platform == "win32":
        return ".bmp"
    return ".png"


def _capture_windows_bmp(target: Path) -> dict[str, Any]:
    """Capture the primary display through GDI and write a bottom-up 32-bpp BMP."""
    import ctypes
    import struct
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int

    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.BitBlt.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
    ]
    gdi32.BitBlt.restype = wintypes.BOOL
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC,  # hdc
        wintypes.HBITMAP,  # hbmp
        wintypes.UINT,  # uStartScan
        wintypes.UINT,  # cScanLines
        ctypes.c_void_p,  # lpvBits
        ctypes.c_void_p,  # lpbi
        wintypes.UINT,  # uUsage
    ]
    gdi32.GetDIBits.restype = ctypes.c_int

    srccopy = 0x00CC0020
    captureblt = 0x40000000
    dib_rgb_colors = 0
    bi_rgb = 0

    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)
    if width <= 0 or height <= 0:
        raise ScreenCaptureError("no display is attached to this session")

    screen_dc = user32.GetDC(None)
    if not screen_dc:
        raise ScreenCaptureError("GetDC failed on the primary display")
    try:
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        if not mem_dc:
            raise ScreenCaptureError("CreateCompatibleDC failed")
        try:
            bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
            if not bitmap:
                raise ScreenCaptureError("CreateCompatibleBitmap failed")
            previous = gdi32.SelectObject(mem_dc, bitmap)
            try:
                if not gdi32.BitBlt(
                    mem_dc, 0, 0, width, height, screen_dc, 0, 0, srccopy | captureblt
                ):
                    raise ScreenCaptureError("BitBlt failed on the primary display")

                # BITMAPINFOHEADER: bottom-up, uncompressed, 32 bits per pixel.
                header = struct.pack(
                    "<IiiHHIIiiII",
                    40,  # biSize
                    width,  # biWidth
                    height,  # biHeight (positive => bottom-up rows)
                    1,  # biPlanes
                    32,  # biBitCount
                    bi_rgb,  # biCompression
                    0,  # biSizeImage (may be 0 for BI_RGB)
                    2835,  # biXPelsPerMeter (~72 DPI)
                    2835,  # biYPelsPerMeter
                    0,  # biClrUsed
                    0,  # biClrImportant
                )
                info = ctypes.create_string_buffer(header, len(header))
                pixels = ctypes.create_string_buffer(width * height * 4)
                copied = gdi32.GetDIBits(
                    mem_dc,
                    bitmap,
                    0,
                    height,
                    ctypes.addressof(pixels),
                    ctypes.addressof(info),
                    dib_rgb_colors,
                )
                if copied != height:
                    raise ScreenCaptureError("GetDIBits failed to read the capture")
            finally:
                gdi32.SelectObject(mem_dc, previous)
                gdi32.DeleteObject(bitmap)
        finally:
            gdi32.DeleteDC(mem_dc)
    finally:
        user32.ReleaseDC(None, screen_dc)

    pixel_bytes = pixels.raw  # 32-bpp rows are always 4-byte aligned
    data_size = 14 + 40 + len(pixel_bytes)
    file_header = struct.pack("<2sIHHI", b"BM", data_size, 0, 0, 54)
    with target.open("wb") as handle:
        handle.write(file_header)
        handle.write(header)
        handle.write(pixel_bytes)

    return {
        "backend": "windows-gdi",
        "width": width,
        "height": height,
        "size_bytes": data_size,
    }


def _capture_macos_png(target: Path) -> dict[str, Any]:
    """Capture the main display with the system ``screencapture`` utility."""
    import subprocess

    try:
        completed = subprocess.run(
            ["screencapture", "-x", str(target)],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ScreenCaptureError(f"macOS screencapture failed: {exc}") from exc
    if completed.returncode != 0 or not target.exists() or target.stat().st_size == 0:
        raise ScreenCaptureError(
            "macOS screencapture failed (is screen recording permission granted?)"
        )

    width = height = 0
    with target.open("rb") as handle:
        head = handle.read(24)
    if len(head) >= 24 and head[:8] == b"\x89PNG\r\n\x1a\n":
        width = int.from_bytes(head[16:20], "big")
        height = int.from_bytes(head[20:24], "big")
    return {
        "backend": "macos-screencapture",
        "width": width,
        "height": height,
        "size_bytes": target.stat().st_size,
    }


def capture_screen_to_file(target: str | Path) -> dict[str, Any]:
    """Capture the real screen to *target* and describe the capture.

    Returns ``{"backend", "width", "height", "size_bytes"}``. Raises
    :class:`ScreenCaptureError` when no real capture backend exists.
    """
    path = Path(target)
    if sys.platform == "win32":
        return _capture_windows_bmp(path)
    if sys.platform == "darwin":
        return _capture_macos_png(path)
    raise ScreenCaptureError(
        "screen capture is not supported on this platform "
        f"(detected {sys.platform!r}); supported: windows (GDI), macOS (screencapture)"
    )
