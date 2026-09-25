"""Explicit multimodal backend contract and fail-closed selection gate."""

from __future__ import annotations

from typing import Any

IMAGE_MIME_ALLOWLIST = ("image/png", "image/jpeg", "image/gif", "image/bmp", "image/webp")
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 100_000_000


def backend_contract(
    provider: str | None = None,
    model: str | None = None,
    *,
    configured: bool = False,
) -> dict[str, Any]:
    """Return the contract without probing or claiming an inference adapter."""
    provider_name = (provider or "").strip() or None
    model_name = (model or "").strip() or None
    return {
        "provider": provider_name,
        "model": model_name,
        "protocol": None,
        "configured": bool(configured),
        "selection_allowed": False,
        "transport_implemented": False,
        "image_input": {
            "accepted_mime": list(IMAGE_MIME_ALLOWLIST),
            "max_bytes": MAX_IMAGE_BYTES,
            "max_pixels": MAX_IMAGE_PIXELS,
            "requires_network_approval": True,
        },
        "video_input": {"available": False, "reason": "no frame transport adapter"},
        "inference": {
            "available": False,
            "reason": "no multimodal transport adapter is implemented",
        },
        "privacy": {
            "network_probe_performed": False,
            "image_sent": False,
            "persistent_copy_created": False,
        },
        "blocked_reason": "انتخاب backend تا زمان اتصال adapter واقعی مجاز نیست.",
    }
