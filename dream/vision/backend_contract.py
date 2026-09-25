"""Explicit multimodal backend contract and fail-closed selection gate."""

from __future__ import annotations

import os
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
    provider_name = (provider or "openai-compatible").strip() or "openai-compatible"
    model_name = (model or os.environ.get("DREAM_VISION_MODEL") or "").strip() or None
    env_ready = bool(
        os.environ.get("DREAM_VISION_API_KEY") or os.environ.get("OPENAI_API_KEY")
    ) and bool(model_name)
    adapter_ready = provider_name == "openai-compatible" and env_ready
    return {
        "provider": provider_name,
        "model": model_name,
        "protocol": "openai-compatible" if provider_name == "openai-compatible" else None,
        "configured": bool(configured or env_ready),
        "selection_allowed": adapter_ready,
        "transport_implemented": provider_name == "openai-compatible",
        "adapter_ready": adapter_ready,
        "image_input": {
            "accepted_mime": list(IMAGE_MIME_ALLOWLIST),
            "max_bytes": MAX_IMAGE_BYTES,
            "max_pixels": MAX_IMAGE_PIXELS,
            "requires_network_approval": True,
        },
        "video_input": {"available": False, "reason": "no frame transport adapter"},
        "inference": {
            "available": adapter_ready,
            "reason": (
                "adapter configured and ready for explicit network approval"
                if adapter_ready
                else "adapter is not configured with a credential and model"
            ),
        },
        "privacy": {
            "network_probe_performed": False,
            "image_sent": False,
            "persistent_copy_created": False,
        },
        "blocked_reason": (
            "backend آماده است؛ ارسال همچنان نیازمند allow_network=true است."
            if adapter_ready
            else "credential و model واقعی برای adapter پیکربندی نشده‌اند."
        ),
    }
