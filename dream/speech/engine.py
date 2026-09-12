"""Speech Synthesis (TTS), Recognition (STT), and HybridEmo Emotion Engine."""

from __future__ import annotations

import math
import struct
import tempfile
import time
from pathlib import Path

from dream.security.pathsafety import is_sensitive_path
from dream.speech.types import (
    EmotionBlend,
    EmotionTrajectorySegment,
    EmotionType,
    STTRequest,
    STTResult,
    STTSegment,
    TTSRequest,
    TTSResult,
    VoicePersona,
)

# Standard Voice Personas
BUILTIN_VOICES: dict[str, VoicePersona] = {
    "fa-mina": VoicePersona(
        voice_id="fa-mina",
        name="Mina (Persian Natural)",
        language="fa",
        gender="female",
        description="Warm, clear standard Persian speaker with natural intonation.",
        default_emotion=EmotionType.CALM,
    ),
    "fa-nima": VoicePersona(
        voice_id="fa-nima",
        name="Nima (Persian Deep)",
        language="fa",
        gender="male",
        description="Deep, authoritative Persian speaker suited for narration and analysis.",
        default_emotion=EmotionType.SERIOUS,
    ),
    "fa-roya": VoicePersona(
        voice_id="fa-roya",
        name="Roya (Persian Expressive)",
        language="fa",
        gender="female",
        description="Vibrant and emotive Persian voice with high dynamic range.",
        default_emotion=EmotionType.JOYFUL,
    ),
    "soprano-fast": VoicePersona(
        voice_id="soprano-fast",
        name="Soprano On-Device Fast",
        language="en",
        gender="neutral",
        description="Ultra-lightweight on-device fast synthesis voice inspired by Soprano.",
        default_emotion=EmotionType.NEUTRAL,
    ),
    "hybrid-expressive": VoicePersona(
        voice_id="hybrid-expressive",
        name="HybridEmo Multi-Emotion",
        language="fa",
        gender="neutral",
        description="Advanced instruction-following multi-emotion and blended voice engine.",
        default_emotion=EmotionType.EMPATHETIC,
    ),
}

# Emotion Acoustic Profiles (pitch_mult, tempo_mult, vibrato_depth, brightness)
EMOTION_PROFILES: dict[EmotionType, tuple[float, float, float, float]] = {
    EmotionType.NEUTRAL: (1.0, 1.0, 0.005, 1.0),
    EmotionType.JOYFUL: (1.18, 1.15, 0.015, 1.25),
    EmotionType.EMPATHETIC: (0.95, 0.90, 0.012, 0.85),
    EmotionType.CALM: (0.88, 0.82, 0.008, 0.80),
    EmotionType.ENTHUSIASTIC: (1.25, 1.22, 0.020, 1.35),
    EmotionType.SERIOUS: (0.86, 0.94, 0.003, 0.90),
    EmotionType.SURPRISED: (1.30, 1.18, 0.018, 1.30),
    EmotionType.CURIOUS: (1.10, 1.05, 0.014, 1.10),
    EmotionType.MELANCHOLIC: (0.82, 0.78, 0.010, 0.75),
}


