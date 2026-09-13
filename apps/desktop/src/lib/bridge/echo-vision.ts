/** Fallback offline mock implementations for vision.* methods. */

import type {
  BoundingBox,
  UIElementGrounding,
  VideoTimeline,
  VisionMetricsResult,
  VisualDiffResult,
} from './vision';

let mockEntitiesCount = 4;
let mockAnalysesCount = 1;

export function resetEchoVision() {
  mockEntitiesCount = 0;
  mockAnalysesCount = 0;
}

export function echoVisionAnalyzeImage(
  _imageDescriptor = 'sample_screen.png',
  objects: Array<{ label_fa: string; box: BoundingBox; category?: string }> = [],
) {
  mockAnalysesCount += 1;
  const count = objects.length || 3;
  mockEntitiesCount += count;

  return {
    success: true,
    analysis_id: na-,
    total_objects_detected: count,
    objects: objects.length
      ? objects.map((o, idx) => ({
          entity_id: ent-,
          label_fa: o.label_fa,
          box: o.box,
        }))
      : [
          {
            entity_id: 'ent-1',
            label_fa: 'دکمه اقدام اصلی',
            box: { ymin: 0.1, xmin: 0.1, ymax: 0.2, xmax: 0.3 },
          },
        ],
    summary_fa: تحلیل تصویر با شناسایی  موجودیت بصری و ثبت در حافظه مکانی انجام شد.,
  };
}

export function echoVisionDecomposeVideo(
  videoId = 'demo_video',
  durationSec = 10.0,
  fps = 30.0,
): VideoTimeline {
  mockAnalysesCount += 1;
  return {
    video_id: videoId,
    duration_sec: durationSec,
    total_frames: Math.floor(durationSec * fps),
    sample_rate_fps: fps,
    scene_count: 2,
    keyframes: [
      {
        frame_id: 'kf_001',
        timestamp_sec: 0.5,
        frame_index: 15,
        scene_id: 1,
        entropy_score: 0.82,
        is_scene_transition: false,
        caption_fa: 'نمای آغازین و صفحه ورود داشبورد',
        detected_entities: ['لوگو', 'دکمه ورود'],
      },
    ],
    narrative_summary_fa: 'ویدیو شامل ۲ صحنه مجزا: آغاز با معرفی صفحه ورود و انتقال به داشبورد.',
  };
}

export function echoVisionGroundUIElements(elements?: UIElementGrounding[], intentFa = '') {
  mockAnalysesCount += 1;
  const defaultElements: UIElementGrounding[] = [
    {
      element_id: 'btn_confirm',
      label_fa: 'دکمه تایید نهایی',
      element_type: 'button',
      box: { ymin: 0.75, xmin: 0.65, ymax: 0.85, xmax: 0.9 },
      confidence: 0.98,
      interactive: true,
      suggested_action: 'click',
      click_target: { x: 0.775, y: 0.8 },
    },
  ];

  const resElements = elements && elements.length ? elements : defaultElements;
  const actions = intentFa ? [کلیک روی ] : [];

  return {
    success: true,
    total_elements: resElements.length,
    elements: resElements,
    proposed_actions: actions,
  };
}

export function echoVisionInspectDiagram(content: string, diagramFormat = 'mermaid') {
  mockAnalysesCount += 1;
  return {
    valid: true,
    diagram_type: diagramFormat,
    total_nodes: 3,
    total_edges: 2,
    has_persian_text: content.includes('فارسی') || content.includes('نمودار'),
    summary_fa: نمودار  با ۳ گره و ۲ اتصال شناسایی و اعتبارسنجی شد.,
  };
}

export function echoVisionDiffVisualStates(
  beforeState: Array<{ label_fa: string; box: BoundingBox }>,
  afterState: Array<{ label_fa: string; box: BoundingBox }>,
): VisualDiffResult {
  mockAnalysesCount += 1;
  const changed = beforeState.length !== afterState.length;
  return {
    diff_id: diff-,
    similarity_score: changed ? 0.75 : 1.0,
    has_significant_change: changed,
    added_elements: changed ? ['عنصر جدید شناسایی‌شده'] : [],
    removed_elements: [],
    modified_regions: changed ? [{ ymin: 0.5, xmin: 0.5, ymax: 0.6, xmax: 0.8 }] : [],
    summary_fa: changed
      ? 'تغییرات بصری معنادار در صفحه شناسایی شد.'
      : 'هیچ تغییر بصری محسوسی بین دو وضعیت یافت نشد.',
  };
}

export function echoVisionGetMetrics(): VisionMetricsResult {
  return {
    uptime_sec: 42.5,
    total_analyses_count: mockAnalysesCount,
    spatial_entities_in_memory: mockEntitiesCount,
    status: 'healthy',
  };
}

export function echoVisionReset() {
  resetEchoVision();
  return { status: 'reset', spatial_entities_in_memory: 0 };
}
