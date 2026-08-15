import { beforeEach, describe, expect, it } from 'vitest';

import {
  countPanes,
  createPane,
  findPane,
  paneLeaf,
  removePane,
  resizeNode,
  splitAtPane,
  useLayoutStore,
} from '@/stores/use-layout-store';

describe('recursive pane layout', () => {
  beforeEach(() => {
    localStorage.clear();
    useLayoutStore.getState().resetLayout();
  });

  it('splits a leaf recursively and collapses its parent on close', () => {
    const first = createPane({ id: 'first' });
    const second = createPane({ id: 'second' });
    const third = createPane({ id: 'third' });
    let root = splitAtPane(paneLeaf(first), first.id, second, 'horizontal');
    root = splitAtPane(root, second.id, third, 'vertical');

    expect(countPanes(root)).toBe(3);
    expect(findPane(root, third.id)).toEqual(third);

    const collapsed = removePane(root, third.id);
    expect(collapsed).not.toBeNull();
    expect(countPanes(collapsed!)).toBe(2);
    expect(findPane(collapsed!, second.id)).toEqual(second);
  });

  it('clamps serialized split ratios', () => {
    const first = createPane({ id: 'first' });
    const second = createPane({ id: 'second' });
    const root = splitAtPane(paneLeaf(first), first.id, second, 'horizontal');
    if (root.kind !== 'split') throw new Error('expected split');

    expect((resizeNode(root, root.id, -2) as typeof root).ratio).toBe(0.1);
    expect((resizeNode(root, root.id, 4) as typeof root).ratio).toBe(0.9);
  });

  it('keeps provider, model, reasoning, and session isolated per pane', () => {
    const store = useLayoutStore.getState();
    const screen = store.screens[0];
    const firstId = screen.activePaneId;
    const secondId = store.addPane(firstId, 'horizontal');

    useLayoutStore.getState().updatePane(firstId, {
      sessionId: 'session-a',
      providerId: 'openai-one',
      modelName: 'gpt-4o',
      reasoningEffort: 1,
    });
    useLayoutStore.getState().updatePane(secondId, {
      sessionId: 'session-b',
      providerId: 'anthropic-one',
      modelName: 'claude-sonnet',
      reasoningEffort: 0.25,
    });

    const root = useLayoutStore.getState().screens[0].root;
    expect(findPane(root, firstId)).toMatchObject({
      sessionId: 'session-a',
      providerId: 'openai-one',
      reasoningEffort: 1,
    });
    expect(findPane(root, secondId)).toMatchObject({
      sessionId: 'session-b',
      providerId: 'anthropic-one',
      reasoningEffort: 0.25,
    });
  });

  it('moves a pane to another virtual screen', () => {
    const store = useLayoutStore.getState();
    const source = store.screens[0];
    const movingId = store.addPane(source.activePaneId, 'horizontal');
    const targetScreenId = useLayoutStore.getState().addScreen('Research');

    useLayoutStore.getState().movePaneToScreen(movingId, targetScreenId);
    const screens = useLayoutStore.getState().screens;
    const target = screens.find((screen) => screen.id === targetScreenId)!;

    expect(findPane(target.root, movingId)).toBeDefined();
    expect(useLayoutStore.getState().activeScreenId).toBe(targetScreenId);
  });
});
