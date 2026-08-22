import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ScheduleHistory } from '@/components/scheduler/schedule-history';
import type { BridgeScheduleRun } from '@/lib/bridge/types';

function run(index: number): BridgeScheduleRun {
  return {
    id: index,
    schedule_id: 'schedule-1',
    started_at: 1_700_000_000 + index,
    completed_at: 1_700_000_001 + index,
    duration: 1,
    result_summary: `Run ${index}`,
    status: 'success',
  };
}

describe('ScheduleHistory', () => {
  it('keeps 1,000 history entries to fewer than 60 mounted rows', () => {
    const { container } = render(
      <ScheduleHistory runs={Array.from({ length: 1000 }, (_, index) => run(index))} />,
    );
    const viewport = container.querySelector<HTMLElement>('[data-virtualized="true"]');
    if (!viewport) throw new Error('missing virtual history viewport');
    expect(screen.getAllByRole('listitem').length).toBeLessThan(60);
    expect(screen.getByText('Run 0')).toBeInTheDocument();

    fireEvent.scroll(viewport, { target: { scrollTop: 18_000 } });
    expect(screen.getAllByRole('listitem').length).toBeLessThan(60);
    console.info(
      `scheduler_history_rows=1000 mounted_rows=${screen.getAllByRole('listitem').length}`,
    );
    expect(screen.getByText('Run 500')).toBeInTheDocument();
    expect(screen.queryByText('Run 0')).not.toBeInTheDocument();
  });
});
