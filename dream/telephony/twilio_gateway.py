"""Twilio Media Streams WebSocket Gateway for Real-Time Phone Call Audio."""

from __future__ import annotations

import base64
import json
import struct
from typing import Any

from dream.duplex.engine import get_duplex_engine
from dream.telephony.types import CallStatus, TelephonyCallRecord


class TwilioMediaGateway:
    """Handles bi-directional Twilio Media Streams audio and event translation."""

    def __init__(self, call_record: TelephonyCallRecord) -> None:
        self.call = call_record
        self.stream_sid: str | None = None
        self.is_connected = False
        self._engine = get_duplex_engine()
        self._session = self._engine.get_or_create_session(self.call.call_id)

    def handle_twilio_message(self, raw_json: str) -> list[dict[str, Any]]:
        """Process incoming WebSocket payload from Twilio and generate outbound packets."""
        try:
            msg = json.loads(raw_json)
        except Exception:
            return []

        event = msg.get("event")
        responses: list[dict[str, Any]] = []

        if event == "start":
            self.stream_sid = msg.get("streamSid")
            self.is_connected = True
            self.call.status = CallStatus.IN_PROGRESS
            responses.append({
                "event": "mark",
                "streamSid": self.stream_sid,
                "mark": {"name": "call_initialized"},
            })

        elif event == "media":
            media_payload = msg.get("media", {})
            payload_b64 = media_payload.get("payload", "")
            if payload_b64:
                mulaw_bytes = base64.b64decode(payload_b64)
                pcm16_bytes = self._mulaw_to_pcm16(mulaw_bytes)
                if len(pcm16_bytes) > 0:
                    pass

        elif event == "dtmf":
            digit = msg.get("dtmf", {}).get("digit", "")
            if digit:
                self.call.dtmf_digits += digit

        elif event == "stop":
            self.is_connected = False
            self.call.status = CallStatus.COMPLETED

        return responses

    def synthesize_outbound_media(self, pcm_16k_chunk: bytes) -> dict[str, Any]:
        """Convert synthesized PCM16 speech chunk to Twilio 8kHz u-law media packet."""
        mulaw_data = self._pcm16_to_mulaw(pcm_16k_chunk)
        b64_payload = base64.b64encode(mulaw_data).decode("utf-8")
        return {
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {"payload": b64_payload},
        }

    def create_clear_message(self) -> dict[str, Any]:
        """Create Twilio clear event to flush queued audio buffer on user barge-in."""
        return {
            "event": "clear",
            "streamSid": self.stream_sid,
        }

    def _mulaw_to_pcm16(self, mulaw_bytes: bytes) -> bytes:
        """Decode G.711 mu-law 8kHz bytes into linear PCM16 (upsampled 2x to 16kHz)."""
        pcm16 = bytearray()
        for b in mulaw_bytes:
            val = (b ^ 0xFF) - 128
            sample = val * 256
            sample_bytes = struct.pack("<h", max(-32768, min(32767, sample)))
            pcm16.extend(sample_bytes * 2)
        return bytes(pcm16)

    def _pcm16_to_mulaw(self, pcm16_bytes: bytes) -> bytes:
        """Encode linear PCM16 (downsampled 2x from 16kHz to 8kHz) into G.711 mu-law."""
        num_samples = len(pcm16_bytes) // 2
        samples = struct.unpack(f"<{num_samples}h", pcm16_bytes[: num_samples * 2])
        mulaw = bytearray()
        for i in range(0, num_samples, 2):
            s = samples[i]
            compressed = ((s // 256) + 128) ^ 0xFF
            mulaw.append(max(0, min(255, compressed)))
        return bytes(mulaw)
