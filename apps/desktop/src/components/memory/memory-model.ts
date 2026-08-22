import { toImportance } from '@/lib/bridge/memory';
import type { MemoryListParams } from '@/lib/bridge/types';
import { dateInputToSeconds } from '@/utils/time';

import type { MemoryFilters } from './memory-toolbar';

const PAGE_SIZE = 25;
type MemoryQueryFilters = Pick<MemoryFilters, 'kind' | 'dateFrom' | 'dateTo' | 'sort'>;

/** Builds the normalized bridge query shared by initial loads and retries. */
export function buildMemoryQuery(
  filters: MemoryQueryFilters,
  settledSearch: string,
  settledStars: number,
): MemoryListParams {
  return {
    limit: PAGE_SIZE,
    kind_filter: filters.kind === 'all' ? null : filters.kind,
    search_query: settledSearch.trim() || null,
    date_from: dateInputToSeconds(filters.dateFrom),
    date_to: dateInputToSeconds(filters.dateTo, true),
    min_importance: settledStars > 0 ? toImportance(settledStars) : null,
    sort_by: filters.sort,
  };
}
