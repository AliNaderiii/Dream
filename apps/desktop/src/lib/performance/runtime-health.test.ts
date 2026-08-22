import { afterEach, describe, expect, it, vi } from 'vitest';

import { createFrameBatcher } from '@/lib/performance/frame-batcher';

const pendingFrames: FrameRequestCallback[] = [];

afterEach(() => {
  pendingFrames.length = 0;
  vi.restoreAllMocks();
});

describe('streaming runtime health', () => {
  it('processes a 500-chunk stream, yields, and reports zero unhandled rejections', async () => {
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      pendingFrames.push(callback);
      return pendingFrames.length;
    });
    vi.stubGlobal('cancelAnimationFrame', vi.fn());

    const unhandled: unknown[] = [];
    const onWindowRejection = (event: PromiseRejectionEvent) => unhandled.push(event.reason);
    const onProcessRejection = (reason: unknown) => unhandled.push(reason);
    window.addEventListener('unhandledrejection', onWindowRejection);
    process.on('unhandledRejection', onProcessRejection);

    try {
      const rendered: string[] = [];
      const batcher = createFrameBatcher((chunk) => rendered.push(chunk));
      await Promise.all(
        Array.from({ length: 500 }, async () => {
          await Promise.resolve();
          batcher.push('token ');
        }),
      );

      expect(pendingFrames).toHaveLength(1);
      pendingFrames.shift()?.(performance.now());

      let eventLoopYielded = false;
      await new Promise<void>((resolve) => {
        window.setTimeout(() => {
          eventLoopYielded = true;
          resolve();
        }, 0);
      });

      expect(rendered).toEqual(['token '.repeat(500)]);
      expect(eventLoopYielded).toBe(true);
      expect(unhandled).toEqual([]);
      console.info('stream_runtime_chunks=500 event_loop_yielded=true unhandled_rejections=0');
    } finally {
      window.removeEventListener('unhandledrejection', onWindowRejection);
      process.off('unhandledRejection', onProcessRejection);
    }
  });
});
