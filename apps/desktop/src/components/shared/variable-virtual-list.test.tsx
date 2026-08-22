import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { VariableVirtualList } from '@/components/shared/variable-virtual-list';

const fixture = Array.from({ length: 1_000 }, (_, index) => ({
  id: `row-${index}`,
  label: `Variable row ${index}`,
}));
const getKey = (item: (typeof fixture)[number]) => item.id;
const renderItem = (item: (typeof fixture)[number]) => <div>{item.label}</div>;

describe('VariableVirtualList', () => {
  it('bounds a 1,000-row variable-height fixture below 60 mounted rows', () => {
    const { container } = render(
      <VariableVirtualList
        items={fixture}
        getKey={getKey}
        renderItem={renderItem}
        estimatedItemSize={80}
        viewportSize={640}
        ariaLabel="Variable fixture"
      />,
    );
    const mounted = container.querySelectorAll('[data-virtual-index]').length;
    console.info(`variable_fixture_rows=1000 mounted_rows=${mounted}`);
    expect(mounted).toBeGreaterThan(0);
    expect(mounted).toBeLessThan(60);
    expect(screen.queryByText('Variable row 999')).not.toBeInTheDocument();
  });

  it('remeasures rows and uses logical block positioning', () => {
    const height = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockImplementation(function implementation(this: HTMLElement) {
        const index = Number(this.dataset['virtualIndex'] ?? 0);
        const blockSize = index % 2 === 0 ? 48 : 132;
        return {
          x: 0,
          y: 0,
          width: 640,
          height: blockSize,
          top: 0,
          right: 640,
          bottom: blockSize,
          left: 0,
          toJSON: () => ({}),
        };
      });
    const { container } = render(
      <VariableVirtualList
        items={fixture}
        getKey={getKey}
        renderItem={renderItem}
        estimatedItemSize={80}
        viewportSize={640}
        ariaLabel="Measured fixture"
      />,
    );
    const rows = container.querySelectorAll<HTMLElement>('[data-virtual-index]');
    expect(rows[1]?.style.insetBlockStart).toBe('48px');
    expect(rows[2]?.style.insetBlockStart).toBe('180px');
    expect(rows[1]?.style.left).toBe('');
    height.mockRestore();
  });

  it('tail-follows newly appended items', () => {
    function Fixture() {
      const [items, setItems] = useState(fixture.slice(0, 100));
      return (
        <>
          <button type="button" onClick={() => setItems(fixture.slice(0, 101))}>
            Append
          </button>
          <VariableVirtualList
            items={items}
            getKey={getKey}
            renderItem={renderItem}
            estimatedItemSize={80}
            viewportSize={640}
            tailFollow
            ariaLabel="Tail fixture"
          />
        </>
      );
    }
    render(<Fixture />);
    const feed = screen.getByRole('feed', { name: 'Tail fixture' });
    Object.defineProperties(feed, {
      scrollHeight: { configurable: true, value: 8_080 },
      scrollTop: { configurable: true, writable: true, value: 0 },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Append' }));
    expect(feed.scrollTop).toBe(8_080);
    expect(screen.getByText('Variable row 100')).toBeInTheDocument();
  });

  it('releases tail ownership after the reader scrolls away', () => {
    function Fixture() {
      const [items, setItems] = useState(fixture.slice(0, 100));
      return (
        <>
          <button type="button" onClick={() => setItems(fixture.slice(0, 101))}>
            Append away
          </button>
          <VariableVirtualList
            items={items}
            getKey={getKey}
            renderItem={renderItem}
            estimatedItemSize={80}
            viewportSize={640}
            tailFollow
            ariaLabel="Released tail fixture"
          />
        </>
      );
    }
    render(<Fixture />);
    const feed = screen.getByRole('feed', { name: 'Released tail fixture' });
    Object.defineProperties(feed, {
      scrollHeight: { configurable: true, value: 8_080 },
      clientHeight: { configurable: true, value: 640 },
      scrollTop: { configurable: true, writable: true, value: 100 },
    });
    fireEvent.scroll(feed);
    fireEvent.click(screen.getByRole('button', { name: 'Append away' }));
    expect(feed.scrollTop).toBe(100);
    expect(screen.queryByText('Variable row 100')).not.toBeInTheDocument();
  });
});
