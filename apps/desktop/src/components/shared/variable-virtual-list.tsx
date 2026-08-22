import {
  type CSSProperties,
  type ReactNode,
  type RefObject,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import {
  isNearVirtualTail,
  variableMeasurements,
  variableRange,
} from '@/components/shared/variable-virtual-geometry';

interface VariableVirtualListProps<T> {
  items: readonly T[];
  getKey: (item: T, index: number) => string | number;
  renderItem: (item: T, index: number) => ReactNode;
  estimatedItemSize: number;
  viewportSize?: number;
  overscan?: number;
  threshold?: number;
  tailFollow?: boolean;
  className?: string;
  ariaLabel?: string;
  listRef?: RefObject<HTMLDivElement | null>;
  footer?: ReactNode;
  onScroll?: () => void;
}

export function VariableVirtualList<T>({
  items,
  getKey,
  renderItem,
  estimatedItemSize,
  viewportSize: fallbackViewportSize = 640,
  overscan = 6,
  threshold = 100,
  tailFollow = false,
  className,
  ariaLabel,
  listRef,
  footer,
  onScroll,
}: VariableVirtualListProps<T>) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [measuredHeights, setMeasuredHeights] = useState(() => new Map<string | number, number>());
  const [viewportSize, setViewportSize] = useState(fallbackViewportSize);
  const [scrollTop, setScrollTop] = useState(() =>
    tailFollow ? Math.max(0, items.length * estimatedItemSize - fallbackViewportSize) : 0,
  );
  const previousLength = useRef(items.length);
  const stickyTail = useRef(tailFollow);
  const shouldVirtualize = items.length >= threshold;

  const setViewportRef = useCallback(
    (node: HTMLDivElement | null) => {
      viewportRef.current = node;
      if (listRef) listRef.current = node;
    },
    [listRef],
  );

  const measurements = useMemo(
    () => variableMeasurements(items, getKey, measuredHeights, estimatedItemSize),
    [estimatedItemSize, getKey, items, measuredHeights],
  );
  const range = shouldVirtualize
    ? variableRange(measurements.offsets, items.length, scrollTop, viewportSize, overscan)
    : { start: 0, end: items.length };

  const measureRow = useCallback((key: string | number, node: HTMLDivElement | null) => {
    if (!node) return;
    const measured = node.getBoundingClientRect().height || node.offsetHeight;
    if (measured <= 0) return;
    setMeasuredHeights((current) => {
      if (current.get(key) === measured) return current;
      const next = new Map(current);
      next.set(key, measured);
      return next;
    });
  }, []);

  useEffect(() => {
    const node = viewportRef.current;
    if (!node || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => {
      const nextSize = entry?.contentRect.height;
      if (nextSize && nextSize > 0) setViewportSize(nextSize);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useLayoutEffect(() => {
    if (!tailFollow || !stickyTail.current || items.length <= previousLength.current) {
      previousLength.current = items.length;
      return;
    }
    const node = viewportRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
      setScrollTop(node.scrollTop);
    }
    previousLength.current = items.length;
  }, [items.length, tailFollow]);

  const rowStyle = (index: number): CSSProperties | undefined =>
    shouldVirtualize
      ? {
          position: 'absolute',
          insetBlockStart: measurements.offsets[index],
          insetInline: 0,
          minBlockSize: measurements.heights[index],
        }
      : undefined;

  return (
    <div
      ref={setViewportRef}
      className={className}
      role="feed"
      aria-label={ariaLabel}
      aria-busy={false}
      onScroll={(event) => {
        const node = event.currentTarget;
        setScrollTop(node.scrollTop);
        stickyTail.current =
          tailFollow && isNearVirtualTail(node.scrollHeight, node.scrollTop, node.clientHeight);
        onScroll?.();
      }}
    >
      <div
        className="relative w-full"
        style={shouldVirtualize ? { blockSize: measurements.total } : undefined}
      >
        {items.slice(range.start, range.end).map((item, visibleIndex) => {
          const index = range.start + visibleIndex;
          const key = getKey(item, index);
          return (
            <div
              key={key}
              ref={(node) => measureRow(key, node)}
              style={rowStyle(index)}
              data-virtual-index={index}
            >
              {renderItem(item, index)}
            </div>
          );
        })}
      </div>
      {footer}
    </div>
  );
}
