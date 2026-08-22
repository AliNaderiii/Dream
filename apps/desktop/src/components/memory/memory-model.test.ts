import { describe, expect, it } from 'vitest';

import { DEFAULT_FILTERS } from './memory-toolbar';
import { buildMemoryQuery } from './memory-model';

describe('memory model', () => {
  it('normalizes an empty filter set for the bridge', () => {
    expect(buildMemoryQuery(DEFAULT_FILTERS, '   ', 0)).toEqual({
      limit: 25,
      kind_filter: null,
      search_query: null,
      date_from: null,
      date_to: null,
      min_importance: null,
      sort_by: 'date_newest',
    });
  });

  it('uses settled values and maps ten-star importance onto the bridge scale', () => {
    const query = buildMemoryQuery(
      {
        ...DEFAULT_FILTERS,
        kind: 'semantic',
        dateFrom: '2026-08-21',
        dateTo: '2026-08-22',
        sort: 'importance',
      },
      '  release plan  ',
      7,
    );

    expect(query).toMatchObject({
      kind_filter: 'semantic',
      search_query: 'release plan',
      min_importance: 0.7,
      sort_by: 'importance',
    });
    expect(query.date_from).not.toBeNull();
    expect(query.date_to).toBeGreaterThan(query.date_from ?? 0);
  });
});
