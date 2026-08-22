/**
 * Filter bar for the memory explorer.
 *
 * Every control is controlled state owned by the route, so the list view and
 * the timeline view stay in sync — switching views never resets a filter.
 */

import { List, Plus, Rows3, Search } from 'lucide-react';

import { ImportanceSlider } from '@/components/memory/importance-stars';
import { KIND_COLOR } from '@/components/memory/kind-badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { MEMORY_KINDS, MEMORY_SORTS } from '@/lib/bridge/types';
import type { MemoryKind, MemorySort } from '@/lib/bridge/types';
import { useTranslation } from '@/lib/i18n';
import { cn } from '@/utils/cn';

/** Everything the explorer filters on. Shared by both views. */
export interface MemoryFilters {
  search: string;
  kind: MemoryKind | 'all';
  dateFrom: string;
  dateTo: string;
  /** Minimum importance in stars, 0–10. */
  minStars: number;
  sort: MemorySort;
}

/** Filters with nothing applied. */
export const DEFAULT_FILTERS: MemoryFilters = {
  search: '',
  kind: 'all',
  dateFrom: '',
  dateTo: '',
  minStars: 0,
  sort: 'date_newest',
};

interface MemoryToolbarProps {
  filters: MemoryFilters;
  onChange: (patch: Partial<MemoryFilters>) => void;
  counts: Record<string, number>;
  total: number;
  view: 'list' | 'timeline';
  onViewChange: (view: 'list' | 'timeline') => void;
  onCreate: () => void;
}

export function MemoryToolbar({
  filters,
  onChange,
  counts,
  total,
  view,
  onViewChange,
  onCreate,
}: MemoryToolbarProps) {
  const { t } = useTranslation('memory');
  const tabs: Array<{ value: MemoryKind | 'all'; label: string; count: number }> = [
    { value: 'all', label: t('toolbar.all'), count: total },
    ...MEMORY_KINDS.map((kind) => ({
      value: kind,
      label: t(`kind.${kind}`),
      count: counts[kind] ?? 0,
    })),
  ];

  return (
    <div className="flex flex-col gap-3 border-b border-border-default bg-surface px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-56 flex-1">
          <Search
            className="pointer-events-none absolute start-2.5 top-1/2 size-4 -translate-y-1/2 text-fg-muted"
            aria-hidden
          />
          <input
            type="search"
            value={filters.search}
            onChange={(event) => onChange({ search: event.target.value })}
            placeholder={t('toolbar.search')}
            aria-label={t('toolbar.search')}
            className="selectable h-8 w-full rounded-md border border-border-default bg-canvas ps-8 pe-2 text-body text-fg-primary placeholder:text-fg-muted"
          />
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant="secondary">
              {t(`toolbar.sort.${filters.sort}`)}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>{t('toolbar.sortBy')}</DropdownMenuLabel>
            {MEMORY_SORTS.map((sort) => (
              <DropdownMenuCheckboxItem
                key={sort}
                checked={filters.sort === sort}
                onCheckedChange={() => onChange({ sort })}
              >
                {t(`toolbar.sort.${sort}`)}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <div
          className="flex rounded-md border border-border-default"
          role="group"
          aria-label={t('toolbar.view')}
        >
          <Button
            size="sm"
            variant={view === 'list' ? 'primary' : 'ghost'}
            aria-pressed={view === 'list'}
            className="rounded-e-none"
            onClick={() => onViewChange('list')}
          >
            <List aria-hidden />
            {t('toolbar.list')}
          </Button>
          <Button
            size="sm"
            variant={view === 'timeline' ? 'primary' : 'ghost'}
            aria-pressed={view === 'timeline'}
            className="rounded-s-none"
            onClick={() => onViewChange('timeline')}
          >
            <Rows3 aria-hidden />
            {t('toolbar.timeline')}
          </Button>
        </div>

        <Button size="sm" variant="primary" onClick={onCreate}>
          <Plus aria-hidden />
          {t('newMemory')}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label={t('toolbar.filterKind')}>
          {tabs.map((tab) => {
            const active = filters.kind === tab.value;
            return (
              <button
                key={tab.value}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => onChange({ kind: tab.value })}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-caption font-medium transition-colors duration-fast',
                  active
                    ? 'border-accent bg-accent-soft text-accent-text'
                    : 'border-border-default text-fg-secondary hover:bg-surface-2',
                )}
              >
                {tab.value !== 'all' && (
                  <span
                    aria-hidden
                    className="size-2 rounded-full"
                    style={{ backgroundColor: KIND_COLOR[tab.value] }}
                  />
                )}
                {tab?.label}
                <span className="tabular rounded-full bg-surface-2 px-1.5 text-micro text-fg-muted">
                  {tab.count}
                </span>
              </button>
            );
          })}
        </div>

        <label className="flex items-center gap-2 text-caption text-fg-secondary">
          <span>{t('toolbar.from')}</span>
          <input
            type="date"
            value={filters.dateFrom}
            onChange={(event) => onChange({ dateFrom: event.target.value })}
            aria-label={t('toolbar.createdFrom')}
            className="ltr-island h-7 rounded-md border border-border-default bg-canvas px-2 text-caption text-fg-primary"
          />
        </label>
        <label className="flex items-center gap-2 text-caption text-fg-secondary">
          <span>{t('toolbar.to')}</span>
          <input
            type="date"
            value={filters.dateTo}
            onChange={(event) => onChange({ dateTo: event.target.value })}
            aria-label={t('toolbar.createdTo')}
            className="ltr-island h-7 rounded-md border border-border-default bg-canvas px-2 text-caption text-fg-primary"
          />
        </label>

        <div className="flex items-center gap-2 text-caption text-fg-secondary">
          <span id="min-importance-label">{t('toolbar.minImportance')}</span>
          <ImportanceSlider
            id="min-importance"
            label={t('toolbar.minImportance')}
            value={filters.minStars}
            onChange={(minStars) => onChange({ minStars })}
          />
        </div>
      </div>
    </div>
  );
}
