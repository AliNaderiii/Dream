"""LLM Agent Tools for Multi-Modal Vision and Video Analysis Subsystem."""

from __future__ import annotations

import logging
from typing import Any

from dream.vision.engine import get_vision_engine, reset_global_vision_engine
from dream.vision.multimodal_sync import get_multimodal_synchronizer
from dream.vision.stream_engine import get_visual_stream_engine

logger = logging.getLogger(__name__)


def vision_analyze_image(
    image_descriptor: dict[str, Any] | str = "",
    detected_objects: list[dict[str, Any]] | None = None,
    image_path: str = "",
    format: str = "png",
    detect_objects: bool = True,
    ocr: bool = True,
) -> dict[str, Any]:
    """Analyze a single image or image descriptor for visual entities and objects."""
    engine = get_vision_engine()
    target = image_descriptor or image_path or "unspecified_image"
    return engine.analyze_image(target, detected_objects)


def vision_decompose_video(
    video_id: str = "video-default",
    duration_sec: float = 10.0,
    fps: float = 30.0,
    frames: list[bytes | str] | None = None,
    video_path: str = "",
    max_keyframes: int = 10,
    similarity_threshold: float = 0.85,
) -> dict[str, Any]:
    """Decompose a video stream into distinct visual keyframes and scene events."""
    engine = get_vision_engine()
    vid = video_id or video_path or "video-stream"
    timeline = engine.decompose_video(
        video_id=vid, duration_sec=duration_sec, fps=fps, frames=frames
    )
    return {
        "success": True,
        "video_id": vid,
        "duration_sec": timeline.duration_sec,
        "timeline": timeline.to_dict(),
    }


def vision_ground_ui_elements(
    elements: list[dict[str, Any]] | None = None,
    intent_fa: str = "",
    elements_spec: list[dict[str, Any]] | None = None,
    image_path: str = "",
    element_type: str = "all",
) -> dict[str, Any]:
    """Detect and ground interactive screen elements (buttons, inputs, menus)."""
    engine = get_vision_engine()
    specs = elements or elements_spec or []
    if not specs and image_path:
        box_d = {"ymin": 0.1, "xmin": 0.1, "ymax": 0.5, "xmax": 0.5}
        specs = [{"id": "elem_1", "label_fa": element_type, "box": box_d}]
    return engine.ground_ui_elements(elements_spec=specs, intent_fa=intent_fa)


def vision_inspect_diagram(
    content: str = "",
    diagram_format: str = "mermaid",
    image_path: str = "",
    diagram_type: str = "auto",
) -> dict[str, Any]:
    """Inspect and extract structure from architecture diagrams and flowcharts."""
    engine = get_vision_engine()
    data = content or image_path or "graph TD\nA-->B"
    fmt = diagram_format if content else diagram_type
    return engine.inspect_diagram(content=data, diagram_format=fmt)


def vision_diff_visual_states(
    before_state: list[dict[str, Any]] | None = None,
    after_state: list[dict[str, Any]] | None = None,
    image_a_path: str = "",
    image_b_path: str = "",
) -> dict[str, Any]:
    """Compare two visual states and return differential modifications."""
    engine = get_vision_engine()
    b_state = before_state or ([{"label_fa": image_a_path}] if image_a_path else [])
    a_state = after_state or ([{"label_fa": image_b_path}] if image_b_path else [])
    diff = engine.diff_visual_states(before_state=b_state, after_state=a_state)
    return {
        "success": True,
        "has_significant_change": diff.has_significant_change,
        "similarity_score": diff.similarity_score,
        "added_elements": diff.added_elements,
        "removed_elements": diff.removed_elements,
        "modified_regions": [r.to_dict() for r in diff.modified_regions],
        "diff": diff.to_dict(),
    }


def vision_query_spatial_memory(query: str = "") -> dict[str, Any]:
    """Query temporal spatial memory for previously seen visual elements."""
    engine = get_vision_engine()
    entities = engine.spatial_memory.list_entities()
    return {
        "success": True,
        "query": query,
        "matches_count": len(entities),
        "results": [e.to_dict() for e in entities],
    }


def vision_get_metrics() -> dict[str, Any]:
    """Retrieve operational metrics for the Vision engine."""
    engine = get_vision_engine()
    return {
        "success": True,
        **engine.get_metrics(),
    }


def vision_reset() -> dict[str, Any]:
    """Reset the vision subsystem state and clear spatial cache."""
    engine = get_vision_engine()
    engine.reset()
    reset_global_vision_engine()
    return {
        "success": True,
        "message": "سامانه بینایی و حافظه مکانی بازنشانی شدند.",
    }


def vision_start_live_stream(stream_id: str = "screen-primary") -> dict[str, Any]:
    """Initialize or reset a real-time screen/webcam visual frame stream."""
    stream_engine = get_visual_stream_engine()
    res = stream_engine.start_stream(stream_id)
    return {
        "success": True,
        "stream": res,
    }


