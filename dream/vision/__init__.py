"""Multi-Modal Vision and Video Stream Understanding Subsystem for Dream."""

from __future__ import annotations

from dream.vision.diagram_inspector import DiagramInspector
from dream.vision.engine import VisionEngine, get_vision_engine
from dream.vision.keyframe_extractor import KeyframeExtractor
from dream.vision.multimodal_sync import (
    MultiModalStreamSynchronizer,
    get_multimodal_synchronizer,
)
from dream.vision.slash import handle_vision_command
from dream.vision.spatial_memory import SpatialMemory
from dream.vision.stream_engine import (
    RealtimeVisualStreamEngine,
    VisualStreamFrame,
    get_visual_stream_engine,
)
from dream.vision.tools import (
    get_vision_tools,
    reset_global_vision_engine,
    vision_analyze_image,
    vision_decompose_video,
    vision_diff_visual_states,
    vision_get_metrics,
    vision_get_multimodal_context,
    vision_ground_ui_elements,
    vision_ingest_stream_frame,
    vision_inspect_diagram,
    vision_query_live_stream,
    vision_query_spatial_memory,
    vision_reset,
    vision_start_live_stream,
    vision_stop_live_stream,
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
    "MultiModalStreamSynchronizer",
    "RealtimeVisualStreamEngine",
    "SpatialEntity",
    "SpatialMemory",
    "SpatialRelationType",
    "UIElementGrounding",
    "UIGrounder",
    "VideoTimeline",
    "VisionEngine",
    "VisualDiffResult",
    "VisualStreamFrame",
    "get_multimodal_synchronizer",
    "get_vision_engine",
    "get_vision_tools",
    "get_visual_stream_engine",
    "handle_vision_command",
    "reset_global_vision_engine",
    "vision_analyze_image",
    "vision_decompose_video",
    "vision_diff_visual_states",
    "vision_get_metrics",
    "vision_get_multimodal_context",
    "vision_ground_ui_elements",
    "vision_ingest_stream_frame",
    "vision_inspect_diagram",
    "vision_query_live_stream",
    "vision_query_spatial_memory",
    "vision_reset",
    "vision_start_live_stream",
    "vision_stop_live_stream",
]
