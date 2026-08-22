/** Coalesces token writes to at most one store update per animation frame. */

export interface FrameBatcher {
  push: (value: string) => void;
  flush: () => void;
  cancel: () => void;
}

export function createFrameBatcher(write: (combined: string) => void): FrameBatcher {
  let pending = '';
  let frame: number | null = null;
  const schedule = (callback: FrameRequestCallback) =>
    typeof requestAnimationFrame === 'function'
      ? requestAnimationFrame(callback)
      : window.setTimeout(() => callback(performance.now()), 16);
  const unschedule = (id: number) => {
    if (typeof cancelAnimationFrame === 'function') cancelAnimationFrame(id);
    else window.clearTimeout(id);
  };

  const flush = () => {
    if (frame !== null) {
      unschedule(frame);
      frame = null;
    }
    if (!pending) return;
    const chunk = pending;
    pending = '';
    write(chunk);
  };

  return {
    push(value) {
      pending += value;
      if (frame !== null) return;
      frame = schedule(() => {
        frame = null;
        if (!pending) return;
        const chunk = pending;
        pending = '';
        write(chunk);
      });
    },
    flush,
    cancel() {
      if (frame !== null) unschedule(frame);
      frame = null;
      pending = '';
    },
  };
}
