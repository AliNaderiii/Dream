"""Temporal Knowledge Graph Engine, Jalali Date Alignment & Cross-Modal Reasoning."""

from __future__ import annotations

import re
import time
from typing import Any

from dream.knowledge.graph import MultimodalTemporalGraph, normalize_entity_key
from dream.knowledge.types import (
    EntityNode,
    EntityType,
    ModalityType,
    RelationType,
    TemporalInterval,
    TemporalQueryResult,
)


def jalali_to_timestamp(jalali_str: str) -> float:
    """Convert Jalali date string (e.g. '1403/06/25' or '1403-06-25') to Unix timestamp."""
    digits_normalized = jalali_str.translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    )
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", digits_normalized)
    if not m:
        return time.time()

    jy, jm, jd = int(m.group(1)), int(m.group(2)), int(m.group(3))

    # Approximate epoch conversion for Jalali 1348-1450 (1348 SH approx 1970 AD)
    if jm <= 6:
        day_of_year = (jm - 1) * 31 + jd
    else:
        day_of_year = 6 * 31 + (jm - 7) * 30 + jd

    # 1348/10/11 is approx 1970-01-01 (Unix Epoch)
    total_days = int((jy - 1348) * 365.242) + day_of_year - 287
    return max(0.0, total_days * 86400.0)


def timestamp_to_jalali(ts: float) -> str:
    """Convert Unix timestamp to approximate Jalali date string (YYYY/MM/DD)."""
    days = int(ts / 86400.0) + 287
    jy = 1348 + int(days / 365.242)
    day_in_year = int(days % 365.242)

    if day_in_year <= 186:
        jm = max(1, min(6, int(day_in_year / 31) + 1))
        jd = max(1, min(31, int(day_in_year % 31) + 1))
    else:
        rem = day_in_year - 186
        jm = max(7, min(12, int(rem / 30) + 7))
        jd = max(1, min(30, int(rem % 30) + 1))

    return f"{jy:04d}/{jm:02d}/{jd:02d}"


