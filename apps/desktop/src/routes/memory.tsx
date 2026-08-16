/**
 * Memory explorer.
 *
 * Filters live in one piece of state shared by the list and timeline views, so
 * switching views never loses context. The list pages with the cursor the
 * bridge returns; the timeline renders whatever has been loaded so far and
 * groups it by day, week or month.
 */

import { Database } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { MemoryCard } from '@/components/memory/memory-card';
import { MemoryDrawer, type MemoryDraft } from '@/components/memory/memory-drawer';
import { MemoryTimeline } from '@/components/memory/memory-timeline';
import {
  DEFAULT_FILTERS,
  MemoryToolbar,
  type MemoryFilters,
} from '@/components/memory/memory-toolbar';
import { EmptyState } from '@/components/shared/empty-state';
import { Button } from '@/components/ui/button';
import { useDebouncedValue } from '@/hooks/use-debounced-value';
import { useBridge } from '@/lib/bridge/hooks';
import {
  countMemories,
  createMemory,
  deleteMemory,
  listMemories,
  toImportance,
  updateMemory,
} from '@/lib/bridge/memory';
import type { BridgeMemory, MemoryListParams } from '@/lib/bridge/types';
import { dateInputToSeconds, type TimelineZoom } from '@/utils/time';

const PAGE_SIZE = 25;

