import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode, UIEvent } from 'react';

import { cn } from '@/utils/cn';

const DEFAULT_VIEWPORT_SIZE = 600;
const DEFAULT_OVERSCAN = 4;

interface VirtualListProps<T> {
  items: readonly T[];
  getKey: (item: T, index: number) => string | number;
  estimateSize: number | ((item: T, index: number) => number);
  renderItem: (item: T, index: number) => ReactNode;
  ariaLabel: string;
  className?: string;
  overscan?: number;
  virtualizeAt?: number;
  onEndReached?: () => void;
  /** Scroll to the tail when streaming output appends. */
  followOutput?: boolean;
}

interface Range {
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

/**
 * Dependency-free fixed/estimated-size virtualization for 100+ row desktop lists.
 * Row measurement is deliberately avoided so scrolling never creates a layout-read loop.
 */
export function VirtualList<T>({
  items,
  getKey,
  estimateSize,
  renderItem,
  ariaLabel,
  className,
  overscan = DEFAULT_OVERSCAN,
  virtualizeAt = 100,
  onEndReached,
  followOutput = false,
}: VirtualListProps<T>) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [scrollOffset, setScrollOffset] = useState(0);
  const [viewportSize, setViewportSize] = useState(DEFAULT_VIEWPORT_SIZE);

  const { offsets, sizes, totalSize } = useMemo(() => {
    const nextOffsets: number[] = [];
    const nextSizes: number[] = [];
    let total = 0;
    items.forEach((item, index) => {
      const size = typeof estimateSize === 'number' ? estimateSize : estimateSize(item, index);
      const safeSize = Math.max(1, size);
      nextOffsets.push(total);
      nextSizes.push(safeSize);
      total += safeSize;
    });
    return { offsets: nextOffsets, sizes: nextSizes, totalSize: total };
  }, [estimateSize, items]);

  useEffect(() => {
    const node = viewportRef.current;
    if (!node || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => {
      const size = entry?.contentRect.height;
      if (size && size > 0) setViewportSize(size);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const range =
    items.length < virtualizeAt
      ? { start: 0, end: items.length }
      : virtualRange(offsets, sizes, scrollOffset, viewportSize, overscan);

  useEffect(() => {
    if (onEndReached && items.length > 0 && range.end >= items.length) onEndReached();
  }, [items.length, onEndReached, range.end]);

  useEffect(() => {
    const node = viewportRef.current;
    if (!followOutput || !node) return;
    node.scrollTop = totalSize;
    setScrollOffset(totalSize);
  }, [followOutput, items.length, totalSize]);

  const onScroll = (event: UIEvent<HTMLDivElement>) => {
    setScrollOffset(event.currentTarget.scrollTop);
  };

  return (
    <div
      ref={viewportRef}
      onScroll={onScroll}
      data-virtualized={items.length >= virtualizeAt ? 'true' : 'false'}
      className={cn('min-h-0 overflow-y-auto', className)}
    >
      <div role="list" aria-label={ariaLabel} className="relative" style={{ height: totalSize }}>
        {items.slice(range.start, range.end).map((item, relativeIndex) => {
          const index = range.start + relativeIndex;
          return (
            <div
              key={getKey(item, index)}
              role="listitem"
              data-index={index}
              className="absolute inset-x-0"
              style={{ height: sizes[index], insetBlockStart: offsets[index] }}
            >
              {renderItem(item, index)}
            </div>
          );
        })}
      </div>
    </div>
  );
}
