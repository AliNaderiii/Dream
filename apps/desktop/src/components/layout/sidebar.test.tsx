import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';

import { Sidebar } from '@/components/layout/sidebar';
import { TooltipProvider } from '@/components/ui/tooltip';
import {
  EchoBridgeTransport,
  getBridgeClient,
  resetBridgeClient,
  type BridgeTransport,
} from '@/lib/bridge/client';
import type { BridgeConnectionState, RpcId, RpcParams, StreamChunk } from '@/lib/bridge/types';
import { useAppStore } from '@/stores/use-app-store';
import { useSessionStore } from '@/stores/use-session-store';
import type { Session } from '@/types';

class SessionTransport implements BridgeTransport {
  readonly kind = 'tauri' as const;
  requests = 0;
  failNext = false;
  hang = false;
  private readonly echo = new EchoBridgeTransport();

  request<T>(id: RpcId, method: string, params: RpcParams, onChunk?: (chunk: StreamChunk) => void) {
    this.requests += 1;
    if (this.hang) return new Promise<T>(() => {});
    if (this.failNext) {
      this.failNext = false;
      return Promise.reject(new Error('session index unavailable'));
    }
    return this.echo.request<T>(id, method, params, onChunk);
  }

  onState(_handler: (state: BridgeConnectionState) => void) {
    return () => {};
  }

  reconnect() {}
}

function session(index: number): Session {
  return {
    id: `session-${index}`,
    title: `Session ${index}`,
    createdAt: Date.now() - index,
    updatedAt: Date.now() - index,
    messageCount: 0,
  };
}

function renderSidebar() {
  return render(
    <MemoryRouter>
      <TooltipProvider>
        <Sidebar />
      </TooltipProvider>
    </MemoryRouter>,
  );
}

describe('Sidebar session management', () => {
  beforeEach(() => {
    resetBridgeClient();
    useAppStore.setState({ sidebarCollapsed: false, sidebarWidth: 280 });
    useSessionStore.setState({ sessions: [], activeSessionId: null, searchQuery: '' });
  });

  it('renders the empty session state', () => {
    renderSidebar();
    expect(screen.getByText('No sessions yet. Start one to begin.')).toBeInTheDocument();
  });

  it('keeps a 1,000-session fixture to a bounded keyboard-accessible DOM range', async () => {
    useSessionStore.setState({
      sessions: Array.from({ length: 1000 }, (_, index) => session(index)),
    });
    const { container } = renderSidebar();
    await waitFor(() => {
      expect(screen.getByRole('complementary', { name: 'Sessions' })).toHaveAttribute(
        'aria-busy',
        'false',
      );
    });
    const viewport = container.querySelector<HTMLElement>('[data-virtualized="true"]');
    if (!viewport) throw new Error('missing virtual viewport');

    expect(screen.getAllByRole('listitem').length).toBeLessThan(30);
    expect(screen.getByRole('button', { name: 'Session 0' })).toBeInTheDocument();
    fireEvent.scroll(viewport, { target: { scrollTop: 18_032 } });
    expect(screen.getAllByRole('listitem').length).toBeLessThan(30);
    console.info(
      `session_fixture_rows=1000 mounted_rows=${screen.getAllByRole('listitem').length}`,
    );
    expect(screen.getByRole('button', { name: 'Session 500' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Session 0' })).not.toBeInTheDocument();
  });

  it('renames a session from its keyboard-accessible actions menu', async () => {
    const user = userEvent.setup();
    useSessionStore.setState({ sessions: [session(1)] });
    renderSidebar();

    await user.click(screen.getByRole('button', { name: 'Actions for Session 1' }));
    await user.click(screen.getByRole('menuitem', { name: 'Rename' }));
    const dialog = screen.getByRole('dialog', { name: 'Rename session' });
    const input = within(dialog).getByLabelText('Session name');
    await user.clear(input);
    await user.type(input, 'Roadmap');
    await user.click(within(dialog).getByRole('button', { name: 'Rename' }));

    expect(useSessionStore.getState().sessions[0].title).toBe('Roadmap');
    expect(screen.getByRole('button', { name: 'Roadmap' })).toBeInTheDocument();
  });

  it('requires confirmation before deleting a session', async () => {
    const user = userEvent.setup();
    useSessionStore.setState({ sessions: [session(1)] });
    renderSidebar();

    await user.click(screen.getByRole('button', { name: 'Actions for Session 1' }));
    await user.click(screen.getByRole('menuitem', { name: 'Delete' }));
    expect(useSessionStore.getState().sessions).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Delete' }));
    expect(useSessionStore.getState().sessions).toHaveLength(0);
  });

  it('shows a multi-row skeleton and clears it when the bounded request is cancelled', () => {
    const transport = new SessionTransport();
    transport.hang = true;
    getBridgeClient().setTransport(transport);
    const { container, unmount } = renderSidebar();
    expect(screen.getByRole('status', { name: 'Loading sessions…' })).toBeInTheDocument();
    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(5);
    unmount();
    expect(screen.queryByRole('status', { name: 'Loading sessions…' })).not.toBeInTheDocument();
  });

  it('retries a failed session bridge request', async () => {
    const user = userEvent.setup();
    const transport = new SessionTransport();
    transport.failNext = true;
    getBridgeClient().setTransport(transport);
    renderSidebar();
    expect(await screen.findByRole('alert')).toHaveTextContent('session index unavailable');
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('No sessions yet. Start one to begin.')).toBeInTheDocument();
    expect(transport.requests).toBe(2);
  });
});
