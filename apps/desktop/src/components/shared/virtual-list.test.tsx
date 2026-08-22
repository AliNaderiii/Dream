import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { VirtualList, virtualRange } from '@/components/shared/virtual-list';

describe('VirtualList', () => {
  it('calculates an overscanned range', () => {
    const offsets = [0, 40, 80, 120, 160];
    const sizes = [40, 40, 40, 40, 40];
    expect(virtualRange(offsets, sizes, 80, 40, 1)).toEqual({ start: 0, end: 4 });
  });

  it('keeps a 1,000-row fixture bounded and scrollable', () => {
    const items = Array.from({ length: 1000 }, (_, index) => `session-${index}`);
    const started = performance.now();
    const { container } = render(
      <VirtualList
        items={items}
        getKey={(item) => item}
        estimateSize={40}
        ariaLabel="Sessions"
        renderItem={(item) => <button type="button">{item}</button>}
      />,
    );
    const elapsed = performance.now() - started;
    const viewport = container.querySelector<HTMLElement>('[data-virtualized="true"]');
    if (!viewport) throw new Error('missing virtual viewport');
    expect(screen.getAllByRole('listitem').length).toBeLessThan(30);
    expect(screen.getByText('session-0')).toBeInTheDocument();

    fireEvent.scroll(viewport, { target: { scrollTop: 20_000 } });
    expect(screen.getByText('session-500')).toBeInTheDocument();
    expect(screen.queryByText('session-0')).not.toBeInTheDocument();
    console.info(
      `virtual_fixture_rows=1000 mounted_rows=${screen.getAllByRole('listitem').length} render_ms=${elapsed.toFixed(3)}`,
    );
    expect(elapsed).toBeLessThan(100);
  });

  it('notifies when the visible range reaches the end', () => {
    const onEndReached = vi.fn();
    const { container } = render(
      <VirtualList
        items={Array.from({ length: 100 }, (_, index) => index)}
        getKey={(item) => item}
        estimateSize={40}
        ariaLabel="Rows"
        onEndReached={onEndReached}
        renderItem={(item) => <span>{item}</span>}
      />,
    );
    const viewport = container.querySelector<HTMLElement>('[data-virtualized="true"]');
    if (!viewport) throw new Error('missing virtual viewport');
    fireEvent.scroll(viewport, { target: { scrollTop: 4_000 } });
    expect(onEndReached).toHaveBeenCalled();
  });
});
