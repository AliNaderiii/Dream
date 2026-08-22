import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { dockEdgeAt } from '@/components/panes/pane-geometry';
import { SplitLayout } from '@/components/panes/split-layout';
import {
  createPane,
  paneLeaf,
  splitAtPane,
  useLayoutStore,
  type PaneSplit,
} from '@/stores/use-layout-store';

vi.mock('@/components/panes/pane', () => ({
  Pane: ({ pane }: { pane: { id: string } }) => <div data-testid={`pane-${pane.id}`} />,
}));

function splitFixture(): PaneSplit {
  const first = createPane({ id: 'first' });
  const second = createPane({ id: 'second' });
  const root = splitAtPane(paneLeaf(first), first.id, second, 'horizontal');
  if (root.kind !== 'split') throw new Error('expected a split fixture');
  useLayoutStore.setState({
    screens: [
      {
        id: 'screen-fixture',
        name: 'Fixture',
        root,
        activePaneId: first.id,
        maximizedPaneId: null,
      },
    ],
    activeScreenId: 'screen-fixture',
  });
  return root;
}

function currentRatio(): number {
  const root = useLayoutStore.getState().screens[0]?.root;
  if (!root || root.kind !== 'split') throw new Error('expected current split');
  return root.ratio;
}

beforeEach(() => {
  document.documentElement.dir = 'ltr';
});

afterEach(() => {
  fireEvent.pointerUp(window);
  document.documentElement.dir = 'ltr';
});

describe('SplitLayout stability', () => {
  it('pins drag-resize to the measured container and minimum pane width', () => {
    const root = splitFixture();
    const { container } = render(<SplitLayout node={root} activePaneId="first" />);
    const split = container.querySelector<HTMLElement>(`[data-split-id="${root.id}"]`);
    if (!split) throw new Error('missing split container');
    vi.spyOn(split, 'getBoundingClientRect').mockReturnValue({
      left: 0,
      right: 1000,
      top: 0,
      bottom: 600,
      width: 1000,
      height: 600,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });

    fireEvent.pointerDown(screen.getByRole('separator', { name: 'Resize panes' }), {
      clientX: 500,
      clientY: 300,
    });
    fireEvent.pointerMove(window, { clientX: 800, clientY: 300 });
    expect(currentRatio()).toBe(0.7);
  });

  it('pins keyboard resize and exposes separator value semantics', () => {
    const root = splitFixture();
    render(<SplitLayout node={root} activePaneId="first" />);
    const separator = screen.getByRole('separator', { name: 'Resize panes' });
    expect(separator).toHaveAttribute('tabindex', '0');
    expect(separator).toHaveAttribute('aria-valuenow', '50');
    fireEvent.keyDown(separator, { key: 'ArrowRight' });
    expect(currentRatio()).toBe(0.55);
    fireEvent.keyDown(separator, { key: 'Home' });
    expect(currentRatio()).toBe(0.1);
  });

  it('mirrors horizontal pointer, keyboard, and docking geometry in RTL', () => {
    document.documentElement.dir = 'rtl';
    const root = splitFixture();
    const { container } = render(<SplitLayout node={root} activePaneId="first" />);
    const split = container.querySelector<HTMLElement>(`[data-split-id="${root.id}"]`);
    if (!split) throw new Error('missing split container');
    vi.spyOn(split, 'getBoundingClientRect').mockReturnValue({
      left: 0,
      right: 1000,
      top: 0,
      bottom: 600,
      width: 1000,
      height: 600,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });
    const separator = screen.getByRole('separator', { name: 'Resize panes' });
    fireEvent.pointerDown(separator, { clientX: 500, clientY: 300 });
    fireEvent.pointerMove(window, { clientX: 300, clientY: 300 });
    expect(currentRatio()).toBe(0.7);

    fireEvent.keyDown(separator, { key: 'ArrowRight' });
    expect(currentRatio()).toBe(0.45);
    expect(dockEdgeAt(0.1, 0.5, true)).toBe('right');
    expect(dockEdgeAt(0.9, 0.5, true)).toBe('left');
  });
});
