import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';

import App from '@/App';
import { useAppStore } from '@/stores/use-app-store';
import { useSessionStore } from '@/stores/use-session-store';

/** Renders the whole shell at `route`, exactly as `main.tsx` does. */
function renderApp(route = '/') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="*" element={<App />} />
      </Routes>
    </MemoryRouter>,
  );
}

const initialApp = useAppStore.getState();

describe('app shell', () => {
  beforeEach(() => {
    useAppStore.setState(initialApp, true);
    useSessionStore.setState({ sessions: [], activeSessionId: null, searchQuery: '' });
    document.documentElement.removeAttribute('data-theme');
  });

  it('renders the shell chrome on the dashboard', () => {
    renderApp('/');

    expect(screen.getByRole('navigation', { name: 'Primary' })).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'Sessions' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
  });

  it.each([
    ['/memory', 'Memory explorer'],
    ['/skills', 'Skills manager'],
    ['/projects', 'Projects'],
    ['/subagents', 'Subagents'],
    ['/provenance', 'Provenance'],
    ['/data', 'Data workbench'],
    ['/providers', 'Providers'],
    ['/settings', 'Appearance'],
  ])('renders %s', (route, heading) => {
    renderApp(route);
    // Level 2: the top bar repeats several of these words as its h1 page title.
    expect(screen.getByRole('heading', { level: 2, name: heading })).toBeInTheDocument();
  });

  it('redirects an unknown route to the dashboard', () => {
    renderApp('/does-not-exist');
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
  });

  it('renders a conversation for a known session id', () => {
    const session = useSessionStore.getState().createSession('Persian grammar');
    renderApp(`/chat/${session.id}`);

    expect(screen.getByRole('heading', { level: 2, name: 'Persian grammar' })).toBeInTheDocument();
  });

  it('toggles the sidebar closed and open again', async () => {
    const user = userEvent.setup();
    renderApp('/');

    await user.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
    expect(screen.queryByRole('complementary', { name: 'Sessions' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Expand sidebar' }));
    expect(screen.getByRole('complementary', { name: 'Sessions' })).toBeInTheDocument();
  });

  it('applies the dark theme to the document when toggled', async () => {
    const user = userEvent.setup();
    renderApp('/');

    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    await user.click(screen.getByRole('button', { name: 'Switch to dark theme' }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('switches the document to RTL for Persian', async () => {
    const user = userEvent.setup();
    renderApp('/');

    await user.click(screen.getByRole('button', { name: 'تغییر به فارسی' }));

    expect(document.documentElement.getAttribute('dir')).toBe('rtl');
    expect(document.documentElement.getAttribute('lang')).toBe('fa');
  });

  it('creates a session from the sidebar and navigates to it', async () => {
    const user = userEvent.setup();
    renderApp('/');

    const sidebar = screen.getByRole('complementary', { name: 'Sessions' });
    await user.click(within(sidebar).getByRole('button', { name: 'New session' }));

    expect(useSessionStore.getState().sessions).toHaveLength(1);
    expect(screen.getByRole('heading', { name: 'Conversation' })).toBeInTheDocument();
  });

  it('opens the command palette with the keyboard and runs a command', async () => {
    const user = userEvent.setup();
    renderApp('/');

    await user.keyboard('{Control>}k{/Control}');
    const dialog = await screen.findByRole('dialog', { name: 'Command palette' });

    await user.type(within(dialog).getByRole('textbox', { name: 'Search commands' }), 'settings');
    await user.keyboard('{Enter}');

    expect(screen.getByRole('heading', { level: 2, name: 'Appearance' })).toBeInTheDocument();
  });
});
