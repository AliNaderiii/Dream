"""Auto-sync script to ensure all Vision, Dialectic, and Bridge files are in place."""
from __future__ import annotations
import json
from pathlib import Path

# 1. dream/bridge/methods_vision.py
METHODS_VISION = '''"""``vision.*`` JSON-RPC bridge methods."""
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
    content = data.get("content") or "graph TD\\n  A --> B"
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
'''

# 2. apps/desktop/src/lib/bridge/vision.ts
VISION_TS = '''import type { BridgeClient } from './client';
import * as echo from './echo-vision';

export interface BoundingBox { ymin: number; xmin: number; ymax: number; xmax: number; center_x?: number; center_y?: number; width?: number; height?: number; }
export interface UIElementGrounding { element_id: string; label_fa: string; element_type: string; box: BoundingBox; confidence: number; interactive: boolean; suggested_action: string; text_content?: string; click_target: { x: number; y: number }; }
export interface KeyFrame { frame_id: string; timestamp_sec: number; frame_index: number; scene_id: number; entropy_score: number; is_scene_transition: boolean; caption_fa: string; detected_entities: string[]; }
export interface VideoTimeline { video_id: string; duration_sec: number; total_frames: number; sample_rate_fps: number; scene_count: number; keyframes: KeyFrame[]; narrative_summary_fa: string; }
export interface VisualDiffResult { diff_id: string; similarity_score: number; has_significant_change: boolean; added_elements: string[]; removed_elements: string[]; modified_regions: BoundingBox[]; summary_fa: string; }
export interface VisionMetricsResult { uptime_sec: number; total_analyses_count: number; spatial_entities_in_memory: number; status: string; }

function echoOr<T>(client: BridgeClient, local: () => T, method: string, params: Record<string, unknown>): Promise<T> {
  if (client.transportKind === 'echo') {
    try { return Promise.resolve(local()); }
    catch (error) { return Promise.reject(error instanceof Error ? error : new Error(String(error))); }
  }
  return client.call<T>(method, params);
}

export function visionAnalyzeImage(client: BridgeClient, imageDescriptor = 'sample_screen.png', objects: Array<{ label_fa: string; box: BoundingBox; category?: string }> = []) {
  return echoOr(client, () => echo.echoVisionAnalyzeImage(imageDescriptor, objects), 'vision.analyze_image', { image_descriptor: imageDescriptor, objects });
}
export function visionDecomposeVideo(client: BridgeClient, videoId = 'demo_video', durationSec = 10.0, fps = 30.0) {
  return echoOr(client, () => echo.echoVisionDecomposeVideo(videoId, durationSec, fps), 'vision.decompose_video', { video_id: videoId, duration_sec: durationSec, fps });
}
export function visionGroundUIElements(client: BridgeClient, elements?: UIElementGrounding[], intentFa = '') {
  return echoOr(client, () => echo.echoVisionGroundUIElements(elements, intentFa), 'vision.ground_ui_elements', { elements: elements ?? [], intent_fa: intentFa });
}
export function visionInspectDiagram(client: BridgeClient, content: string, diagramFormat = 'mermaid') {
  return echoOr(client, () => echo.echoVisionInspectDiagram(content, diagramFormat), 'vision.inspect_diagram', { content, diagram_format: diagramFormat });
}
export function visionDiffVisualStates(client: BridgeClient, beforeState: Array<{ label_fa: string; box: BoundingBox }>, afterState: Array<{ label_fa: string; box: BoundingBox }>) {
  return echoOr(client, () => echo.echoVisionDiffVisualStates(beforeState, afterState), 'vision.diff_visual_states', { before_state: beforeState, after_state: afterState });
}
export function visionGetMetrics(client: BridgeClient) {
  return echoOr(client, () => echo.echoVisionGetMetrics(), 'vision.get_metrics', {});
}
export function visionReset(client: BridgeClient) {
  return echoOr(client, () => echo.echoVisionReset(), 'vision.reset', {});
}
'''

