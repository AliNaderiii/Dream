/**
 * Chronological timeline of memories.
 *
 * Rows are grouped into buckets whose granularity follows the zoom control
 * (day / week / month). The bucket list doubles as scroll-to-date navigation:
 * picking a bucket scrolls its section into view.
 */

import { useMemo, useRef } from 'react';

import { KindBadge, KIND_COLOR } from '@/components/memory/kind-badge';
import { ImportanceStars } from '@/components/memory/importance-stars';
import { Button } from '@/components/ui/button';
import { sanitizeMemoryText, toStars } from '@/lib/bridge/memory';
import type { BridgeMemory } from '@/lib/bridge/types';
import { cn } from '@/utils/cn';
import { bucketKey, bucketLabel, relativeTime, type TimelineZoom } from '@/utils/time';

const ZOOMS: TimelineZoom[] = ['day', 'week', 'month'];

interface MemoryTimelineProps {
  memories: BridgeMemory[];
  zoom: TimelineZoom;
  onZoomChange: (zoom: TimelineZoom) => void;
  onSelect: (memory: BridgeMemory) => void;
  selectedId?: number | null;
}

export function MemoryTimeline({
  memories,
  zoom,
  onZoomChange,
  onSelect,
  selectedId,
}: MemoryTimelineProps) {
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});

  const groups = useMemo(() => {
    const byBucket = new Map<string, BridgeMemory[]>();
    for (const memory of [...memories].sort((a, b) => b.created_at - a.created_at)) {
      const key = bucketKey(memory.created_at, zoom);
      const list = byBucket.get(key);
      if (list) list.push(memory);
      else byBucket.set(key, [memory]);
    }
    return [...byBucket.entries()];
  }, [memories, zoom]);

  const scrollTo = (key: string) => {
    sectionRefs.current[key]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="flex h-full min-h-0">
      <nav
        aria-label="Jump to date"
        className="hidden w-52 shrink-0 overflow-y-auto border-e border-border-default bg-surface p-2 lg:block"
      >
        <p className="px-2 pb-1 text-micro font-semibold uppercase text-fg-muted">Jump to</p>
        <ul className="flex flex-col gap-0.5">
          {groups.map(([key, items]) => (
            <li key={key}>
              <button
                type="button"
                onClick={() => scrollTo(key)}
                className="flex w-full items-center justify-between gap-2 rounded-sm px-2 py-1 text-start text-caption text-fg-secondary hover:bg-surface-2 hover:text-fg-primary"
              >
                <span className="truncate">{bucketLabel(key, zoom)}</span>
                <span className="tabular shrink-0 text-micro text-fg-muted">{items.length}</span>
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-border-default px-4 py-2">
          <span className="text-caption text-fg-secondary">Zoom</span>
          <div className="flex gap-1" role="group" aria-label="Timeline zoom">
            {ZOOMS.map((option) => (
              <Button
                key={option}
                size="sm"
                variant={zoom === option ? 'primary' : 'secondary'}
                aria-pressed={zoom === option}
                onClick={() => onZoomChange(option)}
              >
                {option}
              </Button>
            ))}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          {groups.length === 0 && (
            <p className="py-8 text-center text-body text-fg-muted">
              No memories match these filters.
            </p>
          )}
          {groups.map(([key, items]) => (
            <section
              key={key}
              ref={(node) => {
                sectionRefs.current[key] = node;
              }}
              aria-label={bucketLabel(key, zoom)}
              className="scroll-mt-2 pb-4"
            >
              <h3 className="sticky top-0 z-10 bg-canvas/95 py-1 text-caption font-semibold text-fg-secondary backdrop-blur">
                {bucketLabel(key, zoom)}
              </h3>
              <ol className="relative ms-2 border-s border-border-default ps-4">
                {items.map((memory) => (
                  <li key={memory.id} className="relative py-2">
                    <span
                      aria-hidden
                      className="absolute -start-5 top-4 size-2.5 rounded-full border-2 border-canvas"
                      style={{ backgroundColor: KIND_COLOR[memory.kind] ?? 'var(--color-chart-8)' }}
                    />
                    <button
                      type="button"
                      onClick={() => onSelect(memory)}
                      aria-current={selectedId === memory.id ? 'true' : undefined}
                      className={cn(
                        'flex w-full flex-col gap-1.5 rounded-md border p-2.5 text-start transition-colors duration-fast',
                        selectedId === memory.id
                          ? 'border-accent bg-accent-soft'
                          : 'border-border-default bg-surface hover:bg-surface-2',
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <KindBadge kind={memory.kind} />
                        <span className="ms-auto text-micro text-fg-muted">
                          {relativeTime(memory.created_at)}
                        </span>
                      </div>
                      <p className="line-clamp-2 whitespace-pre-wrap break-words text-body">
                        {sanitizeMemoryText(memory.content)}
                      </p>
                      <ImportanceStars value={toStars(memory.importance)} compact />
                    </button>
                  </li>
                ))}
              </ol>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
