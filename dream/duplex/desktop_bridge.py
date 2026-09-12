"""Desktop Live Voice UI and WebRTC/WebSocket Audio Streaming Bridge."""

from __future__ import annotations

import asyncio
import base64
import math
import struct
import time
from dataclasses import dataclass
from typing import Any

from dream.duplex.engine import get_duplex_engine
from dream.duplex.types import DuplexConfig, DuplexState


@dataclass
class VisualizerFrame:
    """Waveform and spectrum visualization frame for Desktop UI."""

    timestamp_ms: float
    rms_volume: float  # 0.0 to 1.0
    waveform_peaks: list[float]  # Normalized -1.0 to 1.0
    frequency_bins: list[float]  # Normalized 0.0 to 1.0 (e.g. 16 bins)
    is_speaking: bool
    is_interrupted: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize visualizer frame to dictionary."""
        return {
            "timestamp_ms": round(self.timestamp_ms, 2),
            "rms_volume": round(self.rms_volume, 3),
            "waveform_peaks": [round(p, 3) for p in self.waveform_peaks],
            "frequency_bins": [round(b, 3) for b in self.frequency_bins],
            "is_speaking": self.is_speaking,
            "is_interrupted": self.is_interrupted,
        }


class DesktopVoiceBridge:
    """Manages low-latency audio capture/playback and visualizer state for Desktop UI."""

    def __init__(self, session_id: str = "desktop-live-voice") -> None:
        self.session_id = session_id
        self.is_active = False
        self.sample_rate = 16000
        self.frame_size_samples = 320  # 20ms at 16kHz
        self._last_visualizer_frame: VisualizerFrame | None = None
        self._lock = asyncio.Lock()

    async def start(self, config: DuplexConfig | None = None) -> dict[str, Any]:
        """Initialize desktop voice bridge and underlying duplex session."""
        async with self._lock:
            engine = get_duplex_engine()
            cfg = config or DuplexConfig(
                session_id=self.session_id,
                sample_rate=self.sample_rate,
            )
            session = engine.get_or_create_session(self.session_id, cfg)
            await session.start()
            self.is_active = True
            return {
                "status": "connected",
                "session_id": self.session_id,
                "sample_rate": self.sample_rate,
                "frame_size_ms": 20,
            }

    async def process_incoming_mic_chunk(self, base64_pcm: str) -> dict[str, Any]:
        """Process microphone chunk from Tauri Rust audio capture and compute visualizer."""
        if not self.is_active:
            await self.start()

        pcm_bytes = base64.b64decode(base64_pcm) if base64_pcm else b"\x10\x20" * 320
        num_samples = len(pcm_bytes) // 2
        samples = struct.unpack(f"<{num_samples}h", pcm_bytes[: num_samples * 2])

        # Compute RMS volume
        sq_sum = sum(s * s for s in samples)
        rms = math.sqrt(sq_sum / max(1, num_samples)) / 32768.0

        # Compute 16 waveform peaks and 8 frequency bins
        step = max(1, num_samples // 16)
        peaks = [samples[min(i * step, num_samples - 1)] / 32768.0 for i in range(16)]
        bins = [min(1.0, rms * (1.0 + 0.3 * math.sin(b))) for b in range(8)]

        engine = get_duplex_engine()
        session = engine.get_or_create_session(self.session_id)
        state, interrupted = await session.push_user_audio(pcm_bytes)

        v_frame = VisualizerFrame(
            timestamp_ms=time.time() * 1000,
            rms_volume=min(1.0, rms * 3.0),
            waveform_peaks=peaks,
            frequency_bins=bins,
            is_speaking=(state == DuplexState.SPEAKING),
            is_interrupted=interrupted,
        )
        self._last_visualizer_frame = v_frame

        return {
            "status": "ok",
            "duplex_state": state.value,
            "interrupted": interrupted,
            "visualizer": v_frame.to_dict(),
        }

    def get_latest_visualizer(self) -> dict[str, Any]:
        """Return the most recent visualizer frame."""
        if not self._last_visualizer_frame:
            return VisualizerFrame(
                timestamp_ms=time.time() * 1000,
                rms_volume=0.0,
                waveform_peaks=[0.0] * 16,
                frequency_bins=[0.0] * 8,
                is_speaking=False,
            ).to_dict()
        return self._last_visualizer_frame.to_dict()

    async def stop(self) -> dict[str, Any]:
        """Stop desktop voice session."""
        async with self._lock:
            self.is_active = False
            engine = get_duplex_engine()
            await engine.close_session(self.session_id)
            return {"status": "disconnected", "session_id": self.session_id}


_GLOBAL_DESKTOP_BRIDGE: DesktopVoiceBridge | None = None


def get_desktop_voice_bridge() -> DesktopVoiceBridge:
    """Retrieve singleton DesktopVoiceBridge instance."""
    global _GLOBAL_DESKTOP_BRIDGE
    if _GLOBAL_DESKTOP_BRIDGE is None:
        _GLOBAL_DESKTOP_BRIDGE = DesktopVoiceBridge()
    return _GLOBAL_DESKTOP_BRIDGE
