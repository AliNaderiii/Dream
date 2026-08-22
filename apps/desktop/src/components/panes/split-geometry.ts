const KEYBOARD_STEP = 0.05;

/** Convert a physical pointer coordinate to the first logical pane's ratio. */
export function splitRatioFromPointer(
  rect: Pick<DOMRect, 'left' | 'right' | 'top' | 'width' | 'height'>,
  horizontal: boolean,
  clientX: number,
  clientY: number,
  rtl: boolean,
): number {
  if (!horizontal) return (clientY - rect.top) / rect.height;
  return rtl ? (rect.right - clientX) / rect.width : (clientX - rect.left) / rect.width;
}

/** Move a separator physically while preserving logical first/second pane order in RTL. */
export function splitRatioFromKey(
  ratio: number,
  key: string,
  horizontal: boolean,
  rtl: boolean,
): number | null {
  if (key === 'Home') return 0.1;
  if (key === 'End') return 0.9;
  if (horizontal && key === 'ArrowLeft') return ratio + (rtl ? KEYBOARD_STEP : -KEYBOARD_STEP);
  if (horizontal && key === 'ArrowRight') return ratio + (rtl ? -KEYBOARD_STEP : KEYBOARD_STEP);
  if (!horizontal && key === 'ArrowUp') return ratio - KEYBOARD_STEP;
  if (!horizontal && key === 'ArrowDown') return ratio + KEYBOARD_STEP;
  return null;
}
