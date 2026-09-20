/**
 * Virtual-list range geometry.
 *
 * Kept in a module without components so React Fast Refresh stays intact for
 * `virtual-list.tsx` (react-refresh/only-export-components).
 */

export interface Range {
  start: number;
  end: number;
}

/** Calculate a bounded visible range without reading row geometry. */
export function virtualRange(
  offsets: readonly number[],
  sizes: readonly number[],
  scrollOffset: number,
  viewportSize: number,
  overscan: number,
): Range {
  if (sizes.length === 0) return { start: 0, end: 0 };
  const viewportEnd = scrollOffset + viewportSize;
  let first = 0;
  while (first < sizes.length && offsets[first] + sizes[first] < scrollOffset) first += 1;
  let last = first;
  while (last < sizes.length && offsets[last] < viewportEnd) last += 1;
  return {
    start: Math.max(0, first - overscan),
    end: Math.min(sizes.length, last + overscan),
  };
}
