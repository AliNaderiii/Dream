"""Comprehensive tests for Multimodal Temporal Knowledge Graph and Entity Linking."""

from __future__ import annotations

import tempfile
from pathlib import Path

from dream.knowledge import (
    EntityType,
    ModalityType,
    MultimodalTemporalGraph,
    RelationType,
    TemporalInterval,
    TemporalKnowledgeEngine,
    get_knowledge_tools,
    handle_knowledge_command,
    jalali_to_timestamp,
    knowledge_add_entity,
    knowledge_add_relation,
    knowledge_get_entity_timeline,
    knowledge_get_stats,
    knowledge_link_multimodal_artifact,
    knowledge_query_temporal,
    reset_global_knowledge_engine,
    timestamp_to_jalali,
)
from dream.tools.toolsets import BUILTIN_TOOLSETS, get_toolset


def test_temporal_types_and_jalali_conversion():
    # Jalali conversion test
    j_date = "1403/06/25"
    ts = jalali_to_timestamp(j_date)
    assert ts > 0.0
    converted_back = timestamp_to_jalali(ts)
    assert converted_back.startswith("1403/06")

    # Interval test
    interval = TemporalInterval(valid_from=ts, jalali_date=j_date)
    assert interval.is_active_at(ts + 100) is True
    assert interval.is_active_at(ts - 1000) is False
    d_int = interval.to_dict()
    assert d_int["jalali_date"] == j_date


def test_multimodal_temporal_graph_operations():
    graph = MultimodalTemporalGraph()

    # Add Node with aliases and modalities
    node1 = graph.add_node(
        name="شرکت فناوری دریم",
        entity_type=EntityType.ORGANIZATION,
        aliases=["دریم تک", "Dream Tech"],
        modalities=[ModalityType.TEXT, ModalityType.OCR],
    )
    assert node1.name == "شرکت فناوری دریم"
    assert "Dream Tech" in node1.aliases
    assert ModalityType.OCR in node1.modalities

    # Alias lookup
    found = graph.find_node("Dream Tech")
    assert found is not None
    assert found.id == node1.id

    # Add second node & edge
    node2 = graph.add_node(
        name="پروژه دستیار هوشمند",
        entity_type=EntityType.PROJECT,
        modalities=[ModalityType.TEXT],
    )
    edge = graph.add_edge(
        source=node1,
        target=node2,
        relation_type=RelationType.BELONGS_TO,
        weight=1.5,
        modality=ModalityType.TEXT,
        context_snippet="توسعه فازهای پیشرفته",
    )
    assert edge.source_id == node1.id
    assert edge.target_id == node2.id
    assert edge.weight == 1.5

    # k-hop query
    k_hops = graph.query_k_hop("شرکت فناوری دریم", max_hops=2)
    assert len(k_hops) == 1
    assert k_hops[0]["target"] == "پروژه دستیار هوشمند"

    # Export & Import JSON
    with tempfile.TemporaryDirectory() as tmpdir:
        json_file = str(Path(tmpdir) / "kg_backup.json")
        graph.export_json(json_file)
        assert Path(json_file).exists()

        new_graph = MultimodalTemporalGraph()
        new_graph.import_json(json_file)
        assert len(new_graph._nodes) == 2
        assert len(new_graph._edges) == 1


def test_engine_ingest_ocr_invoice_multimodal():
    engine = TemporalKnowledgeEngine()

    mock_ocr = {
        "file_path": "/workspace/invoices/invoice_1042.pdf",
        "cleaned_text": "فاکتور خرید خدمات هوش مصنوعی بازرگانی امید",
        "extracted_fields": {
            "vendor": "بازرگانی امید",
            "date": "1403/06/25",
            "total_amount": 5500000,
            "tax": 550000,
            "tracking_code": "TRK-778899",
            "iban": "IR120000000000000000000001",
        },
    }

    nodes = engine.ingest_ocr_result(mock_ocr)
    assert len(nodes) >= 3

    # Verify Vendor Node
    vendor = engine.graph.find_node("بازرگانی امید")
    assert vendor is not None
    assert vendor.entity_type == EntityType.VENDOR
    assert ModalityType.OCR in vendor.modalities

    # Verify Transaction Node
    tx_nodes = [n for n in nodes if n.entity_type == EntityType.TRANSACTION]
    assert len(tx_nodes) == 1
    assert tx_nodes[0].attributes["amount"] == 5500000

    # Verify Timeline Events
    timeline = engine.graph.query_timeline()
    assert len(timeline) >= 1
    assert timeline[0].modality == ModalityType.OCR
    assert timeline[0].jalali_date == "1403/06/25"


