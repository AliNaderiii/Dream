"""``vision.*`` JSON-RPC bridge methods.

Discovered automatically by :mod:`dream.bridge.extensions`.
Exposes the Multi-Modal Vision & Video Stream Reasoning Subsystem:

================================  ================================================
``vision.analyze_image``          Perform visual perception and spatial grounding
``vision.decompose_video``        Extract keyframes, detect scenes, build narrative
``vision.ground_ui_elements``     Ground interactive GUI elements and click targets
``vision.inspect_diagram``        Inspect architectural diagrams and SVG trees
``vision.diff_visual_states``     Compute visual differences between screen states
``vision.capture_screen``         Capture the real screen and OCR it (v4.5)
``vision.get_metrics``            Retrieve operational telemetry for vision subsystem
``vision.reset``                  Clear spatial memory and caches
================================  ================================================
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from dream.bridge.errors import invalid_params
from dream.ocr.tools import ocr_extract_document
from dream.vision.capture import (
    ScreenCaptureError,
    capture_extension,
    capture_screen_to_file,
)
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
    """Analyze image and ground objects. Params: ``image_descriptor``, ``objects``."""
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
    """Decompose video into timeline. Params: ``video_id``, ``duration_sec``, ``fps``."""
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
    """Ground GUI elements. Params: ``elements``, optional ``intent_fa``."""
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
    """Inspect diagram source or SVG. Params: ``content``, ``diagram_format``."""
    data = _params(params, kwargs)
    content = data.get("content")
    if content is not None and not isinstance(content, str):
        raise invalid_params("content must be a string")
    content = content or "graph TD\n  A --> B"

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
    """Diff two visual screen states. Params: ``before_state``, ``after_state``."""
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


async def vision_capture_screen(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Capture the real screen and OCR it. Params: optional ``document_type``.

    Privacy (P-14): the screenshot is written to a temp file, fed to the core
    OCR engine, and deleted immediately — screen pixels never persist on disk
    and the temp path is never returned or logged.
    """
    data = _params(params, kwargs)
    document_type = data.get("document_type", "general")
    if not isinstance(document_type, str) or not document_type.strip():
        raise invalid_params("document_type must be a non-empty string")
    if len(document_type) > 64:
        raise invalid_params("document_type must be at most 64 characters")

    def _capture_and_extract() -> dict[str, Any]:
        fd, name = tempfile.mkstemp(prefix="dream-scan-", suffix=capture_extension())
        os.close(fd)
        path = Path(name)
        try:
            info = capture_screen_to_file(path)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        try:
            result = ocr_extract_document(str(path), document_type.strip())
        finally:
            path.unlink(missing_ok=True)
        if isinstance(result, dict):
            # The temp path must never leak to the client (privacy).
            result["file_path"] = "<screen-capture>"
            return {**result, "screen": {**info, "temp_deleted": True}}
        return result

    try:
        return await asyncio.to_thread(_capture_and_extract)
    except ScreenCaptureError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:  # defensive: capture failures must not crash the bridge
        logger.warning("vision.capture_screen failed: %s", exc)
        return {"success": False, "error": f"screen capture failed: {exc}"}


async def vision_get_metrics(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Retrieve vision telemetry metrics."""
    engine = get_vision_engine()
    res = await asyncio.to_thread(engine.get_metrics)
    return res


async def vision_reset(params: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Reset vision state and spatial memory."""
    engine = get_vision_engine()
    await asyncio.to_thread(engine.reset)
    return {"status": "reset", "spatial_entities_in_memory": 0}


HANDLERS = {
    "vision.analyze_image": vision_analyze_image,
    "vision.decompose_video": vision_decompose_video,
    "vision.ground_ui_elements": vision_ground_ui_elements,
    "vision.inspect_diagram": vision_inspect_diagram,
    "vision.diff_visual_states": vision_diff_visual_states,
    "vision.capture_screen": vision_capture_screen,
    "vision.get_metrics": vision_get_metrics,
    "vision.reset": vision_reset,
}