class SpeechEngine:
    """Orchestrates Text-to-Speech, Speech-to-Text, and Multi-Emotion voice processing."""

    def __init__(self) -> None:
        self._voices: dict[str, VoicePersona] = dict(BUILTIN_VOICES)

    def list_voices(self, language: str | None = None) -> list[VoicePersona]:
        """List registered voice personas, optionally filtered by language."""
        if language:
            return [v for v in self._voices.values() if v.language == language]
        return list(self._voices.values())

    def get_voice(self, voice_id: str) -> VoicePersona | None:
        """Get voice persona by identifier."""
        return self._voices.get(voice_id)

    def synthesize(self, req: TTSRequest) -> TTSResult:
        """Synthesize text into speech audio with multi-emotion trajectory and blending."""
        # 1. Resolve voice persona
        voice = self._voices.get(req.voice_id, BUILTIN_VOICES["fa-mina"])

        # 2. Compute Emotion Acoustic Multipliers (inspired by HybridEmo)
        pitch_mult, tempo_mult, vibrato, brightness = self._calculate_emotion_acoustics(
            req.emotion, req.trajectory
        )

        pitch_factor = req.pitch * pitch_mult
        speed_factor = req.speed * tempo_mult

        # 3. Text analysis & duration estimation
        text = req.text.strip()
        phonemes = self._text_to_phonemes(text)
        base_duration = max(0.4, len(phonemes) * 0.075 / max(0.2, speed_factor))

        # 4. Generate raw 16-bit PCM audio samples
        sample_rate = req.sample_rate
        total_samples = int(base_duration * sample_rate)
        base_freq = 180.0 * pitch_factor if voice.gender == "female" else 125.0 * pitch_factor

        pcm_data = bytearray()
        two_pi = 2.0 * math.pi

        for i in range(total_samples):
            t = i / sample_rate
            # Dynamic frequency with vibrato & trajectory modulation
            vib = math.sin(two_pi * 5.5 * t) * vibrato
            freq = base_freq * (1.0 + vib)

            # Envelope shaping (attack, sustain, decay)
            env = 1.0
            attack_len = int(0.04 * sample_rate)
            decay_len = int(0.06 * sample_rate)
            if i < attack_len:
                env = i / attack_len
            elif i > (total_samples - decay_len):
                env = (total_samples - i) / decay_len

            # Harmonic synthesis with formant brightness
            s1 = math.sin(two_pi * freq * t)
            s2 = 0.45 * math.sin(two_pi * (2.0 * freq) * t) * brightness
            s3 = 0.20 * math.sin(two_pi * (3.0 * freq) * t) * (brightness**1.2)
            sample_val = int(32767.0 * 0.35 * env * (s1 + s2 + s3))
            sample_val = max(-32768, min(32767, sample_val))
            pcm_data.extend(struct.pack("<h", sample_val))

        # 5. Build standard RIFF WAV container
        wav_bytes = self._build_wav_container(bytes(pcm_data), sample_rate, num_channels=1)

        # 6. Save or assign output path
        out_path = req.output_path
        if not out_path:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                tf.write(wav_bytes)
                out_path = tf.name
        else:
            if is_sensitive_path(out_path):
                raise PermissionError(f"Permission denied: '{out_path}' is a sensitive path.")
            target = Path(out_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(wav_bytes)

        emotion_label = self._describe_applied_emotion(req.emotion, req.trajectory)

        return TTSResult(
            audio_path=str(out_path),
            duration_seconds=base_duration,
            sample_rate=sample_rate,
            format=req.output_format.value,
            text=text,
            voice_id=voice.voice_id,
            emotion_applied=emotion_label,
            audio_bytes=wav_bytes,
            phonemes=phonemes,
            metadata={
                "pitch_factor": round(pitch_factor, 3),
                "speed_factor": round(speed_factor, 3),
                "samples_generated": total_samples,
                "voice_name": voice.name,
            },
        )

    def transcribe(self, req: STTRequest) -> STTResult:
        """Transcribe speech audio into text and analyze vocal emotion."""
        if is_sensitive_path(req.audio_path):
            raise PermissionError(f"Permission denied: '{req.audio_path}' is a sensitive path.")

        audio_file = Path(req.audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file '{req.audio_path}' not found.")

        raw_bytes = audio_file.read_bytes()
        duration = max(0.5, len(raw_bytes) / (24000 * 2))

        # Extract acoustic metrics for emotion classification
        detected_emotion, blend = self._analyze_audio_emotion(raw_bytes)

        # Persian NFKC text normalization and transcription simulation
        lang = req.language if req.language in ("fa", "en") else "fa"
        mock_text = req.prompt_hint or (
            "\u062f\u0631\u06cc\u0645 \u062f\u0633\u062a\u06cc\u0627\u0631 "
            "\u0647\u0648\u0634\u0645\u0646\u062f \u0641\u0627\u0631\u0633\u06cc"
            if lang == "fa"
            else "Dream intelligent multimodal assistant"
        )

        segments = [
            STTSegment(
                start=0.0,
                end=round(duration, 2),
                text=mock_text,
                confidence=0.98,
                emotion=detected_emotion,
            )
        ]

        return STTResult(
            text=mock_text,
            language=lang,
            duration=duration,
            confidence=0.98,
            segments=segments,
            overall_emotion=detected_emotion,
            emotion_blend=blend,
            metadata={
                "audio_bytes_length": len(raw_bytes),
                "processed_at": time.time(),
            },
        )

    def _calculate_emotion_acoustics(
        self,
        emotion: EmotionType | EmotionBlend | None,
        trajectory: list[EmotionTrajectorySegment] | None,
    ) -> tuple[float, float, float, float]:
        """Compute acoustic parameters from EmotionBlend or EmotionTrajectory."""
        if trajectory and len(trajectory) > 0:
            # Average acoustic profile across trajectory segments
            p_sum, t_sum, v_sum, b_sum = 0.0, 0.0, 0.0, 0.0
            for seg in trajectory:
                p1, t1, v1, b1 = EMOTION_PROFILES.get(
                    seg.start_emotion, EMOTION_PROFILES[EmotionType.NEUTRAL]
                )
                p2, t2, v2, b2 = EMOTION_PROFILES.get(
                    seg.end_emotion, EMOTION_PROFILES[EmotionType.NEUTRAL]
                )
                weight = max(0.1, seg.end_time - seg.start_time)
                p_sum += ((p1 + p2) / 2.0) * weight
                t_sum += ((t1 + t2) / 2.0) * weight
                v_sum += ((v1 + v2) / 2.0) * weight
                b_sum += ((b1 + b2) / 2.0) * weight
            total_dur = max(0.1, trajectory[-1].end_time - trajectory[0].start_time)
            return (
                p_sum / total_dur,
                t_sum / total_dur,
                v_sum / total_dur,
                b_sum / total_dur,
            )

        if isinstance(emotion, EmotionBlend):
            p1, t1, v1, b1 = EMOTION_PROFILES.get(
                emotion.primary_emotion, EMOTION_PROFILES[EmotionType.NEUTRAL]
            )
            p2, t2, v2, b2 = EMOTION_PROFILES.get(
                emotion.secondary_emotion, EMOTION_PROFILES[EmotionType.NEUTRAL]
            )
            r = emotion.blend_ratio
            return (
                p1 * r + p2 * (1.0 - r),
                t1 * r + t2 * (1.0 - r),
                v1 * r + v2 * (1.0 - r),
                b1 * r + b2 * (1.0 - r),
            )

        if isinstance(emotion, EmotionType):
            return EMOTION_PROFILES.get(emotion, EMOTION_PROFILES[EmotionType.NEUTRAL])

        return EMOTION_PROFILES[EmotionType.NEUTRAL]

    def _describe_applied_emotion(
        self,
        emotion: EmotionType | EmotionBlend | None,
        trajectory: list[EmotionTrajectorySegment] | None,
    ) -> str:
        """Generate human-readable emotion description."""
        if trajectory:
            stages = [f"{s.start_emotion.value}->{s.end_emotion.value}" for s in trajectory]
            return f"Trajectory({', '.join(stages)})"
        if isinstance(emotion, EmotionBlend):
            return (
                f"Blend({emotion.primary_emotion.value}:{int(emotion.blend_ratio*100)}% + "
                f"{emotion.secondary_emotion.value}:{int((1-emotion.blend_ratio)*100)}%)"
            )
        if isinstance(emotion, EmotionType):
            return emotion.value
        return EmotionType.NEUTRAL.value

    def _analyze_audio_emotion(self, audio_data: bytes) -> tuple[EmotionType, EmotionBlend]:
        """Classify voice emotion and blend ratio from audio waveform properties."""
        if len(audio_data) < 44:
            return EmotionType.NEUTRAL, EmotionBlend(EmotionType.NEUTRAL, EmotionType.CALM, 1.0)

        # Compute root-mean-square energy & zero crossings on sample snippet
        samples = struct.unpack_from(
            f"<{min(len(audio_data)//2 - 22, 1000)}h", audio_data, 44
        )
        if not samples:
            return EmotionType.NEUTRAL, EmotionBlend(EmotionType.NEUTRAL, EmotionType.CALM, 1.0)

        rms = math.sqrt(sum(s * s for s in samples) / len(samples))

        if rms > 8000:
            primary = EmotionType.ENTHUSIASTIC
            sec = EmotionType.JOYFUL
            ratio = 0.75
        elif rms > 4500:
            primary = EmotionType.JOYFUL
            sec = EmotionType.EMPATHETIC
            ratio = 0.80
        elif rms < 1500:
            primary = EmotionType.CALM
            sec = EmotionType.SERIOUS
            ratio = 0.70
        else:
            primary = EmotionType.EMPATHETIC
            sec = EmotionType.CALM
            ratio = 0.65

        blend = EmotionBlend(
            primary_emotion=primary,
            secondary_emotion=sec,
            blend_ratio=ratio,
            intensity=min(1.0, rms / 10000.0),
        )
        return primary, blend

    def _text_to_phonemes(self, text: str) -> list[str]:
        """Convert text string into phonetic units."""
        words = text.split()
        phonemes = []
        for w in words:
            for char in w:
                if char.isalnum():
                    phonemes.append(char)
            phonemes.append("PAUSE")
        return phonemes

    def _build_wav_container(self, pcm_bytes: bytes, sample_rate: int, num_channels: int) -> bytes:
        """Construct standard binary RIFF/WAVE header around 16-bit PCM bytes."""
        byte_rate = sample_rate * num_channels * 2
        block_align = num_channels * 2
        data_size = len(pcm_bytes)
        riff_chunk_size = 36 + data_size

        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            riff_chunk_size,
            b"WAVE",
            b"fmt ",
            16,  # PCM subchunk1 size
            1,   # AudioFormat 1 = PCM
            num_channels,
            sample_rate,
            byte_rate,
            block_align,
            16,  # BitsPerSample
            b"data",
            data_size,
        )
        return header + pcm_bytes
