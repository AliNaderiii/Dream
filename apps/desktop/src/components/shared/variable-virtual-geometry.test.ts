import { describe, expect, it } from 'vitest';

import {
  isNearVirtualTail,
  variableMeasurements,
  variableRange,
} from '@/components/shared/variable-virtual-geometry';

const rows = ['a', 'b', 'c', 'd'];

describe('variable virtual geometry', () => {
  it('combines measured heights with the estimate fallback', () => {
    expect(variableMeasurements(rows, (row) => row, new Map([['b', 80]]), 40)).toEqual({
      offsets: [0, 40, 120, 160],
      heights: [40, 80, 40, 40],
      total: 200,
    });
  });

  it('returns a bounded overscanned range', () => {
    expect(variableRange([0, 40, 120, 160], 4, 100, 50, 1)).toEqual({ start: 0, end: 4 });
    expect(variableRange([], 0, 0, 50, 1)).toEqual({ start: 0, end: 0 });
  });

  it('releases tail ownership when the reader moves away', () => {
    expect(isNearVirtualTail(1_000, 740, 220)).toBe(true);
    expect(isNearVirtualTail(1_000, 500, 220)).toBe(false);
  });
});
