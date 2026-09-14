import { beforeEach, describe, expect, it } from 'vitest';

import { getBridgeClient, resetBridgeClient, type BridgeClient } from './client';
import { resetEchoVision } from './echo-vision';
import {
  visionAnalyzeImage,
  visionDecomposeVideo,
  visionDiffVisualStates,
  visionGetMetrics,
  visionGroundUIElements,
  visionInspectDiagram,
  visionReset,
} from './vision';

describe('Vision Bridge Client', () => {
  let client: BridgeClient;

  beforeEach(() => {
    resetBridgeClient();
    resetEchoVision();
    client = getBridgeClient();
  });

  it('analyzes image and grounds objects', async () => {
    const res = await visionAnalyzeImage(client, 'dashboard.png', [
      {
        label_fa: 'دکمه ورود',
        box: { ymin: 0.2, xmin: 0.3, ymax: 0.4, xmax: 0.5 },
      },
    ]);
    expect(res.success).toBe(true);
    expect(res.total_objects_detected).toBe(1);
    expect(res.summary_fa).toContain('تحلیل تصویر');
  });

  it('decomposes video into keyframes and narrative timeline', async () => {
    const timeline = await visionDecomposeVideo(client, 'app_demo', 10.0, 30.0);
    expect(timeline.video_id).toBe('app_demo');
    expect(timeline.keyframes.length).toBeGreaterThanOrEqual(1);
    expect(timeline.narrative_summary_fa).toBeDefined();
  });

  it('grounds UI elements with click targets and proposed actions', async () => {
    const grounded = await visionGroundUIElements(client, undefined, 'کلیک روی تایید');
    expect(grounded.success).toBe(true);
    expect(grounded.total_elements).toBeGreaterThanOrEqual(1);
    expect(grounded.proposed_actions.length).toBeGreaterThanOrEqual(1);
  });

  it('inspects architectural diagrams', async () => {
    const diag = await visionInspectDiagram(client, 'graph TD\n  A --> B', 'mermaid');
    expect(diag.valid).toBe(true);
    expect(diag.total_nodes).toBeGreaterThanOrEqual(2);
  });

  it('diffs visual states and resets spatial memory', async () => {
    const before = [{ label_fa: 'A', box: { ymin: 0, xmin: 0, ymax: 1, xmax: 1 } }];
    const after = [
      { label_fa: 'A', box: { ymin: 0, xmin: 0, ymax: 1, xmax: 1 } },
      { label_fa: 'B', box: { ymin: 0.5, xmin: 0.5, ymax: 0.8, xmax: 0.8 } },
    ];
    const diff = await visionDiffVisualStates(client, before, after);
    expect(diff.has_significant_change).toBe(true);

    const reset = await visionReset(client);
    expect(reset.status).toBe('reset');

    const metrics = await visionGetMetrics(client);
    expect(metrics.status).toBe('healthy');
  });
});
