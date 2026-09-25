"""Mock-transport tests for the real OpenAI-compatible vision adapter."""

from __future__ import annotations

import json

import pytest

from dream.vision.openai_multimodal import MultimodalAdapterError, analyze_image


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({"choices": [{"message": {"content": "A blue button."}}]}).encode()


def test_requires_explicit_network_approval(monkeypatch):
    monkeypatch.setenv("DREAM_VISION_API_KEY", "test-secret")
    monkeypatch.setenv("DREAM_VISION_MODEL", "vision-test")
    with pytest.raises(MultimodalAdapterError, match="network approval"):
        analyze_image(b"image", "image/png", "What is shown?", opener=lambda *args, **kwargs: None)


def test_sends_real_data_uri_and_returns_safe_provenance(monkeypatch):
    monkeypatch.setenv("DREAM_VISION_API_KEY", "test-secret")
    monkeypatch.setenv("DREAM_VISION_MODEL", "vision-test")
    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return FakeResponse()

    result = analyze_image(
        b"image",
        "image/png",
        "What is shown?",
        endpoint="https://vision.example/v1",
        allow_network=True,
        opener=opener,
    )
    assert captured["url"] == "https://vision.example/v1/chat/completions"
    assert captured["body"]["model"] == "vision-test"
    image_url = captured["body"]["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url == "data:image/png;base64,aW1hZ2U="
    assert captured["headers"]["Authorization"] == "Bearer test-secret"
    assert result["answer"] == "A blue button."
    assert result["provenance"]["network_sent"] is True
    assert result["provenance"]["endpoint_host"] == "vision.example"
    assert "secret" not in json.dumps(result)
    assert "data:image" not in json.dumps(result)


def test_remote_plain_http_is_rejected(monkeypatch):
    monkeypatch.setenv("DREAM_VISION_API_KEY", "test-secret")
    monkeypatch.setenv("DREAM_VISION_MODEL", "vision-test")
    with pytest.raises(MultimodalAdapterError, match="local"):
        analyze_image(
            b"image",
            "image/png",
            "What is shown?",
            endpoint="http://vision.example/v1",
            allow_network=True,
            opener=lambda *args, **kwargs: None,
        )