def test_engine_ingest_speech_audio_multimodal():
    engine = TemporalKnowledgeEngine()

    mock_speech = {
        "audio_path": "/workspace/audio/voice_note_1.wav",
        "duration": 4.5,
        "text": "جلسه بررسی عملکرد مدل دریم با موفقیت انجام شد",
        "overall_emotion": "joyful",
        "emotion_blend": {
            "primary_emotion": "joyful",
            "secondary_emotion": "enthusiastic",
            "blend_ratio": 0.8,
        },
    }

    nodes = engine.ingest_speech_result(mock_speech, speaker_name="علی")
    assert len(nodes) >= 3

    speaker = engine.graph.find_node("علی")
    assert speaker is not None
    assert speaker.entity_type == EntityType.PERSON
    assert ModalityType.AUDIO in speaker.modalities

    # Emotion node
    emo_nodes = [n for n in nodes if "joyful" in n.name]
    assert len(emo_nodes) == 1


def test_cross_modal_temporal_query_and_narrative():
    engine = TemporalKnowledgeEngine()

    # Ingest OCR artifact
    engine.ingest_ocr_result({
        "file_path": "inv_01.txt",
        "extracted_fields": {
            "vendor": "فروشگاه مرکزی دریم",
            "date": "1403/06/25",
            "total_amount": 1200000,
        },
    })

    # Ingest Speech artifact
    engine.ingest_speech_result({
        "audio_path": "audio_01.wav",
        "text": "خرید از فروشگاه مرکزی دریم تایید شد",
        "overall_emotion": "calm",
    })

    # Query by keyword across modalities
    res = engine.query_temporal_knowledge(query="دریم")
    assert res.total_matches >= 2
    assert len(res.matched_nodes) >= 1
    assert len(res.timeline_events) >= 1
    assert "دریم" in res.summary_narrative


def test_knowledge_tools_and_security():
    reset_global_knowledge_engine()

    tools = get_knowledge_tools()
    assert len(tools) == 6

    # 1. Add entity
    res_ent = knowledge_add_entity(
        name="سرور ابری تهران",
        entity_type="organization",
        aliases="ابر تهران, Cloud Tehran",
        attributes={"region": "tehran-1"},
        valid_from_jalali="1403/01/01",
    )
    assert res_ent["success"] is True
    assert res_ent["entity"]["name"] == "سرور ابری تهران"

    # 2. Add relation
    res_rel = knowledge_add_relation(
        source_name="سرور ابری تهران",
        target_name="پروژه دریم",
        relation_type="belongs_to",
        context_snippet="زیرساخت اصلی پردازش ابری",
    )
    assert res_rel["success"] is True

    # 3. Query temporal
    q_res = knowledge_query_temporal(query="تهران")
    assert q_res["success"] is True
    assert len(q_res["matched_nodes"]) >= 1

    # 4. Get entity timeline
    t_res = knowledge_get_entity_timeline("سرور ابری تهران")
    assert t_res["success"] is True
    assert len(t_res["relationships"]) >= 1

    # 5. Link multimodal artifact
    link_res = knowledge_link_multimodal_artifact(
        artifact_type="ocr",
        artifact_data={
            "file_path": "server_invoice.pdf",
            "extracted_fields": {
                "vendor": "سرور ابری تهران",
                "total_amount": 3000000,
                "date": "1403/06/25",
            },
        },
    )
    assert link_res["success"] is True
    assert len(link_res["linked_nodes"]) >= 2

    # 6. Stats
    stats_res = knowledge_get_stats()
    assert stats_res["success"] is True
    assert stats_res["total_nodes"] >= 2

    reset_global_knowledge_engine()


def test_knowledge_slash_command_and_toolset_registration():
    reset_global_knowledge_engine()

    lines = []
    handle_knowledge_command("/kg stats", output=lines.append)
    assert any("Temporal KG" in line for line in lines)

    lines.clear()
    handle_knowledge_command("/kg query دریم", output=lines.append)
    assert len(lines) >= 1

    lines.clear()
    handle_knowledge_command("/kg timeline سرور", output=lines.append)
    assert len(lines) >= 1

    # Toolset check
    assert "knowledge" in BUILTIN_TOOLSETS
    kg_ts = get_toolset("knowledge")
    assert kg_ts is not None
    assert "knowledge_add_entity" in kg_ts.tools
    assert "knowledge_query_temporal" in kg_ts.tools

    reset_global_knowledge_engine()
