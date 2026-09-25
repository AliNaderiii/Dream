"""OpenAI-compatible multimodal adapter, gated by explicit network approval."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from dream.vision.backend_contract import IMAGE_MIME_ALLOWLIST, MAX_IMAGE_BYTES


class MultimodalAdapterError(ValueError):
    """A configured multimodal request could not be safely completed."""


def _endpoint(raw: str | None) -> str:
    endpoint = (
        raw or os.environ.get("DREAM_VISION_BASE_URL") or "https://api.openai.com/v1"
    ).rstrip("/")
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise MultimodalAdapterError("vision endpoint must be a valid http(s) URL")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise MultimodalAdapterError("plain HTTP is allowed only for a local vision endpoint")
    return endpoint


def analyze_image(
    image: bytes,
    mime: str,
    prompt: str,
    *,
    model: str | None = None,
    endpoint: str | None = None,
    allow_network: bool = False,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    """Send one real image request; credentials are resolved from environment only."""
    if not allow_network:
        raise MultimodalAdapterError("network approval is required before sending an image")
    if mime not in IMAGE_MIME_ALLOWLIST:
        raise MultimodalAdapterError("image MIME type is not allowed by the vision contract")
    if not isinstance(image, (bytes, bytearray)) or not image:
        raise MultimodalAdapterError("image bytes are required")
    if len(image) > MAX_IMAGE_BYTES:
        raise MultimodalAdapterError("image exceeds the vision contract byte limit")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8_000:
        raise MultimodalAdapterError("prompt must be non-empty and at most 8000 characters")

    token = os.environ.get("DREAM_VISION_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not token:
        raise MultimodalAdapterError("no vision API credential is configured in the environment")
    selected_model = (model or os.environ.get("DREAM_VISION_MODEL") or "").strip()
    if not selected_model:
        raise MultimodalAdapterError("DREAM_VISION_MODEL is required for multimodal inference")

    started = time.monotonic()
    encoded = base64.b64encode(bytes(image)).decode("ascii")
    payload = {
        "model": selected_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt.strip()},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                ],
            }
        ],
        "stream": False,
    }
    request = Request(
        f"{_endpoint(endpoint)}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Dream-vision/5.15",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise MultimodalAdapterError(f"vision provider rejected the request ({exc.code})") from None
    except (URLError, OSError, ValueError, TypeError) as exc:
        reason = type(exc).__name__
        raise MultimodalAdapterError(
            f"vision provider request failed: {reason}"
        ) from None

    try:
        content = result["choices"][0]["message"].get("content")
    except (KeyError, IndexError, TypeError) as exc:
        raise MultimodalAdapterError("vision provider returned an invalid response") from exc
    if not isinstance(content, str):
        raise MultimodalAdapterError("vision provider returned no text content")
    return {
        "success": True,
        "answer": content,
        "provenance": {
            "provider_protocol": "openai-compatible",
            "model": selected_model,
            "endpoint_host": urlparse(_endpoint(endpoint)).hostname,
            "prompt_sha256": hashlib.sha256(prompt.strip().encode()).hexdigest(),
            "image_sha256": hashlib.sha256(bytes(image)).hexdigest(),
            "bytes_sent": len(image),
            "network_sent": True,
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
        },
    }
