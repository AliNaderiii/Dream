"""Voice Activity Detection (VAD) and Barge-In detection engine."""

from __future__ import annotations

import math
import struct

from dream.duplex.types import AudioFrame, VADState


class VoiceActivityDetector:
    """Real-time Voice Activity Detector with Barge-In capability."""

    def __init__(
        self,
        energy_threshold: float = 0.015,
        hangover_ms: int = 300,
        sample_rate: int = 16000,
        frame_size_ms: int = 20,
    ) -> None:
        self.energy_threshold = energy_threshold
        self.hangover_ms = hangover_ms
        self.sample_rate = sample_rate
        self.frame_size_ms = frame_size_ms
        self._state: VADState = VADState.SILENCE
        self._silence_duration_ms: float = 0.0
        self._speech_duration_ms: float = 0.0
        self._frame_counter: int = 0

    @property
    def current_state(self) -> VADState:
        """Return the current VAD state."""
        return self._state

    @property
    def speech_duration_ms(self) -> float:
        """Return continuous speech duration in milliseconds."""
        return self._speech_duration_ms

    @staticmethod
    def calculate_energy(data: bytes) -> float:
        """Calculate Root Mean Square (RMS) energy normalized to [0.0, 1.0]."""
        if not data:
            return 0.0

        # Unpack signed 16-bit integers
        num_samples = len(data) // 2
        if num_samples == 0:
            return 0.0

        try:
            samples = struct.unpack(f"<{num_samples}h", data[: num_samples * 2])
        except struct.error:
            return 0.0

        sum_squares = sum(s * s for s in samples)
        mean_square = sum_squares / num_samples
        rms = math.sqrt(mean_square)
        # Normalize 16-bit max value (32768)
        return min(rms / 32768.0, 1.0)

    def process_frame(self, data: bytes) -> AudioFrame:
        """Process a chunk of audio bytes and return an annotated AudioFrame."""
        self._frame_counter += 1
        energy = self.calculate_energy(data)
        is_above_threshold = energy >= self.energy_threshold

        frame = AudioFrame(
            frame_id=self._frame_counter,
            data=data,
            sample_rate=self.sample_rate,
            energy=energy,
            is_speech=is_above_threshold,
        )

        frame_duration = frame.duration_ms

        if is_above_threshold:
            self._speech_duration_ms += frame_duration
            self._silence_duration_ms = 0.0

            if self._state == VADState.SILENCE:
                self._state = VADState.SPEECH_START
            else:
                self._state = VADState.SPEECH_ONGOING
        else:
            self._silence_duration_ms += frame_duration

            if self._state in (VADState.SPEECH_START, VADState.SPEECH_ONGOING):
                if self._silence_duration_ms >= self.hangover_ms:
                    self._state = VADState.SPEECH_END
                    self._speech_duration_ms = 0.0
            elif self._state == VADState.SPEECH_END:
                self._state = VADState.SILENCE
                self._speech_duration_ms = 0.0
            else:
                self._state = VADState.SILENCE
                self._speech_duration_ms = 0.0

        return frame

    def check_barge_in(self, frame: AudioFrame, min_speech_ms: int = 100) -> bool:
        """Determine whether user audio frame qualifies as a barge-in interruption."""
        return bool(
            frame.is_speech
            and self._state in (VADState.SPEECH_START, VADState.SPEECH_ONGOING)
            and self._speech_duration_ms >= min_speech_ms
        )

    def reset(self) -> None:
        """Reset internal detector state."""
        self._state = VADState.SILENCE
        self._silence_duration_ms = 0.0
        self._speech_duration_ms = 0.0
        self._frame_counter = 0
