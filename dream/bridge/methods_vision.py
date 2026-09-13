"""`vision.*` JSON-RPC bridge methods."""

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
    img_desc = data.get("image_descriptor")
    if img_desc is not None and not isinstance(img_desc, str):
        raise invalid_params("image_descriptor must be a string")
    img_desc = img_desc or "sample_screen.png"

    objects = data.get("objects")
    if objects is not None:
        if not isinstance(objects, list) or not all(isinstance(o, dict) for o in objects):
            raise invalid_params("objects must be a list of object descriptors")

    engine = get_vision_engine()
    res = await asyncio.to_thread(
        engine.analyze_image,
        image_descriptor=img_desc,
        detected_objects=objects,
    )
    return res


async def vision_decompose_video(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    video_id = data.get("video_id")
    if video_id is not None and not isinstance(video_id, str):
        raise invalid_params("video_id must be a string")
    video_id = video_id or "demo_video"

    duration_sec = data.get("duration_sec", 10.0)
    if not isinstance(duration_sec, (int, float)) or isinstance(duration_sec, bool):
        raise invalid_params("duration_sec must be a number")

    fps = data.get("fps", 30.0)
    if not isinstance(fps, (int, float)) or isinstance(fps, bool):
        raise invalid_params("fps must be a number")

    engine = get_vision_engine()
    timeline = await asyncio.to_thread(
        engine.decompose_video,
        video_id=video_id,
        duration_sec=float(duration_sec),
        fps=float(fps),
    )
    return timeline.to_dict()


async def vision_ground_ui_elements(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    elements = data.get("elements")
    if elements is not None:
        if not isinstance(elements, list) or not all(isinstance(e, dict) for e in elements):
            raise invalid_params("elements must be a list of element dicts")

    if elements is None:
        elements = [
            {
                "element_id": "btn_submit",
                "label_fa": "دکمه ثبت نهایی",
                "element_type": "button",
                "box": {"ymin": 0.8, "xmin": 0.7, "ymax": 0.9, "xmax": 0.95},
                "interactive": True,
            },
            {
                "element_id": "input_search",
                "label_fa": "کادر جستجو",
                "element_type": "input_field",
                "box": {"ymin": 0.1, "xmin": 0.2, "ymax": 0.2, "xmax": 0.8},
                "interactive": True,
            },
        ]

    intent_fa = data.get("intent_fa", "")
    if intent_fa is not None and not isinstance(intent_fa, str):
        raise invalid_params("intent_fa must be a string")
    intent_fa = (intent_fa or "").strip()

    engine = get_vision_engine()
    res = await asyncio.to_thread(
        engine.ground_ui_elements,
        elements_spec=elements,
        intent_fa=intent_fa,
    )
    return res


async def vision_inspect_diagram(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    content = data.get("content")
    if content is not None and not isinstance(content, str):
        raise invalid_params("content must be a string")
    content = content or "graph TD
  A --> B"

    fmt = data.get("diagram_format", "mermaid")
    if fmt is not None and not isinstance(fmt, str):
        raise invalid_params("diagram_format must be a string")
    fmt = fmt or "mermaid"

    engine = get_vision_engine()
    res = await asyncio.to_thread(
        engine.inspect_diagram,
        content=content.strip(),
        diagram_format=fmt.strip(),
    )
    return res


async def vision_diff_visual_states(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    data = _params(params, kwargs)
    before = data.get("before_state")
    after = data.get("after_state")
    if before is not None:
        if not isinstance(before, list) or not all(isinstance(e, dict) for e in before):
            raise invalid_params("before_state must be a list of state dicts")
    if after is not None:
        if not isinstance(after, list) or not all(isinstance(e, dict) for e in after):
            raise invalid_params("after_state must be a list of state dicts")

    before = before or []
    after = after or []

    engine = get_vision_engine()
    diff = await asyncio.to_thread(
        engine.diff_visual_states,
        before_state=before,
        after_state=after,
    )
    return diff.to_dict()


async def vision_get_metrics(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    engine = get_vision_engine()
    res = await asyncio.to_thread(engine.get_metrics)
    return res


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
