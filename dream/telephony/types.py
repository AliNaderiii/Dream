"""Domain Types, Enums and Schemas for Telephony and VoIP Gateway."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CallDirection(str, Enum):
    """Direction of phone call."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallStatus(str, Enum):
    """Lifecycle state of telephone call."""
    QUEUED = "queued"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BUSY = "busy"
    FAILED = "failed"
    NO_ANSWER = "no_answer"
    CANCELED = "canceled"


class AudioCodec(str, Enum):
    """Telephony audio stream encoding codecs."""
    PCMU_8KHZ = "audio/x-mulaw;rate=8000"  # G.711 u-law (Twilio default)
    PCMA_8KHZ = "audio/x-alaw;rate=8000"   # G.711 a-law
    PCM_16KHZ = "audio/l16;rate=16000"     # Linear PCM 16kHz


@dataclass
class TelephonyCallRecord:
    """Metadata record representing a telephone call session."""

    call_id: str
    from_number: str
    to_number: str
    direction: CallDirection = CallDirection.OUTBOUND
    status: CallStatus = CallStatus.QUEUED
    codec: AudioCodec = AudioCodec.PCMU_8KHZ
    provider: str = "twilio_media_streams"
    created_at: float = field(default_factory=time.time)
    connected_at: float | None = None
    ended_at: float | None = None
    duration_sec: float = 0.0
    cost_estimated_usd: float = 0.0
    dtmf_digits: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize call record to dictionary."""
        return {
            "call_id": self.call_id,
            "from_number": self.from_number,
            "to_number": self.to_number,
            "direction": self.direction.value,
            "status": self.status.value,
            "codec": self.codec.value,
            "provider": self.provider,
            "duration_sec": round(self.duration_sec, 2),
            "cost_estimated_usd": round(self.cost_estimated_usd, 4),
            "dtmf_digits": self.dtmf_digits,
            "metadata": self.metadata,
        }
