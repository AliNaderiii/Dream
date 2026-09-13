"""``vision.*`` JSON-RPC bridge methods."""
from __future__ import annotations
import asyncio
import logging
from typing import Any
from dream.bridge.errors import invalid_params
from dream.vision.engine import get_vision_engine

logger = logging.getLogger("dream.bridge.vision")
__all__ = ["HANDLERS"]

def _params(params: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(params, dict):
        merged.update(params)
    merged.update(kwargs)
    return merged

async def vision_analyze_image(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    img_desc = data.get("image_descriptor") or "sample_screen.png"
    objects = data.get("objects")
    if objects is not None and not isinstance(objects, list):
        raise invalid_params("objects must be a list of object descriptors")
    engine = get_vision_engine()
    return await asyncio.to_thread(engine.analyze_image, image_descriptor=img_desc, detected_objects=objects)

async def vision_decompose_video(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    video_id = str(data.get("video_id", "demo_video")).strip() or "demo_video"
    duration_sec = float(data.get("duration_sec", 10.0))
    fps = float(data.get("fps", 30.0))
    engine = get_vision_engine()
    timeline = await asyncio.to_thread(engine.decompose_video, video_id=video_id, duration_sec=duration_sec, fps=fps)
    return timeline.to_dict()

async def vision_ground_ui_elements(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    elements = data.get("elements")
    if not isinstance(elements, list):
        elements = [
            {"element_id": "btn_submit", "label_fa": "دکمه ثبت نهایی", "element_type": "button", "box": {"ymin": 0.8, "xmin": 0.7, "ymax": 0.9, "xmax": 0.95}, "interactive": True},
            {"element_id": "input_search", "label_fa": "کادر جستجو", "element_type": "input_field", "box": {"ymin": 0.1, "xmin": 0.2, "ymax": 0.2, "xmax": 0.8}, "interactive": True},
        ]
    intent_fa = str(data.get("intent_fa", "")).strip()
    engine = get_vision_engine()
    return await asyncio.to_thread(engine.ground_ui_elements, elements_spec=elements, intent_fa=intent_fa)

async def vision_inspect_diagram(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    content = data.get("content") or "graph TD\n  A --> B"
    fmt = str(data.get("diagram_format", "mermaid")).strip()
    engine = get_vision_engine()
    return await asyncio.to_thread(engine.inspect_diagram, content=content.strip(), diagram_format=fmt)

async def vision_diff_visual_states(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    before = data.get("before_state") or []
    after = data.get("after_state") or []
    if not isinstance(before, list) or not isinstance(after, list):
        raise invalid_params("before_state and after_state must be lists")
    engine = get_vision_engine()
    diff = await asyncio.to_thread(engine.diff_visual_states, before_state=before, after_state=after)
    return diff.to_dict()

async def vision_get_metrics(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    engine = get_vision_engine()
    return await asyncio.to_thread(engine.get_metrics)

async def vision_reset(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    engine = get_vision_engine()
    await asyncio.to_thread(engine.reset)
    return {"status": "reset", "spatial_entities_in_memory": 0}

HANDLERS = {
    "vision.analyze_image": vision_analyze_image,
    "vision.decompose_video": vision_decompose_video,
    "vision.ground_ui_elements": vision_ground_ui_elements,
    "vision.inspect_diagram": vision_inspect_diagram,
    "vision.diff_visual_states": vision_diff_visual_states,
    "vision.get_metrics": vision_get_metrics,
    "vision.reset": vision_reset,
}
