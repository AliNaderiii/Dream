/**
 * Filter bar for the memory explorer.
 *
 * Every control is controlled state owned by the route, so the list view and
 * the timeline view stay in sync — switching views never resets a filter.
 */

import { List, Plus, Rows3, Search } from 'lucide-react';

import { ImportanceSlider } from '@/components/memory/importance-stars';
import { KIND_COLOR, kindLabel } from '@/components/memory/kind-badge';
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

const SORT_LABEL: Record<MemorySort, string> = {
  relevance: 'Relevance',
  date_newest: 'Newest first',
  date_oldest: 'Oldest first',
  importance: 'Importance',
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
  const tabs: Array<{ value: MemoryKind | 'all'; label: string; count: number }> = [
    { value: 'all', label: 'All', count: total },
    ...MEMORY_KINDS.map((kind) => ({
      value: kind,
      label: kindLabel(kind),
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
            placeholder="Search memories…"
            aria-label="Search memories"
            className="selectable h-8 w-full rounded-md border border-border-default bg-canvas ps-8 pe-2 text-body text-fg-primary placeholder:text-fg-muted"
          />
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant="secondary">
              {SORT_LABEL[filters.sort]}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>Sort by</DropdownMenuLabel>
            {MEMORY_SORTS.map((sort) => (
              <DropdownMenuCheckboxItem
                key={sort}
                checked={filters.sort === sort}
                onCheckedChange={() => onChange({ sort })}
              >
                {SORT_LABEL[sort]}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <div
          className="flex rounded-md border border-border-default"
          role="group"
          aria-label="View"
        >
          <Button
            size="sm"
            variant={view === 'list' ? 'primary' : 'ghost'}
            aria-pressed={view === 'list'}
            className="rounded-e-none"
            onClick={() => onViewChange('list')}
          >
            <List aria-hidden />
            List
          </Button>
          <Button
            size="sm"
            variant={view === 'timeline' ? 'primary' : 'ghost'}
            aria-pressed={view === 'timeline'}
            className="rounded-s-none"
            onClick={() => onViewChange('timeline')}
          >
            <Rows3 aria-hidden />
            Timeline
          </Button>
        </div>

        <Button size="sm" variant="primary" onClick={onCreate}>
          <Plus aria-hidden />
          New memory
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Filter by kind">
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
                {tab.label}
                <span className="tabular rounded-full bg-surface-2 px-1.5 text-micro text-fg-muted">
                  {tab.count}
                </span>
              </button>
            );
          })}
        </div>

        <label className="flex items-center gap-2 text-caption text-fg-secondary">
          <span>From</span>
          <input
            type="date"
            value={filters.dateFrom}
            onChange={(event) => onChange({ dateFrom: event.target.value })}
            aria-label="Created from"
            className="ltr-island h-7 rounded-md border border-border-default bg-canvas px-2 text-caption text-fg-primary"
          />
        </label>
        <label className="flex items-center gap-2 text-caption text-fg-secondary">
          <span>To</span>
          <input
            type="date"
            value={filters.dateTo}
            onChange={(event) => onChange({ dateTo: event.target.value })}
            aria-label="Created to"
            className="ltr-island h-7 rounded-md border border-border-default bg-canvas px-2 text-caption text-fg-primary"
          />
        </label>

        <div className="flex items-center gap-2 text-caption text-fg-secondary">
          <span id="min-importance-label">Min importance</span>
          <ImportanceSlider
            id="min-importance"
            label="Minimum importance"
            value={filters.minStars}
            onChange={(minStars) => onChange({ minStars })}
          />
        </div>
      </div>
    </div>
  );
}