export function MemoryRoute() {
  const { client } = useBridge();

  const [filters, setFilters] = useState<MemoryFilters>(DEFAULT_FILTERS);
  const [view, setView] = useState<'list' | 'timeline'>('list');
  const [zoom, setZoom] = useState<TimelineZoom>('day');

  const [memories, setMemories] = useState<BridgeMemory[]>([]);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [countTotal, setCountTotal] = useState(0);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drawerError, setDrawerError] = useState<string | null>(null);
  const [selected, setSelected] = useState<BridgeMemory | 'new' | null>(null);

  const debouncedSearch = useDebouncedValue(filters.search, 300);
  const debouncedStars = useDebouncedValue(filters.minStars, 300);

  const query = useMemo<MemoryListParams>(
    () => ({
      limit: PAGE_SIZE,
      kind_filter: filters.kind === 'all' ? null : filters.kind,
      search_query: debouncedSearch.trim() || null,
      date_from: dateInputToSeconds(filters.dateFrom),
      date_to: dateInputToSeconds(filters.dateTo, true),
      min_importance: debouncedStars > 0 ? toImportance(debouncedStars) : null,
      sort_by: filters.sort,
    }),
    [filters.kind, filters.dateFrom, filters.dateTo, filters.sort, debouncedSearch, debouncedStars],
  );

  const refreshCounts = useCallback(async () => {
    try {
      const result = await countMemories(client);
      setCounts(result.by_kind ?? {});
      setCountTotal(result.total ?? 0);
    } catch {
      // Counts are decorative; a failure must not blank the list.
    }
  }, [client]);

  // Reload the first page whenever a filter settles. State updates happen in
  // the promise callbacks, never synchronously in the effect body.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const page = await listMemories(client, query);
        if (cancelled) return;
        setMemories(page.memories);
        setTotal(page.total);
        setCursor(page.next_cursor);
        setHasMore(page.has_more);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load memories.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [client, query]);

  useEffect(() => {
    const load = async () => {
      await refreshCounts();
    };
    void load();
  }, [refreshCounts]);

  const loadMore = useCallback(async () => {
    if (!hasMore || loadingMore || cursor === null) return;
    setLoadingMore(true);
    try {
      const page = await listMemories(client, { ...query, cursor });
      setMemories((prev) => [...prev, ...page.memories]);
      setCursor(page.next_cursor);
      setHasMore(page.has_more);
      setTotal(page.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load more memories.');
    } finally {
      setLoadingMore(false);
    }
  }, [client, cursor, hasMore, loadingMore, query]);

  // Infinite scroll: a sentinel below the last card triggers the next page.
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || view !== 'list' || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) void loadMore();
      },
      { rootMargin: '200px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [loadMore, view]);

  const reload = useCallback(async () => {
    const page = await listMemories(client, query);
    setMemories(page.memories);
    setTotal(page.total);
    setCursor(page.next_cursor);
    setHasMore(page.has_more);
    await refreshCounts();
  }, [client, query, refreshCounts]);

  const handleSave = async (draft: MemoryDraft, record: BridgeMemory | null) => {
    setDrawerError(null);
    try {
      if (record) {
        await updateMemory(client, record.id, {
          content: draft.content,
          kind: draft.kind,
          stars: draft.stars,
        });
      } else {
        await createMemory(client, {
          content: draft.content,
          kind: draft.kind,
          stars: draft.stars,
        });
      }
      setSelected(null);
      await reload();
    } catch (err) {
      setDrawerError(err instanceof Error ? err.message : 'Could not save this memory.');
    }
  };

  const handleDelete = async (record: BridgeMemory) => {
    setDrawerError(null);
    try {
      await deleteMemory(client, record.id);
      setSelected(null);
      await reload();
    } catch (err) {
      setDrawerError(err instanceof Error ? err.message : 'Could not delete this memory.');
    }
  };

  const selectedId = selected && selected !== 'new' ? selected.id : null;

  return (
    <section aria-label="Memory explorer" className="flex h-full min-h-0 flex-col">
      <MemoryToolbar
        filters={filters}
        onChange={(patch) => setFilters((prev) => ({ ...prev, ...patch }))}
        counts={counts}
        total={countTotal}
        view={view}
        onViewChange={setView}
        onCreate={() => {
          setDrawerError(null);
          setSelected('new');
        }}
      />

      <p aria-live="polite" className="sr-only">
        {loading ? 'Loading memories' : `${memories.length} of ${total} memories shown`}
      </p>

      {error && (
        <p
          role="alert"
          className="border-b border-danger-fg bg-danger-bg px-4 py-2 text-caption text-danger-fg"
        >
          {error}
        </p>
      )}

      <div className="min-h-0 flex-1">
        {loading ? (
          <p className="p-8 text-center text-body text-fg-muted">Loading memories…</p>
        ) : memories.length === 0 ? (
          <EmptyState
            icon={Database}
            title="No memories yet"
            description="Memories are captured from conversations, or you can add one by hand."
            action={{ label: 'New memory', onClick: () => setSelected('new') }}
          />
        ) : view === 'timeline' ? (
          <MemoryTimeline
            memories={memories}
            zoom={zoom}
            onZoomChange={setZoom}
            onSelect={(memory) => {
              setDrawerError(null);
              setSelected(memory);
            }}
            selectedId={selectedId}
          />
        ) : (
          <div className="h-full overflow-y-auto p-4">
            <ul className="flex flex-col gap-2">
              {memories.map((memory) => (
                <li key={memory.id}>
                  <MemoryCard
                    memory={memory}
                    selected={selectedId === memory.id}
                    onSelect={(next) => {
                      setDrawerError(null);
                      setSelected(next);
                    }}
                  />
                </li>
              ))}
            </ul>

            <div ref={sentinelRef} className="h-4" />

            {hasMore && (
              <div className="flex justify-center py-3">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={loadingMore}
                  onClick={() => void loadMore()}
                >
                  {loadingMore ? 'Loading…' : 'Load more'}
                </Button>
              </div>
            )}
            {!hasMore && (
              <p className="py-3 text-center text-caption text-fg-muted">
                {total} {total === 1 ? 'memory' : 'memories'}
              </p>
            )}
          </div>
        )}
      </div>

      <MemoryDrawer
        key={selected === 'new' ? 'new' : (selected?.id ?? 'closed')}
        memory={selected}
        error={drawerError}
        onClose={() => setSelected(null)}
        onSave={handleSave}
        onDelete={handleDelete}
      />
    </section>
  );
}
