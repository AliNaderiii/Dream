"""Comprehensive tests for Speech Synthesis, STT, HybridEmo Emotion, and Document OCR subsystem."""

from __future__ import annotations

import tempfile
from pathlib import Path

from dream.ocr import (
    DocumentType,
    OCREngine,
    get_ocr_tools,
    handle_ocr_command,
    ocr_extract_document,
    ocr_extract_invoice,
    reset_global_ocr_engine,
)
from dream.speech import (
    AudioFormat,
    EmotionBlend,
    EmotionTrajectorySegment,
    EmotionType,
    SpeechEngine,
    STTRequest,
    TTSRequest,
    VoicePersona,
    get_speech_tools,
    handle_speech_command,
    reset_global_speech_engine,
    speech_analyze_voice_emotion,
    speech_list_voices,
    speech_speech_to_text,
    speech_text_to_speech,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


def test_speech_types_and_emotion_serialization():
    seg = EmotionTrajectorySegment(
        start_emotion=EmotionType.JOYFUL,
        end_emotion=EmotionType.CALM,
        start_time=0.0,
        end_time=2.0,
        intensity=0.9,
    )
    assert seg.get_intensity_at(0.0) == 0.9
    assert seg.get_intensity_at(2.0) == 0.9
    d_seg = seg.to_dict()
    assert d_seg["start_emotion"] == "joyful"
    assert d_seg["end_emotion"] == "calm"

    blend = EmotionBlend(
        primary_emotion=EmotionType.JOYFUL,
        secondary_emotion=EmotionType.EMPATHETIC,
        blend_ratio=0.8,
        intensity=0.95,
    )
    d_blend = blend.to_dict()
    assert d_blend["primary_emotion"] == "joyful"
    assert d_blend["blend_ratio"] == 0.8

    persona = VoicePersona(
        voice_id="fa-test",
        name="Test Persona",
        language="fa",
        gender="female",
    )
    assert persona.to_dict()["voice_id"] == "fa-test"


def test_soprano_fast_tts_synthesis():
    reset_global_speech_engine()
    engine = SpeechEngine()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_wav = str(Path(tmpdir) / "output.wav")
        req = TTSRequest(
            text="Dream assistant fast audio generation.",
            voice_id="soprano-fast",
            output_path=out_wav,
            output_format=AudioFormat.WAV,
        )
        res = engine.synthesize(req)
        assert res.duration_seconds > 0.0
        assert res.format == "wav"
        assert Path(out_wav).exists()

        data = Path(out_wav).read_bytes()
        assert data.startswith(b"RIFF")
        assert b"WAVE" in data[:12]
        assert b"fmt " in data
        assert b"data" in data


def test_hybridemo_emotional_modulation_and_trajectory():
    engine = SpeechEngine()

    # Test Emotion Blend
    blend = EmotionBlend(
        primary_emotion=EmotionType.JOYFUL,
        secondary_emotion=EmotionType.ENTHUSIASTIC,
        blend_ratio=0.75,
    )
    req_blend = TTSRequest(
        text="\u0627\u0645\u0631\u0648\u0632 \u06cc\u06a9 \u0631\u0648\u0632 \u062e\u0648\u0628",
        voice_id="fa-roya",
        emotion=blend,
    )
    res_blend = engine.synthesize(req_blend)
    assert "Blend" in res_blend.emotion_applied
    assert res_blend.metadata["pitch_factor"] > 1.0

    # Test Emotion Trajectory
    trajectory = [
        EmotionTrajectorySegment(
            start_emotion=EmotionType.SURPRISED,
            end_emotion=EmotionType.CALM,
            start_time=0.0,
            end_time=1.0,
        )
    ]
    req_traj = TTSRequest(
        text="A sequential trajectory test passage.",
        voice_id="hybrid-expressive",
        trajectory=trajectory,
    )
    res_traj = engine.synthesize(req_traj)
    assert "Trajectory" in res_traj.emotion_applied


def test_persian_stt_and_emotion_recognition():
    engine = SpeechEngine()

    # Generate test audio
    tts_req = TTSRequest(
        text="\u062f\u0631\u06cc\u0645 \u062f\u0633\u062a\u06cc\u0627\u0631",
        voice_id="fa-mina",
        emotion=EmotionType.CALM,
    )
    tts_res = engine.synthesize(tts_req)

    # Transcribe & analyze emotion
    stt_req = STTRequest(audio_path=tts_res.audio_path, language="fa")
    stt_res = engine.transcribe(stt_req)
    assert len(stt_res.text) > 0
    assert stt_res.language == "fa"
    assert stt_res.confidence >= 0.90
    assert len(stt_res.segments) >= 1
    assert stt_res.overall_emotion in list(EmotionType)


def test_document_ocr_and_financial_invoice_parsing(tmp_path: Path):
    invoice_content = (
        "فاکتور فروش کالا\n"
        "فروشنده: بازرگانی\n"
        "تاریخ: ۱۴۰۳/۰۶/۲۵\n"
        "شماره پیگیری: TRK-987654\n"
        "مبلغ کل: ۲,۵۰۰,۰۰۰\n"
        "مالیات: ۲۵۰,۰۰۰\n"
        "شبا: IR820120000000012345678901\n"
        "| ردیف | شرح | قیمت |\n"
        "| 1 | سرویس ابری | 2500000 |\n"
    )
    inv_file = tmp_path / "sample_invoice.txt"
    inv_file.write_text(invoice_content, encoding="utf-8")

    engine = OCREngine()
    res = engine.extract_document(str(inv_file), doc_type=DocumentType.INVOICE)

    assert res.language == "fa"
    assert res.extracted_fields["total_amount"] == 2500000
    assert res.extracted_fields["date"] == "1403/06/25"
    assert res.extracted_fields["tracking_code"] == "TRK-987654"
    assert res.extracted_fields["tax"] == 250000
    assert res.extracted_fields["iban"] == "IR820120000000012345678901"
    assert "بازرگانی" in res.extracted_fields["vendor"]
    assert len(res.tables) == 1


def test_speech_and_ocr_tools_with_security():
    reset_global_speech_engine()
    reset_global_ocr_engine()

    sp_tools = get_speech_tools()
    assert len(sp_tools) == 4
    ocr_tools = get_ocr_tools()
    assert len(ocr_tools) == 2

    # Speech tools
    tts_res = speech_text_to_speech("Salam", voice_id="fa-mina", emotion="joyful")
    assert tts_res["success"] is True
    audio_path = tts_res["audio_path"]

    stt_res = speech_speech_to_text(audio_path, language="fa")
    assert stt_res["success"] is True

    emo_res = speech_analyze_voice_emotion(audio_path)
    assert emo_res["success"] is True
    assert "overall_emotion" in emo_res

    v_res = speech_list_voices()
    assert v_res["success"] is True
    assert len(v_res["voices"]) >= 4

    # Security path blocking
    blocked_tts = speech_text_to_speech("Evil", output_path="/etc/passwd")
    assert blocked_tts["success"] is False
    assert "Permission denied" in blocked_tts["error"]

    blocked_ocr = ocr_extract_document("/etc/shadow")
    assert blocked_ocr["success"] is False
    assert "Permission denied" in blocked_ocr["error"]

    # OCR Invoice tool
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", encoding="utf-8", delete=False) as tf:
        tf.write("\u0645\u0628\u0644\u063a \u06a9\u0644: \u06f5\u06f0\u06f0,\u06f0\u06f0\u06f0")
        tf_name = tf.name

    inv_tool_res = ocr_extract_invoice(tf_name)
    assert inv_tool_res["success"] is True
    assert inv_tool_res["extracted_fields"]["total_amount"] == 500000

    reset_global_speech_engine()
    reset_global_ocr_engine()


def test_speech_ocr_slash_commands_and_toolsets():
    reset_global_speech_engine()
    reset_global_ocr_engine()

    # Slash /speech
    lines = []
    handle_speech_command("/speech voices", output=lines.append)
    assert any("Voice Personas" in line for line in lines)

    lines.clear()
    handle_speech_command("/speech tts Test", output=lines.append)
    assert len(lines) >= 1

    # Slash /ocr
    lines.clear()
    handle_ocr_command("/ocr help", output=lines.append)
    assert any("ocr" in line.lower() for line in lines)

    # Toolset registration
    assert "speech" in BUILTIN_TOOLSETS
    assert "ocr" in BUILTIN_TOOLSETS
    sp_ts = get_toolset("speech")
    assert sp_ts is not None
    assert "speech_text_to_speech" in sp_ts.tools

    ocr_ts = get_toolset("ocr")
    assert ocr_ts is not None
    assert "ocr_extract_document" in ocr_ts.tools

    reset_global_speech_engine()
    reset_global_ocr_engine()
