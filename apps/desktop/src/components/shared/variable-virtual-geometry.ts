export interface VariableMeasurements {
  heights: number[];
  offsets: number[];
  total: number;
}

export interface VariableRange {
  start: number;
  end: number;
}

function indexAtOffset(offsets: readonly number[], value: number): number {
  let low = 0;
  let high = offsets.length - 1;
  while (low < high) {
    const middle = Math.floor((low + high + 1) / 2);
    if ((offsets[middle] ?? 0) <= value) low = middle;
    else high = middle - 1;
  }
  return low;
}

/** Computes logical row offsets from measured heights with an estimate fallback. */
export function variableMeasurements<T>(
  items: readonly T[],
  getKey: (item: T, index: number) => string | number,
  measuredHeights: ReadonlyMap<string | number, number>,
  estimatedItemSize: number,
): VariableMeasurements {
  const offsets = new Array<number>(items.length);
  const heights = new Array<number>(items.length);
  let total = 0;
  for (let index = 0; index < items.length; index += 1) {
    offsets[index] = total;
    const item = items[index];
    const height = measuredHeights.get(getKey(item, index)) ?? estimatedItemSize;
    heights[index] = height;
    total += height;
  }
  return { heights, offsets, total };
}

/** Finds the bounded overscanned range for a variable-height viewport. */
export function variableRange(
  offsets: readonly number[],
  itemCount: number,
  scrollTop: number,
  viewportSize: number,
  overscan: number,
): VariableRange {
  if (itemCount === 0) return { start: 0, end: 0 };
  const firstVisible = indexAtOffset(offsets, scrollTop);
  const lastVisible = indexAtOffset(offsets, scrollTop + viewportSize);
  return {
    start: Math.max(0, firstVisible - overscan),
    end: Math.min(itemCount, lastVisible + overscan + 1),
  };
}

/** Reader owns the scroll position after leaving this distance from the tail. */
export function isNearVirtualTail(
  scrollHeight: number,
  scrollTop: number,
  clientHeight: number,
  threshold = 64,
): boolean {
  return scrollHeight - scrollTop - clientHeight < threshold;
}