# 3. apps/desktop/src/lib/bridge/echo-vision.ts
ECHO_VISION_TS = '''import type { BoundingBox, UIElementGrounding, VideoTimeline, VisionMetricsResult, VisualDiffResult } from './vision';
let mockEntitiesCount = 4;
let mockAnalysesCount = 1;
export function resetEchoVision() { mockEntitiesCount = 0; mockAnalysesCount = 0; }
export function echoVisionAnalyzeImage(_imageDescriptor = 'sample_screen.png', objects: Array<{ label_fa: string; box: BoundingBox; category?: string }> = []) {
  mockAnalysesCount += 1;
  const count = objects.length || 3;
  mockEntitiesCount += count;
  return { success: true, analysis_id: `ana-${Math.random().toString(16).slice(2, 8)}`, total_objects_detected: count, objects: objects.map((o, idx) => ({ entity_id: `ent-${idx + 1}`, label_fa: o.label_fa, box: o.box })), summary_fa: `تحلیل تصویر با شناسایی ${count} موجودیت بصری انجام شد.` };
}
export function echoVisionDecomposeVideo(videoId = 'demo_video', durationSec = 10.0, fps = 30.0): VideoTimeline {
  mockAnalysesCount += 1;
  return { video_id: videoId, duration_sec: durationSec, total_frames: Math.floor(durationSec * fps), sample_rate_fps: fps, scene_count: 2, keyframes: [{ frame_id: 'kf_001', timestamp_sec: 0.5, frame_index: 15, scene_id: 1, entropy_score: 0.82, is_scene_transition: false, caption_fa: 'نمای آغازین و صفحه ورود داشبورد', detected_entities: ['لوگو', 'دکمه ورود'] }], narrative_summary_fa: 'ویدیو شامل ۲ صحنه مجزا: آغاز با معرفی صفحه ورود و انتقال به داشبورد.' };
}
export function echoVisionGroundUIElements(elements?: UIElementGrounding[], intentFa = '') {
  mockAnalysesCount += 1;
  const defaultElements: UIElementGrounding[] = [{ element_id: 'btn_confirm', label_fa: 'دکمه تایید نهایی', element_type: 'button', box: { ymin: 0.75, xmin: 0.65, ymax: 0.85, xmax: 0.9 }, confidence: 0.98, interactive: true, suggested_action: 'click', click_target: { x: 0.775, y: 0.8 } }];
  const resElements = elements && elements.length ? elements : defaultElements;
  const actions = intentFa ? [`کلیک روی ${resElements[0].label_fa}`] : [];
  return { success: true, total_elements: resElements.length, elements: resElements, proposed_actions: actions };
}
export function echoVisionInspectDiagram(content: string, diagramFormat = 'mermaid') {
  mockAnalysesCount += 1;
  return { valid: true, diagram_type: diagramFormat, total_nodes: 3, total_edges: 2, has_persian_text: content.includes('فارسی') || content.includes('نمودار'), summary_fa: `نمودار ${diagramFormat} با ۳ گره و ۲ اتصال شناسایی شد.` };
}
export function echoVisionDiffVisualStates(beforeState: Array<{ label_fa: string; box: BoundingBox }>, afterState: Array<{ label_fa: string; box: BoundingBox }>): VisualDiffResult {
  mockAnalysesCount += 1;
  const changed = beforeState.length !== afterState.length;
  return { diff_id: `diff-${Math.random().toString(16).slice(2, 8)}`, similarity_score: changed ? 0.75 : 1.0, has_significant_change: changed, added_elements: changed ? ['عنصر جدید شناسایی‌شده'] : [], removed_elements: [], modified_regions: changed ? [{ ymin: 0.5, xmin: 0.5, ymax: 0.6, xmax: 0.8 }] : [], summary_fa: changed ? 'تغییرات بصری معنادار در صفحه شناسایی شد.' : 'هیچ تغییر بصری محسوسی بین دو وضعیت یافت نشد.' };
}
export function echoVisionGetMetrics(): VisionMetricsResult { return { uptime_sec: 42.5, total_analyses_count: mockAnalysesCount, spatial_entities_in_memory: mockEntitiesCount, status: 'healthy' }; }
export function echoVisionReset() { resetEchoVision(); return { status: 'reset', spatial_entities_in_memory: 0 }; }
'''

