"""Master Multi-Modal Vision & Video Stream Reasoning Engine for Dream Agent."""

from __future__ import annotations

import time
import uuid
from typing import Any

from dream.vision.diagram_inspector import DiagramInspector
from dream.vision.keyframe_extractor import KeyframeExtractor
from dream.vision.spatial_memory import SpatialMemory
from dream.vision.types import (
    BoundingBox,
    VideoTimeline,
    VisualDiffResult,
)
from dream.vision.ui_grounder import UIGrounder


class VisionEngine:
    """Master engine orchestrating multi-modal vision perception and video stream reasoning."""

    def __init__(self) -> None:
        self.keyframe_extractor = KeyframeExtractor()
        self.ui_grounder = UIGrounder()
        self.diagram_inspector = DiagramInspector()
        self.spatial_memory = SpatialMemory()
        self._start_time = time.time()
        self._total_analyses_count = 0

    def analyze_image(
        self,
        image_descriptor: dict[str, Any] | str,
        detected_objects: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Perform multi-modal visual analysis and ground objects in spatial memory."""
        self._total_analyses_count += 1
        objects = detected_objects or []

        registered_entities = []
        for obj in objects:
            label = obj.get("label_fa") or obj.get("label") or "شیء بصری"
            cat = obj.get("category", "general")
            b_raw = obj.get("box", {})
            box = BoundingBox(
                ymin=float(b_raw.get("ymin", 0.0)),
                xmin=float(b_raw.get("xmin", 0.0)),
                ymax=float(b_raw.get("ymax", 1.0)),
                xmax=float(b_raw.get("xmax", 1.0)),
            )
            ent = self.spatial_memory.register_entity(
                label_fa=label,
                category=cat,
                box=box,
                attributes=obj.get("attributes", {}),
            )
            registered_entities.append(ent)

        summary_fa = (
            f"تحلیل تصویر با شناسایی {len(registered_entities)} موجودیت بصری "
            f"و ثبت در حافظه مکانی انجام شد."
        )

        return {
            "success": True,
            "analysis_id": f"ana-{uuid.uuid4().hex[:6]}",
            "total_objects_detected": len(registered_entities),
            "objects": [e.to_dict() for e in registered_entities],
            "summary_fa": summary_fa,
        }

    def decompose_video(
        self,
        video_id: str,
        duration_sec: float = 10.0,
        fps: float = 30.0,
        frames: list[bytes | str] | None = None,
    ) -> VideoTimeline:
        """Decompose video into keyframes, scenes, and narrative events."""
        self._total_analyses_count += 1
        if frames:
            return self.keyframe_extractor.extract_from_stream(
                video_id=video_id,
                frames_data=frames,
                fps=fps,
            )
        return self.keyframe_extractor.extract_from_simulated_video(
            video_id=video_id,
            duration_sec=duration_sec,
            fps=fps,
        )

    def ground_ui_elements(
        self,
        elements_spec: list[dict[str, Any]],
        intent_fa: str = "",
    ) -> dict[str, Any]:
        """Ground interactive screen elements and propose visual action sequence."""
        self._total_analyses_count += 1
        grounded = self.ui_grounder.ground_elements_from_descriptors(elements_spec)
        actions = self.ui_grounder.propose_action_sequence(grounded, intent_fa) if intent_fa else []

        return {
            "success": True,
            "total_elements": len(grounded),
            "elements": [e.to_dict() for e in grounded],
            "proposed_actions": actions,
        }

    def inspect_diagram(
        self,
        content: str,
        diagram_format: str = "mermaid",
    ) -> dict[str, Any]:
        """Inspect architectural diagram or SVG structure."""
        self._total_analyses_count += 1
        if diagram_format.lower() == "svg":
            return self.diagram_inspector.inspect_svg_elements(content)
        return self.diagram_inspector.inspect_mermaid_source(content)

    def diff_visual_states(
        self,
        before_state: list[dict[str, Any]],
        after_state: list[dict[str, Any]],
    ) -> VisualDiffResult:
        """Compute state transitions and visual diffs."""
        self._total_analyses_count += 1
        mem_before = SpatialMemory()
        mem_after = SpatialMemory()

        ents_before = [
            mem_before.register_entity(
                label_fa=s.get("label_fa", "عنصر"),
                category=s.get("category", "general"),
                box=BoundingBox(
                    ymin=s.get("box", {}).get("ymin", 0.0),
                    xmin=s.get("box", {}).get("xmin", 0.0),
                    ymax=s.get("box", {}).get("ymax", 1.0),
                    xmax=s.get("box", {}).get("xmax", 1.0),
                ),
            )
            for s in before_state
        ]

        ents_after = [
            mem_after.register_entity(
                label_fa=s.get("label_fa", "عنصر"),
                category=s.get("category", "general"),
                box=BoundingBox(
                    ymin=s.get("box", {}).get("ymin", 0.0),
                    xmin=s.get("box", {}).get("xmin", 0.0),
                    ymax=s.get("box", {}).get("ymax", 1.0),
                    xmax=s.get("box", {}).get("xmax", 1.0),
                ),
            )
            for s in after_state
        ]

        return self.spatial_memory.compare_visual_states(ents_before, ents_after)

    def get_metrics(self) -> dict[str, Any]:
        """Return operational telemetry for the vision subsystem."""
        uptime = time.time() - self._start_time
        return {
            "uptime_sec": round(uptime, 2),
            "total_analyses_count": self._total_analyses_count,
            "spatial_entities_in_memory": len(self.spatial_memory.list_entities()),
            "status": "healthy",
        }

    def reset(self) -> None:
        """Reset spatial memory and internal states."""
        self.spatial_memory.clear()
        self._total_analyses_count = 0


# Global singleton
_GLOBAL_VISION_ENGINE: VisionEngine | None = None


def get_vision_engine() -> VisionEngine:
    """Retrieve global singleton VisionEngine instance."""
    global _GLOBAL_VISION_ENGINE
    if _GLOBAL_VISION_ENGINE is None:
        _GLOBAL_VISION_ENGINE = VisionEngine()
    return _GLOBAL_VISION_ENGINE
