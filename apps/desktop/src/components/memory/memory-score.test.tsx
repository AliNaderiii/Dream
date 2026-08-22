import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import {
  explainMemoryScore,
  MEMORY_SCORE_WEIGHTS,
  MemoryScore,
} from '@/components/memory/memory-score';
import type { BridgeMemory } from '@/lib/bridge/types';
import { i18n } from '@/lib/i18n';

const memory: BridgeMemory = {
  id: 1,
  kind: 'semantic',
  content: 'A scored memory',
  tags: [],
  importance: 0.8,
  created_at: 1_700_000_000,
  last_used_at: 1_700_000_000,
  use_count: 5,
  source: 'test',
  archived: false,
  pinned: false,
  score: 0.75,
};

afterEach(async () => {
  await act(() => i18n.changeLanguage('en'));
  document.documentElement.dir = 'ltr';
});

describe('memory score explanation', () => {
  it('mirrors all four protocol factors and weights', () => {
    const parts = explainMemoryScore(memory, memory.created_at + 30 * 24 * 60 * 60);
    expect(parts.map((part) => part.factor)).toEqual([
      'relevance',
      'recency',
      'importance',
      'usage',
    ]);
    expect(Object.fromEntries(parts.map((part) => [part.factor, part.weight]))).toEqual(
      MEMORY_SCORE_WEIGHTS,
    );
    expect(parts.find((part) => part.factor === 'recency')?.value).toBeCloseTo(0.5);
    expect(parts.find((part) => part.factor === 'importance')?.value).toBe(0.8);
    expect(parts.reduce((sum, part) => sum + (part.contribution ?? 0), 0)).toBeCloseTo(
      memory.score,
    );
  });

  it('marks relevance unavailable when a list row was not retrieval-ranked', () => {
    const unranked = { ...memory, score: 0 };
    const parts = explainMemoryScore(unranked, memory.created_at);
    expect(parts.find((part) => part.factor === 'relevance')?.value).toBeNull();
    render(<MemoryScore memory={unranked} />);
    expect(screen.getByRole('meter', { name: 'Relevance score factor' })).toHaveAttribute(
      'aria-valuetext',
      'Unavailable',
    );
    expect(screen.getByText('Not ranked')).toBeInTheDocument();
  });

  it('renders four accessible meters and the composite score', () => {
    render(<MemoryScore memory={memory} />);
    expect(screen.getAllByRole('meter')).toHaveLength(4);
    expect(screen.getByLabelText('Memory score: 75%')).toBeInTheDocument();
    expect(
      screen.getByText('55% relevance + 20% recency + 15% importance + 10% usage'),
    ).toBeInTheDocument();
  });

  it('uses real Persian factor labels in an RTL document', async () => {
    await act(() => i18n.changeLanguage('fa'));
    document.documentElement.dir = 'rtl';
    render(<MemoryScore memory={memory} />);
    expect(screen.getByText('امتیاز بازیابی')).toBeInTheDocument();
    expect(screen.getByText('ارتباط')).toBeInTheDocument();
    expect(screen.getByText('تازگی')).toBeInTheDocument();
    expect(screen.getByText('اهمیت')).toBeInTheDocument();
    expect(screen.getByText('استفاده')).toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute('dir', 'rtl');
  });
});
