/**
 * Memory explorer.
 *
 * Filters live in one piece of state shared by the list and timeline views, so
 * switching views never loses context. The list pages with the cursor the
 * bridge returns; the timeline renders whatever has been loaded so far and
 * groups it by day, week or month.
 */

import { Database } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { MemoryCard } from '@/components/memory/memory-card';
import { MemoryDrawer, type MemoryDraft } from '@/components/memory/memory-drawer';
import { buildMemoryQuery } from '@/components/memory/memory-model';
import { MemoryTimeline } from '@/components/memory/memory-timeline';
import {
  DEFAULT_FILTERS,
  MemoryToolbar,
  type MemoryFilters,
} from '@/components/memory/memory-toolbar';
import { BridgeOfflineBanner } from '@/components/shared/bridge-offline-banner';
import { EmptyState } from '@/components/shared/empty-state';
import { VirtualList } from '@/components/shared/virtual-list';
import { Button } from '@/components/ui/button';
import { useDebouncedValue } from '@/hooks/use-debounced-value';
import { useTranslation } from '@/lib/i18n';
import { useBridge } from '@/lib/bridge/hooks';
import {
  countMemories,
  createMemory,
  deleteMemory,
  listMemories,
  updateMemory,
} from '@/lib/bridge/memory';
import type { RequestOptions } from '@/lib/bridge/client';
import type { BridgeMemory } from '@/lib/bridge/types';
import type { TimelineZoom } from '@/utils/time';

export function MemoryRoute() {
  const { t } = useTranslation('memory');
  const { t: tc } = useTranslation('common');
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

  const query = useMemo(
    () =>
      buildMemoryQuery(
        {
          kind: filters.kind,
          dateFrom: filters.dateFrom,
          dateTo: filters.dateTo,
          sort: filters.sort,
        },
        debouncedSearch,
        debouncedStars,
      ),
    [filters.kind, filters.dateFrom, filters.dateTo, filters.sort, debouncedSearch, debouncedStars],
  );

  const refreshCounts = useCallback(
    async (options?: RequestOptions) => {
      try {
        const result = await countMemories(client, options);
        setCounts(result.by_kind ?? {});
        setCountTotal(result.total ?? 0);
      } catch {
        // Counts are decorative; a failure must not blank the list.
      }
    },
    [client],
  );

  // Reload the first page whenever a filter settles. State updates happen in
  // the promise callbacks, never synchronously in the effect body.
  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const page = await listMemories(client, query, { signal: controller.signal });
        setMemories(page.memories);
        setTotal(page.total);
        setCursor(page.next_cursor);
        setHasMore(page.has_more);
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : t('failedLoad'));
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void load();
    return () => controller.abort();
  }, [client, query, t]);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(() => refreshCounts({ signal: controller.signal }));
    return () => controller.abort();
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
      setError(err instanceof Error ? err.message : t('failedLoadMore'));
    } finally {
      setLoadingMore(false);
    }
  }, [client, cursor, hasMore, loadingMore, query, t]);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await listMemories(client, query);
      setMemories(page.memories);
      setTotal(page.total);
      setCursor(page.next_cursor);
      setHasMore(page.has_more);
      await refreshCounts();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('failedLoad'));
    } finally {
      setLoading(false);
    }
  }, [client, query, refreshCounts, t]);

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
      setDrawerError(err instanceof Error ? err.message : t('failedSave'));
    }
  };

  const handleDelete = async (record: BridgeMemory) => {
    setDrawerError(null);
    try {
      await deleteMemory(client, record.id);
      setSelected(null);
      await reload();
    } catch (err) {
      setDrawerError(err instanceof Error ? err.message : t('failedDelete'));
    }
  };

  const selectedId = selected && selected !== 'new' ? selected.id : null;

  return (
    <section aria-label={t('title')} className="flex h-full min-h-0 flex-col">
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
        {loading ? t('loading') : t('shown', { shown: memories.length, total })}
      </p>

      <BridgeOfflineBanner />

      {error && (
        <div
          role="alert"
          className="flex items-center gap-3 border-b border-danger-fg bg-danger-bg px-4 py-2 text-caption text-danger-fg"
        >
          <span className="min-w-0 flex-1">{error}</span>
          <Button size="sm" variant="secondary" onClick={() => void reload()}>
            {t('retry')}
          </Button>
        </div>
      )}

      <div className="min-h-0 flex-1">
        {loading ? (
          <div role="status" aria-label={t('loading')} className="flex flex-col gap-2 p-4">
            {Array.from({ length: 5 }, (_, index) => (
              <div
                key={index}
                className="h-40 animate-pulse rounded-xl bg-surface-2 motion-reduce:animate-none"
              />
            ))}
          </div>
        ) : memories.length === 0 ? (
          <EmptyState
            icon={Database}
            title={t('noMemories')}
            description={t('noMemoriesDesc')}
            action={{ label: t('newMemory'), onClick: () => setSelected('new') }}
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
          <div className="flex h-full min-h-0 flex-col p-4">
            <VirtualList
              items={memories}
              getKey={(memory) => memory.id}
              estimateSize={168}
              virtualizeAt={0}
              ariaLabel={t('resultsLabel')}
              className="flex-1"
              onEndReached={hasMore && !loadingMore ? () => void loadMore() : undefined}
              renderItem={(memory) => (
                <div className="h-full pb-2">
                  <MemoryCard
                    memory={memory}
                    selected={selectedId === memory.id}
                    onSelect={(next) => {
                      setDrawerError(null);
                      setSelected(next);
                    }}
                  />
                </div>
              )}
            />

            {hasMore && (
              <div className="flex justify-center py-3">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={loadingMore}
                  onClick={() => void loadMore()}
                >
                  {loadingMore ? tc('generic.loading') : t('loadMore')}
                </Button>
              </div>
            )}
            {!hasMore && (
              <p className="py-3 text-center text-caption text-fg-muted">
                {total === 1 ? t('memoryCountOne') : t('memoryCount', { count: total })}
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
