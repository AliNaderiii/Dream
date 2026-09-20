/**
 * Memory explorer filter model.
 *
 * Kept in a module without components so React Fast Refresh stays intact for
 * `memory-toolbar.tsx` (react-refresh/only-export-components). Every control
 * is controlled state owned by the route, so the list view and the timeline
 * view stay in sync — switching views never resets a filter.
 */

import type { MemoryKind, MemorySort } from '@/lib/bridge/types';

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
