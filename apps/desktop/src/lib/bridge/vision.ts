import type { BridgeClient } from './client';
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