class TemporalKnowledgeEngine:
    """Orchestrates cross-modal entity linking, temporal indexing, and multi-hop queries."""

    def __init__(self, graph: MultimodalTemporalGraph | None = None) -> None:
        self.graph = graph or MultimodalTemporalGraph()

    def ingest_ocr_result(
        self,
        ocr_data: Any,
        artifact_id: str = "",
    ) -> list[EntityNode]:
        """Extract and link entities, transactions, and temporal events from OCR result."""
        fields: dict[str, Any] = {}
        cleaned_text: str = ""
        file_path: str = ""

        if hasattr(ocr_data, "to_dict"):
            d = ocr_data.to_dict()
            fields = d.get("extracted_fields", {})
            cleaned_text = d.get("cleaned_text", "")
            file_path = d.get("file_path", "")
        elif isinstance(ocr_data, dict):
            fields = ocr_data.get("extracted_fields", {})
            cleaned_text = ocr_data.get("cleaned_text", "")
            file_path = ocr_data.get("file_path", "")
        elif isinstance(ocr_data, str):
            cleaned_text = ocr_data

        nodes_created: list[EntityNode] = []
        now = time.time()

        # 1. Parse Date and Temporal Interval
        jalali_str = fields.get("date", "")
        ts = jalali_to_timestamp(jalali_str) if jalali_str else now
        if not jalali_str:
            jalali_str = timestamp_to_jalali(ts)

        temporal = TemporalInterval(valid_from=ts, jalali_date=jalali_str)

        # 2. Document/Invoice Node
        clean_name = file_path.replace("\\", "/").split("/")[-1] if file_path else ""
        doc_label = (
            f"\u0633\u0646\u062f OCR: {clean_name}"
            if clean_name
            else "\u0633\u0646\u062f \u0627\u0633\u06a9\u0646 \u0634\u062f\u0647"
        )
        is_invoice = "total_amount" in fields
        doc_node = self.graph.add_node(
            name=doc_label,
            entity_type=EntityType.INVOICE if is_invoice else EntityType.DOCUMENT,
            modalities=[ModalityType.OCR],
            attributes={
                "file_path": file_path,
                "tracking_code": fields.get("tracking_code", ""),
                "iban": fields.get("iban", ""),
                "total_amount": fields.get("total_amount"),
                "tax": fields.get("tax"),
            },
            temporal=temporal,
        )
        nodes_created.append(doc_node)

        # 3. Vendor / Organization Node
        vendor_name = fields.get("vendor", "").strip()
        if vendor_name:
            vendor_node = self.graph.add_node(
                name=vendor_name,
                entity_type=EntityType.VENDOR,
                modalities=[ModalityType.OCR, ModalityType.TEXT],
                attributes={"iban": fields.get("iban", "")},
                temporal=temporal,
            )
            nodes_created.append(vendor_node)
            self.graph.add_edge(
                source=doc_node,
                target=vendor_node,
                relation_type=RelationType.ISSUED_BY,
                modality=ModalityType.OCR,
                context_snippet=cleaned_text[:120],
                timestamp=ts,
            )

        # 4. Financial Transaction Node
        if "total_amount" in fields:
            t_amt = fields["total_amount"]
            tx_name = (
                f"\u062a\u0631\u0627\u06a9\u0646\u0634: "
                f"{t_amt} \u062a\u0648\u0645\u0627\u0646"
            )
            tx_node = self.graph.add_node(
                name=tx_name,
                entity_type=EntityType.TRANSACTION,
                modalities=[ModalityType.OCR, ModalityType.STRUCTURED],
                attributes={
                    "amount": fields["total_amount"],
                    "tax": fields.get("tax", 0),
                    "tracking_code": fields.get("tracking_code", ""),
                    "iban": fields.get("iban", ""),
                },
                temporal=temporal,
            )
            nodes_created.append(tx_node)
            self.graph.add_edge(
                source=doc_node,
                target=tx_node,
                relation_type=RelationType.CONTAINS_ITEM,
                modality=ModalityType.OCR,
                timestamp=ts,
            )

        # 5. Record Chronological Timeline Event
        v_title = vendor_name or doc_label
        amt_str = str(fields.get("total_amount", "\u0646\u0627\u0645\u0634\u062e\u0635"))
        desc = (
            f"\u0627\u0633\u062a\u062e\u0631\u0627\u062c \u0633\u0646\u062f OCR \u0627\u0632 "
            f"{v_title} \u0628\u0647 \u0645\u0628\u0644\u063a {amt_str}"
        )
        self.graph.add_timeline_event(
            entity=doc_node,
            event_type="ocr_extraction",
            modality=ModalityType.OCR,
            description=desc,
            jalali_date=jalali_str,
            related_entities=[n.name for n in nodes_created if n.id != doc_node.id],
            timestamp=ts,
            metadata={"fields": fields},
        )

        return nodes_created

    def ingest_speech_result(
        self,
        speech_data: Any,
        speaker_name: str = "\u06a9\u0627\u0631\u0628\u0631",
        artifact_id: str = "",
    ) -> list[EntityNode]:
        """Extract and link entities, vocal emotions, and events from Speech results."""
        text: str = ""
        duration: float = 0.0
        audio_path: str = ""
        emotion: str = "neutral"
        blend_d: dict[str, Any] | None = None

        if hasattr(speech_data, "to_dict"):
            d = speech_data.to_dict()
            text = d.get("text", "")
            duration = d.get("duration", d.get("duration_seconds", 0.0))
            audio_path = d.get("audio_path", "")
            emotion = d.get("overall_emotion", d.get("emotion_applied", "neutral"))
            blend_d = d.get("emotion_blend")
        elif isinstance(speech_data, dict):
            text = speech_data.get("text", "")
            duration = speech_data.get("duration", speech_data.get("duration_seconds", 0.0))
            audio_path = speech_data.get("audio_path", "")
            emotion = speech_data.get("overall_emotion") or speech_data.get(
                "emotion_applied", "neutral"
            )
            blend_d = speech_data.get("emotion_blend")
        elif isinstance(speech_data, str):
            text = speech_data

        nodes_created: list[EntityNode] = []
        now = time.time()
        jalali_str = timestamp_to_jalali(now)
        temporal = TemporalInterval(valid_from=now, jalali_date=jalali_str)

        # 1. Speaker Person Node
        speaker_node = self.graph.add_node(
            name=speaker_name,
            entity_type=EntityType.PERSON,
            modalities=[ModalityType.AUDIO, ModalityType.TEXT],
            temporal=temporal,
        )
        nodes_created.append(speaker_node)

        # 2. Audio Note Node
        snippet = text[:25]
        note_name = (
            f"\u06cc\u0627\u062f\u062f\u0627\u0634\u062a \u0635\u0648\u062a\u06cc: {snippet}..."
            if snippet
            else "\u0641\u0627\u06cc\u0644 \u0635\u0648\u062a\u06cc"
        )
        audio_node = self.graph.add_node(
            name=note_name,
            entity_type=EntityType.AUDIO_NOTE,
            modalities=[ModalityType.AUDIO],
            attributes={
                "audio_path": audio_path,
                "duration": duration,
                "transcription": text,
                "emotion": emotion,
                "emotion_blend": blend_d,
            },
            temporal=temporal,
        )
        nodes_created.append(audio_node)

        # Edge: AudioNote -> Speaker
        self.graph.add_edge(
            source=audio_node,
            target=speaker_node,
            relation_type=RelationType.DISCUSSED_IN,
            modality=ModalityType.AUDIO,
            context_snippet=text[:100],
            timestamp=now,
        )

        # 3. Emotion Node
        emotion_node = self.graph.add_node(
            name=f"\u062d\u0627\u0644\u062a \u0627\u062d\u0633\u0627\u0633\u06cc: {emotion}",
            entity_type=EntityType.CONCEPT,
            modalities=[ModalityType.AUDIO],
            attributes={"emotion_name": emotion, "blend": blend_d},
            temporal=temporal,
        )
        nodes_created.append(emotion_node)

        self.graph.add_edge(
            source=audio_node,
            target=emotion_node,
            relation_type=RelationType.EMOTIONAL_TONE,
            modality=ModalityType.AUDIO,
            timestamp=now,
        )

        # 4. Record Timeline Event
        snip60 = text[:60]
        desc = (
            f"\u062b\u0628\u062a \u06af\u0641\u062a\u0627\u0631 "
            f"\u0635\u0648\u062a\u06cc \u062a\u0648\u0633\u0637 {speaker_name} "
            f"\u0628\u0627 \u0627\u062d\u0633\u0627\u0633 [{emotion}]: \"{snip60}\""
        )
        self.graph.add_timeline_event(
            entity=audio_node,
            event_type="speech_interaction",
            modality=ModalityType.AUDIO,
            description=desc,
            jalali_date=jalali_str,
            related_entities=[speaker_node.name, emotion_node.name],
            timestamp=now,
            metadata={"duration": duration, "text": text},
        )

        return nodes_created

    def ingest_text_entity(
        self,
        name: str,
        entity_type: EntityType = EntityType.CONCEPT,
        aliases: list[str] | None = None,
        attributes: dict[str, Any] | None = None,
        valid_from_jalali: str = "",
    ) -> EntityNode:
        """Manually add or update text-based entity."""
        ts = jalali_to_timestamp(valid_from_jalali) if valid_from_jalali else time.time()
        j_str = valid_from_jalali or timestamp_to_jalali(ts)
        temp = TemporalInterval(valid_from=ts, jalali_date=j_str)

        return self.graph.add_node(
            name=name,
            entity_type=entity_type,
            aliases=aliases,
            modalities=[ModalityType.TEXT],
            attributes=attributes or {},
            temporal=temp,
        )

    def query_temporal_knowledge(
        self,
        query: str,
        entity_types: list[EntityType] | None = None,
        start_jalali: str = "",
        end_jalali: str = "",
        limit: int = 20,
    ) -> TemporalQueryResult:
        """Run cross-modal temporal search and narrative synthesis across knowledge graph."""
        start_ts = jalali_to_timestamp(start_jalali) if start_jalali else None
        end_ts = jalali_to_timestamp(end_jalali) if end_jalali else None

        norm_q = normalize_entity_key(query)

        # 1. Matched Nodes
        matched_nodes: list[EntityNode] = []
        for node in self.graph._nodes.values():
            if entity_types and node.entity_type not in entity_types:
                continue

            node_key = normalize_entity_key(node.name)
            alias_match = any(norm_q in normalize_entity_key(a) for a in node.aliases)
            attr_match = any(norm_q in str(v).lower() for v in node.attributes.values())
            if norm_q in node_key or alias_match or attr_match:
                matched_nodes.append(node)

        # 2. Matched Timeline Events
        events = self.graph.query_timeline(
            start_time=start_ts,
            end_time=end_ts,
            entity_name=query if matched_nodes else None,
            limit=limit,
        )

        # 3. Matched Edges
        matched_edges: list[Any] = []
        matched_ids = {n.id for n in matched_nodes}
        for edge in self.graph._edges.values():
            if edge.source_id in matched_ids or edge.target_id in matched_ids:
                matched_edges.append(edge)

        # 4. Synthesize Story Narrative
        narrative_lines = [
            f"\U0001f50d \u0646\u062a\u0627\u06cc\u062c \u062c\u0633\u062a\u062c\u0648\u06cc "
            f"\u06af\u0631\u0627\u0641 \u062f\u0627\u0646\u0634 \u0632\u0645\u0627\u0646\u06cc "
            f"(\u06a9\u0644\u06cc\u062f\u0648\u0627\u0698\u0647: '{query}'):",
        ]
        if matched_nodes:
            cnt_n = len(matched_nodes)
            f_hdr = (
                f"\u2022 \u062a\u0639\u062f\u0627\u062f {cnt_n} "
                f"\u0645\u0648\u062c\u0648\u062f\u06cc\u062a "
                f"(Entity) \u06cc\u0627\u0641\u062a \u0634\u062f:"
            )
            narrative_lines.append(f_hdr)
            for n in matched_nodes[:5]:
                mods = ",".join(m.value for m in n.modalities)
                narrative_lines.append(f"   - [{n.entity_type.value}] {n.name} (Modality: {mods})")

        if events:
            cnt_e = len(events)
            ev_hdr = (
                f"\u2022 \u062a\u0627\u06cc\u0645\u200c\u0644\u0627\u06cc\u0646 "
                f"\u0631\u0648\u06cc\u062f\u0627\u062f\u0647\u0627 "
                f"({cnt_e} \u0645\u0648\u0631\u062f):"
            )
            narrative_lines.append(ev_hdr)
            for ev in events[:5]:
                j_d = ev.jalali_date or "N/A"
                narrative_lines.append(f"   [{j_d}] ({ev.modality.value}) {ev.description}")

        narrative = "\n".join(narrative_lines)

        return TemporalQueryResult(
            query=query,
            matched_nodes=matched_nodes,
            matched_edges=matched_edges,
            timeline_events=events,
            summary_narrative=narrative,
            total_matches=len(matched_nodes) + len(events),
        )