def main() -> None:
    root = Path(__file__).resolve().parent
    files = {
        root / "dream/bridge/methods_vision.py": METHODS_VISION,
        root / "apps/desktop/src/lib/bridge/vision.ts": VISION_TS,
        root / "apps/desktop/src/lib/bridge/echo-vision.ts": ECHO_VISION_TS,
    }
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")
        print(f"Synced: {path.relative_to(root)}")

    locales_dir = root / "apps/desktop/src/locales"
    en_vision = {
        "title": "Multi-Modal Vision & Screen Grounding Studio",
        "subtitle": "Real-time GUI grounding, spatial memory, and video decomposition.",
        "screenInspect": "Inspect Screen Elements",
        "inspecting": "Inspecting…",
        "intent": "Action Intent",
        "intentPlaceholder": "e.g. Click on submit button or search user",
        "groundAction": "Ground & Propose Action",
        "grounding": "Grounding…",
        "detectedElements": "Detected UI Elements & Click Targets",
        "videoTimeline": "Video Keyframes & Scene Decomposition",
        "decomposeVideo": "Decompose Video Stream",
        "decomposing": "Decomposing…",
        "diagramInspector": "Architectural Diagram Inspector",
        "inspectDiagram": "Inspect Diagram Structure",
        "reset": "Reset Spatial Memory",
        "clickTarget": "Target: ({{x}}, {{y}})",
        "confidence": "Conf: {{conf}}%",
        "noElements": "No UI elements grounded yet. Click inspect above.",
        "noKeyframes": "No video keyframes extracted. Run stream decomposition above.",
    }
    fa_vision = {
        "title": "استودیوی بینایی ماشین و ردیابی بصری صفحه (Vision Studio)",
        "subtitle": "ردیابی المان‌های تعاملی صفحه، حافظه مکانی و تجزیه سکانس‌های ویدیو.",
        "screenInspect": "اسکن المان‌های صفحه",
        "inspecting": "در حال اسکن…",
        "intent": "قصد یا اقدام مورد نظر",
        "intentPlaceholder": "مثلاً کلیک روی دکمه ثبت نهایی یا جستجو",
        "groundAction": "ردیابی و پیشنهاد اقدام",
        "grounding": "در حال پردازش…",
        "detectedElements": "المان‌های تعاملی و اهداف کلیک شناسایی‌شده",
        "videoTimeline": "کی‌فریم‌ها و تجزیه صحنه‌های ویدیو",
        "decomposeVideo": "تجزیه ویدیوی استریم",
        "decomposing": "در حال تجزیه…",
        "diagramInspector": "تحلیل‌گر دیاگرام‌های معماری",
        "inspectDiagram": "تحلیل ساختار دیاگرام",
        "reset": "پاکسازی حافظه مکانی",
        "clickTarget": "مختصات هدف: ({{x}}, {{y}})",
        "confidence": "اطمینان: {{conf}}٪",
        "noElements": "هنوز المانی ردیابی نشده است. روی اسکن المان‌ها کلیک کنید.",
        "noKeyframes": "هنوز فریم کلیدی استخراج نشده است. تجزیه ویدیو را اجرا کنید.",
    }
    for loc in ["en", "fa", "de", "es", "fr", "ja", "ko", "zh-CN"]:
        p = locales_dir / loc / "live.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            data["vision"] = fa_vision if loc == "fa" else en_vision
            p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Synced locale: {p.relative_to(root)}")

    print("\nAll files synchronized successfully!")

if __name__ == "__main__":
    main()
