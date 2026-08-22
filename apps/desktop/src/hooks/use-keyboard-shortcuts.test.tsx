import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { useKeyboardShortcuts } from '@/hooks/use-keyboard-shortcuts';
import { useAppStore } from '@/stores/use-app-store';
import { useSessionStore } from '@/stores/use-session-store';

function RegistryProbe() {
  const commands = useKeyboardShortcuts();
  return (
    <main>
      <input aria-label="Editor" />
      <output aria-label="Command IDs">{commands.map((command) => command.id).join(' ')}</output>
    </main>
  );
}

function renderRegistry() {
  return render(
    <MemoryRouter>
      <RegistryProbe />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  useAppStore.setState({ sidebarCollapsed: false, commandPaletteOpen: false });
  useSessionStore.setState({
    sessions: [
      {
        id: 'session-fixture',
        title: 'تحقیق روی Rooya',
        createdAt: 1,
        updatedAt: 1,
        messageCount: 0,
      },
    ],
    activeSessionId: null,
    searchQuery: '',
  });
});

afterEach(() => {
  useSessionStore.setState({ sessions: [], activeSessionId: null, searchQuery: '' });
});

describe('useKeyboardShortcuts', () => {
  it('registers routes, sessions, appearance controls, tools, and all locales', () => {
    renderRegistry();
    const ids = screen.getByRole('status', { name: 'Command IDs' }).textContent ?? '';
    for (const id of [
      'route.dashboard',
      'route.settings',
      'route.scheduler',
      'session.session-fixture',
      'theme.warm',
      'accent.ocean',
      'density.dense',
      'zoom.150',
      'motion.reduce',
      'locale.fa',
      'locale.ko',
    ]) {
      expect(ids).toContain(id);
    }
  });

  it('runs global shortcuts but protects text entry', () => {
    renderRegistry();
    fireEvent.keyDown(window, { key: 'b', ctrlKey: true });
    expect(useAppStore.getState().sidebarCollapsed).toBe(true);

    const editor = screen.getByRole('textbox', { name: 'Editor' });
    fireEvent.keyDown(editor, { key: 'b', ctrlKey: true });
    expect(useAppStore.getState().sidebarCollapsed).toBe(true);
  });

  it('allows the palette shortcut while an editor has focus', () => {
    renderRegistry();
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Editor' }), {
      key: 'k',
      ctrlKey: true,
    });
    expect(useAppStore.getState().commandPaletteOpen).toBe(true);
  });
});
