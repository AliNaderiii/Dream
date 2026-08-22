import { afterEach, describe, expect, it, vi } from 'vitest';

import { createFrameBatcher } from '@/lib/performance/frame-batcher';

afterEach(() => vi.restoreAllMocks());

describe('frame batcher', () => {
  it('coalesces any token count into one write per frame', () => {
    let callback: FrameRequestCallback | null = null;
    vi.stubGlobal('requestAnimationFrame', (next: FrameRequestCallback) => {
      callback = next;
      return 1;
    });
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    const write = vi.fn();
    const batcher = createFrameBatcher(write);

    const pushStarted = performance.now();
    for (let index = 0; index < 500; index += 1) batcher.push('x');
    const pushDuration = performance.now() - pushStarted;
    expect(write).not.toHaveBeenCalled();
    expect(callback).not.toBeNull();
    const flushStarted = performance.now();
    (callback as unknown as FrameRequestCallback)(16);
    const flushDuration = performance.now() - flushStarted;
    const longestTask = Math.max(pushDuration, flushDuration);
    console.info(
      `stream_fixture_tokens=500 writes=${write.mock.calls.length} longest_task_ms=${longestTask.toFixed(3)}`,
    );
    expect(longestTask).toBeLessThan(50);
    expect(write).toHaveBeenCalledTimes(1);
    expect(write).toHaveBeenCalledWith('x'.repeat(500));
  });

  it('can cancel pending output', () => {
    vi.stubGlobal('requestAnimationFrame', () => 7);
    const cancel = vi.fn();
    vi.stubGlobal('cancelAnimationFrame', cancel);
    const write = vi.fn();
    const batcher = createFrameBatcher(write);
    batcher.push('never rendered');
    batcher.cancel();
    batcher.flush();
    expect(cancel).toHaveBeenCalledWith(7);
    expect(write).not.toHaveBeenCalled();
  });
});
