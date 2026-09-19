/** Typed client wrappers for vision.* JSON-RPC methods. */

import type { BridgeClient } from './client';
import * as echo from './echo-vision';
import type { OcrExtractResult } from './ocr';

export interface BoundingBox {
  ymin: number;
  xmin: number;
  ymax: number;
  xmax: number;
  center_x?: number;
  center_y?: number;
  width?: number;
  height?: number;
}

export interface UIElementGrounding {
  element_id: string;
  label_fa: string;
  element_type: string;
  box: BoundingBox;
  confidence: number;
  interactive: boolean;
  suggested_action: string;
  text_content?: string;
  click_target: { x: number; y: number };
}

export interface KeyFrame {
  frame_id: string;
  timestamp_sec: number;
  frame_index: number;
  scene_id: number;
  entropy_score: number;
  is_scene_transition: boolean;
  caption_fa: string;
  detected_entities: string[];
}

export interface VideoTimeline {
  video_id: string;
  duration_sec: number;
  total_frames: number;
  sample_rate_fps: number;
  scene_count: number;
  keyframes: KeyFrame[];
  narrative_summary_fa: string;
}

export interface VisualDiffResult {
  diff_id: string;
  similarity_score: number;
  has_significant_change: boolean;
  added_elements: string[];
  removed_elements: string[];
  modified_regions: BoundingBox[];
  summary_fa: string;
}

export interface VisionMetricsResult {
  uptime_sec: number;
  total_analyses_count: number;
  spatial_entities_in_memory: number;
  status: string;
}

function echoOr<T>(
  client: BridgeClient,
  local: () => T,
  method: string,
  params: Record<string, unknown>,
): Promise<T> {
  if (client.transportKind === 'echo') {
    try {
      return Promise.resolve(local());
    } catch (error) {
      return Promise.reject(error instanceof Error ? error : new Error(String(error)));
    }
  }
  return client.call<T>(method, params);
}

export function visionAnalyzeImage(
  client: BridgeClient,
  imageDescriptor = 'sample_screen.png',
  objects: Array<{ label_fa: string; box: BoundingBox; category?: string }> = [],
): Promise<{
  success: boolean;
  analysis_id: string;
  total_objects_detected: number;
  objects: Array<{ entity_id: string; label_fa: string; box: BoundingBox }>;
  summary_fa: string;
}> {
  return echoOr(
    client,
    () => echo.echoVisionAnalyzeImage(imageDescriptor, objects),
    'vision.analyze_image',
    { image_descriptor: imageDescriptor, objects },
  );
}

export function visionDecomposeVideo(
  client: BridgeClient,
  videoId = 'demo_video',
  durationSec = 10.0,
  fps = 30.0,
): Promise<VideoTimeline> {
  return echoOr(
    client,
    () => echo.echoVisionDecomposeVideo(videoId, durationSec, fps),
    'vision.decompose_video',
    { video_id: videoId, duration_sec: durationSec, fps },
  );
}

export function visionGroundUIElements(
  client: BridgeClient,
  elements?: UIElementGrounding[],
  intentFa = '',
): Promise<{
  success: boolean;
  total_elements: number;
  elements: UIElementGrounding[];
  proposed_actions: string[];
}> {
  return echoOr(
    client,
    () => echo.echoVisionGroundUIElements(elements, intentFa),
    'vision.ground_ui_elements',
    { elements: elements ?? [], intent_fa: intentFa },
  );
}

export function visionInspectDiagram(
  client: BridgeClient,
  content: string,
  diagramFormat = 'mermaid',
): Promise<{
  valid: boolean;
  diagram_type?: string;
  total_nodes?: number;
  total_edges?: number;
  has_persian_text?: boolean;
  summary_fa: string;
}> {
  return echoOr(
    client,
    () => echo.echoVisionInspectDiagram(content, diagramFormat),
    'vision.inspect_diagram',
    { content, diagram_format: diagramFormat },
  );
}

export function visionDiffVisualStates(
  client: BridgeClient,
  beforeState: Array<{ label_fa: string; box: BoundingBox }>,
  afterState: Array<{ label_fa: string; box: BoundingBox }>,
): Promise<VisualDiffResult> {
  return echoOr(
    client,
    () => echo.echoVisionDiffVisualStates(beforeState, afterState),
    'vision.diff_visual_states',
    { before_state: beforeState, after_state: afterState },
  );
}

export function visionGetMetrics(client: BridgeClient): Promise<VisionMetricsResult> {
  return echoOr(client, () => echo.echoVisionGetMetrics(), 'vision.get_metrics', {});
}

export function visionReset(
  client: BridgeClient,
): Promise<{ status: string; spatial_entities_in_memory: number }> {
  return echoOr(client, () => echo.echoVisionReset(), 'vision.reset', {});
}

/** Metadata about a real screen capture (v4.5) — the temp file is always deleted. */
export interface ScreenCaptureInfo {
  backend: string;
  width: number;
  height: number;
  size_bytes: number;
  temp_deleted: boolean;
}

/** Result of `vision.capture_screen`: OCR of a real, immediately-deleted screenshot. */
export type VisionCaptureResult = OcrExtractResult & { screen?: ScreenCaptureInfo | null };

/**
 * Capture the real screen and OCR it (desktop: GDI/screencapture → core OCR,
 * temp file deleted immediately). Under the echo transport the result is a
 * clearly-flagged deterministic demo.
 */
export function visionCaptureScreen(
  client: BridgeClient,
  documentType = 'general',
): Promise<VisionCaptureResult> {
  return echoOr(client, () => echo.echoVisionCaptureScreen(documentType), 'vision.capture_screen', {
    document_type: documentType,
  });
}
