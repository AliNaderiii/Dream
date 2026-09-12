"""LLM Agent Tools and Toolset Definitions for Multi-Modal Vision & Video."""

from __future__ import annotations

import logging
from typing import Any

from dream.vision.engine import VisionEngine, get_vision_engine

logger = logging.getLogger(__name__)

_GLOBAL_VISION_ENGINE: VisionEngine | None = None


def get_global_vision_engine() -> VisionEngine:
    """Retrieve or initialize global singleton VisionEngine."""
    global _GLOBAL_VISION_ENGINE
    if _GLOBAL_VISION_ENGINE is None:
        _GLOBAL_VISION_ENGINE = get_vision_engine()
    return _GLOBAL_VISION_ENGINE


def reset_global_vision_engine() -> None:
    """Reset global VisionEngine instance for test isolation."""
    global _GLOBAL_VISION_ENGINE
    if _GLOBAL_VISION_ENGINE is not None:
        _GLOBAL_VISION_ENGINE.reset()
    _GLOBAL_VISION_ENGINE = None


def vision_analyze_image(
    image_descriptor: str = "",
    detected_objects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Analyze image or scene content and ground entities in spatial memory.

    Args:
        image_descriptor: Textual or visual metadata descriptor of image.
        detected_objects: List of detected objects with bounding boxes.
    """
    engine = get_global_vision_engine()
    return engine.analyze_image(image_descriptor, detected_objects)


def vision_decompose_video(
    video_id: str,
    duration_sec: float = 10.0,
    fps: float = 30.0,
) -> dict[str, Any]:
    """Decompose video stream into keyframes, scene boundaries, and temporal events.

    Args:
        video_id: Unique identifier of video.
        duration_sec: Video length in seconds.
        fps: Framerate.
    """
    engine = get_global_vision_engine()
    timeline = engine.decompose_video(video_id=video_id, duration_sec=duration_sec, fps=fps)
    return {"success": True, **timeline.to_dict()}


def vision_ground_ui_elements(
    elements: list[dict[str, Any]],
    intent_fa: str = "",
) -> dict[str, Any]:
    """Ground interactive GUI elements with pixel coordinates and click targets.

    Args:
        elements: List of UI element specifications with bounding boxes.
        intent_fa: High-level Persian user goal (e.g. 'روی دکمه ورود کلیک کن').
    """
    engine = get_global_vision_engine()
    return engine.ground_ui_elements(elements, intent_fa)


def vision_inspect_diagram(
    content: str,
    diagram_format: str = "mermaid",
) -> dict[str, Any]:
    """Inspect architectural flowchart, Mermaid code, or SVG elements.

    Args:
        content: Mermaid diagram string or SVG XML content.
        diagram_format: Format type ('mermaid' or 'svg').
    """
    engine = get_global_vision_engine()
    return engine.inspect_diagram(content, diagram_format)


def vision_diff_visual_states(
    before_state: list[dict[str, Any]],
    after_state: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare two visual frames or screen states to detect changes and transitions.

    Args:
        before_state: Entities before action.
        after_state: Entities after action.
    """
    engine = get_global_vision_engine()
    diff = engine.diff_visual_states(before_state, after_state)
    return {"success": True, **diff.to_dict()}


def vision_query_spatial_memory() -> dict[str, Any]:
    """Retrieve all visual entities and spatial relations currently in memory."""
    engine = get_global_vision_engine()
    entities = engine.spatial_memory.list_entities()
    return {
        "success": True,
        "total_entities": len(entities),
        "entities": [e.to_dict() for e in entities],
    }


def vision_get_metrics() -> dict[str, Any]:
    """Get operational telemetry of the Vision subsystem."""
    engine = get_global_vision_engine()
    return {"success": True, **engine.get_metrics()}


def vision_reset() -> dict[str, Any]:
    """Reset vision engine and spatial memory."""
    reset_global_vision_engine()
    return {"success": True, "message_fa": "موتور بینایی و حافظه مکانی بازنشانی شد."}


def get_vision_tools() -> list[dict[str, Any]]:
    """Return tool manifests for LLM registration."""
    return [
        {
            "name": "vision_analyze_image",
            "description": "Analyze image content and ground visual entities in spatial memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_descriptor": {"type": "string"},
                    "detected_objects": {"type": "array"},
                },
            },
            "handler": vision_analyze_image,
        },
        {
            "name": "vision_decompose_video",
            "description": "Decompose video stream into keyframes, scenes, and temporal timeline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_id": {"type": "string"},
                    "duration_sec": {"type": "number", "default": 10.0},
                    "fps": {"type": "number", "default": 30.0},
                },
                "required": ["video_id"],
            },
            "handler": vision_decompose_video,
        },
        {
            "name": "vision_ground_ui_elements",
            "description": "Ground GUI elements with pixel coordinates and click action sequence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "elements": {"type": "array"},
                    "intent_fa": {"type": "string"},
                },
                "required": ["elements"],
            },
            "handler": vision_ground_ui_elements,
        },
        {
            "name": "vision_inspect_diagram",
            "description": "Inspect flowchart, Mermaid diagram, or SVG visual structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "diagram_format": {
                        "type": "string",
                        "enum": ["mermaid", "svg"],
                        "default": "mermaid",
                    },
                },
                "required": ["content"],
            },
            "handler": vision_inspect_diagram,
        },
        {
            "name": "vision_diff_visual_states",
            "description": "Detect visual state changes and spatial diffs between two frames.",
            "parameters": {
                "type": "object",
                "properties": {
                    "before_state": {"type": "array"},
                    "after_state": {"type": "array"},
                },
                "required": ["before_state", "after_state"],
            },
            "handler": vision_diff_visual_states,
        },
    ]
