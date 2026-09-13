"""Tests for Desktop Real-Time Duplex Voice Bridge and JSON-RPC Methods."""

from __future__ import annotations

import asyncio
import base64
import struct

import pytest

from dream.bridge.errors import BridgeError
from dream.bridge.extensions import Registry
from dream.bridge.methods_duplex import (
    duplex_export_transcript,
    duplex_get_metrics,
    duplex_get_visualizer,
    duplex_inject_interruption,
    duplex_push_mic_chunk,
    duplex_start,
    duplex_stop,
)


def test_duplex_bridge_extension_discovery():
    """Verify duplex.* methods are automatically registered in the Bridge Registry."""
    handlers = Registry.publish({})
    assert "duplex.start" in handlers
    assert "duplex.push_mic_chunk" in handlers
    assert "duplex.get_visualizer" in handlers
    assert "duplex.inject_interruption" in handlers
    assert "duplex.get_metrics" in handlers
    assert "duplex.export_transcript" in handlers
    assert "duplex.stop" in handlers


def test_duplex_start_valid_and_invalid_params():
    """Test starting a duplex session with valid and invalid sample rates."""
    async def _test():
        res = await duplex_start({"session_id": "test-voice-sess", "sample_rate": 16000})
        assert res["status"] == "connected"
        assert res["session_id"] == "test-voice-sess"
        assert res["sample_rate"] == 16000

        with pytest.raises(BridgeError):
            await duplex_start({"sample_rate": 12345})

        await duplex_stop()

    asyncio.run(_test())


def test_duplex_push_mic_chunk_and_visualizer_pipeline():
    """Test pushing audio chunks, computing visualizer metrics, and polling."""
    async def _test():
        await duplex_start({"session_id": "test-mic-stream", "sample_rate": 16000})

        pcm_samples = [1000] * 320
        pcm_bytes = struct.pack("<320h", *pcm_samples)
        b64_chunk = base64.b64encode(pcm_bytes).decode("utf-8")

        push_res = await duplex_push_mic_chunk({"chunk_b64": b64_chunk})
        assert push_res["status"] == "ok"
        assert "visualizer" in push_res

        v_frame = push_res["visualizer"]
        assert len(v_frame["waveform_peaks"]) == 16
        assert len(v_frame["frequency_bins"]) == 8
        assert v_frame["rms_volume"] > 0.0

        polled = duplex_get_visualizer()
        assert len(polled["waveform_peaks"]) == 16
        assert len(polled["frequency_bins"]) == 8

        await duplex_stop()

    asyncio.run(_test())


def test_duplex_inject_interruption_and_metrics():
    """Test barge-in interruption injection and metrics retrieval."""
    async def _test():
        await duplex_start({"session_id": "test-interruption"})

        intr_res = await duplex_inject_interruption({"session_id": "test-interruption"})
        assert intr_res["session_id"] == "test-interruption"
        assert "interrupted" in intr_res

        metrics_res = duplex_get_metrics({"session_id": "test-interruption"})
        assert metrics_res["status"] == "ok"
        assert "stats" in metrics_res

        await duplex_stop()

    asyncio.run(_test())


def test_duplex_export_transcript_lifecycle():
    """Test exporting the conversation transcript in markdown format."""
    async def _test():
        await duplex_start({"session_id": "test-transcript-session"})

        trans_res = duplex_export_transcript({
            "session_id": "test-transcript-session",
            "format": "markdown",
        })
        assert trans_res["session_id"] == "test-transcript-session"
        assert trans_res["format"] == "markdown"
        assert isinstance(trans_res["transcript"], str)

        await duplex_stop()

    asyncio.run(_test())
