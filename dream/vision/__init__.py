"""Autonomous Multi-Modal Vision & Video Stream Reasoning Subsystem for Dream."""

from __future__ import annotations

from dream.vision.diagram_inspector import DiagramInspector
from dream.vision.engine import VisionEngine, get_vision_engine
from dream.vision.keyframe_extractor import KeyframeExtractor
from dream.vision.slash import handle_vision_command
from dream.vision.spatial_memory import SpatialMemory
from dream.vision.tools import (
    get_global_vision_engine,
    get_vision_tools,
    reset_global_vision_engine,
    vision_analyze_image,
    vision_decompose_video,
    vision_diff_visual_states,
    vision_get_metrics,
    vision_ground_ui_elements,
    vision_inspect_diagram,
    vision_query_spatial_memory,
    vision_reset,
)
from dream.vision.types import (
    BoundingBox,
    ElementType,
    ImageFormat,
    KeyFrame,
    SpatialEntity,
    SpatialRelationType,
    UIElementGrounding,
    VideoTimeline,
    VisualDiffResult,
)
from dream.vision.ui_grounder import UIGrounder

__all__ = [
    "BoundingBox",
    "DiagramInspector",
    "ElementType",
    "ImageFormat",
    "KeyFrame",
    "KeyframeExtractor",
    "SpatialEntity",
    "SpatialMemory",
    "SpatialRelationType",
    "UIElementGrounding",
    "UIGrounder",
    "VideoTimeline",
    "VisionEngine",
    "VisualDiffResult",
    "get_global_vision_engine",
    "get_vision_engine",
    "get_vision_tools",
    "handle_vision_command",
    "reset_global_vision_engine",
    "vision_analyze_image",
    "vision_decompose_video",
    "vision_diff_visual_states",
    "vision_get_metrics",
    "vision_ground_ui_elements",
    "vision_inspect_diagram",
    "vision_query_spatial_memory",
    "vision_reset",
]