def vision_ingest_stream_frame(
    stream_id: str,
    base64_data: str,
    width: int = 1920,
    height: int = 1080,
) -> dict[str, Any]:
    """Ingest a real-time frame into the visual stream buffer."""
    stream_engine = get_visual_stream_engine()
    frame = stream_engine.ingest_frame(
        stream_id=stream_id,
        base64_data=base64_data,
        width=width,
        height=height,
    )
    return {
        "success": True,
        "frame": frame.to_dict(),
    }


def vision_query_live_stream(
    stream_id: str = "screen-primary",
    window_sec: float = 2.0,
) -> dict[str, Any]:
    """Query current screen/video stream state and recent optical text."""
    stream_engine = get_visual_stream_engine()
    ctx = stream_engine.query_recent_visual_context(stream_id=stream_id, window_sec=window_sec)
    return {
        "success": True,
        "context": ctx,
    }


def vision_get_multimodal_context(
    duplex_session_id: str = "default-duplex",
    visual_stream_id: str = "screen-primary",
) -> dict[str, Any]:
    """Retrieve synchronized audio turn and contemporaneous visual stream context."""
    sync = get_multimodal_synchronizer()
    ctx = sync.get_unified_multimodal_context(
        duplex_session_id=duplex_session_id,
        visual_stream_id=visual_stream_id,
    )
    return {
        "success": True,
        "multimodal_context": ctx,
    }


def vision_stop_live_stream(stream_id: str = "screen-primary") -> dict[str, Any]:
    """Stop and release resources for an active live visual stream."""
    stream_engine = get_visual_stream_engine()
    success = stream_engine.stop_stream(stream_id)
    return {
        "success": success,
        "stream_id": stream_id,
    }


def get_vision_tools() -> list[dict[str, Any]]:
    """Return tool manifests for LLM registration."""
    return [
        {
            "name": "vision_analyze_image",
            "description": "Analyze an image or descriptor for visual entities and objects",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_descriptor": {"type": "string"},
                    "detected_objects": {"type": "array", "items": {"type": "object"}},
                },
            },
            "handler": vision_analyze_image,
        },
        {
            "name": "vision_decompose_video",
            "description": "Decompose a video stream into distinct visual keyframes",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_id": {"type": "string", "default": "video-stream"},
                    "duration_sec": {"type": "number", "default": 10.0},
                    "fps": {"type": "number", "default": 30.0},
                },
            },
            "handler": vision_decompose_video,
        },
        {
            "name": "vision_ground_ui_elements",
            "description": "Detect interactable UI elements on screen (buttons, inputs, menus)",
            "parameters": {
                "type": "object",
                "properties": {
                    "elements": {"type": "array", "items": {"type": "object"}},
                    "intent_fa": {"type": "string"},
                },
            },
            "handler": vision_ground_ui_elements,
        },
        {
            "name": "vision_inspect_diagram",
            "description": "Inspect and extract structure from architecture diagrams",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "diagram_format": {"type": "string", "default": "mermaid"},
                },
            },
            "handler": vision_inspect_diagram,
        },
        {
            "name": "vision_diff_visual_states",
            "description": "Compare two visual states and return differential modifications",
            "parameters": {
                "type": "object",
                "properties": {
                    "before_state": {"type": "array", "items": {"type": "object"}},
                    "after_state": {"type": "array", "items": {"type": "object"}},
                },
            },
            "handler": vision_diff_visual_states,
        },
        {
            "name": "vision_start_live_stream",
            "description": "Initialize or reset a real-time screen/webcam visual frame stream",
            "parameters": {
                "type": "object",
                "properties": {
                    "stream_id": {"type": "string", "default": "screen-primary"},
                },
            },
            "handler": vision_start_live_stream,
        },
        {
            "name": "vision_ingest_stream_frame",
            "description": "Ingest a real-time frame into the visual stream buffer",
            "parameters": {
                "type": "object",
                "properties": {
                    "stream_id": {"type": "string"},
                    "base64_data": {"type": "string"},
                    "width": {"type": "integer", "default": 1920},
                    "height": {"type": "integer", "default": 1080},
                },
                "required": ["stream_id", "base64_data"],
            },
            "handler": vision_ingest_stream_frame,
        },
        {
            "name": "vision_query_live_stream",
            "description": "Query current screen/video stream state and recent optical text",
            "parameters": {
                "type": "object",
                "properties": {
                    "stream_id": {"type": "string", "default": "screen-primary"},
                    "window_sec": {"type": "number", "default": 2.0},
                },
            },
            "handler": vision_query_live_stream,
        },
        {
            "name": "vision_get_multimodal_context",
            "description": "Retrieve synchronized audio turn and visual stream context",
            "parameters": {
                "type": "object",
                "properties": {
                    "duplex_session_id": {"type": "string", "default": "default-duplex"},
                    "visual_stream_id": {"type": "string", "default": "screen-primary"},
                },
            },
            "handler": vision_get_multimodal_context,
        },
        {
            "name": "vision_stop_live_stream",
            "description": "Stop and release resources for an active live visual stream",
            "parameters": {
                "type": "object",
                "properties": {
                    "stream_id": {"type": "string", "default": "screen-primary"},
                },
                "required": ["stream_id"],
            },
            "handler": vision_stop_live_stream,
        },
    ]
