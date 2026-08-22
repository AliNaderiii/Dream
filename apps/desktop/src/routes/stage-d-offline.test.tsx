import { act, render, screen } from '@testing-library/react';
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
import { MemoryRoute } from '@/routes/memory';
import { SchedulerRoute } from '@/routes/scheduler';
import { SkillsRoute } from '@/routes/skills';
import { SubagentsRoute } from '@/routes/subagents';
import { useAppStore } from '@/stores/use-app-store';
import { useSessionStore } from '@/stores/use-session-store';

class DisconnectableTransport implements BridgeTransport {
  readonly kind = 'echo' as const;
  private readonly echo = new EchoBridgeTransport();
  private readonly handlers = new Set<(state: BridgeConnectionState) => void>();

  request<T>(id: RpcId, method: string, params: RpcParams, onChunk?: (chunk: StreamChunk) => void) {
    return this.echo.request<T>(id, method, params, onChunk);
  }

  onState(handler: (state: BridgeConnectionState) => void) {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  reconnect() {}

  disconnect() {
    this.handlers.forEach((handler) => handler('disconnected'));
  }
}

const surfaceRenderers = {
  sessions: () =>
    render(
      <MemoryRouter>
        <TooltipProvider>
          <Sidebar />
        </TooltipProvider>
      </MemoryRouter>,
    ),
  memory: () => render(<MemoryRoute />),
  skills: () => render(<SkillsRoute />),
  subagents: () => render(<SubagentsRoute />),
  scheduler: () => render(<SchedulerRoute />),
};

describe.each(Object.entries(surfaceRenderers))(
  'Stage D %s offline state',
  (_name, renderSurface) => {
    beforeEach(() => {
      resetBridgeClient();
      useAppStore.setState({ sidebarCollapsed: false });
      useSessionStore.setState({ sessions: [], activeSessionId: null, searchQuery: '' });
    });

    it('renders the shared bridge-dead state with a reconnect action', () => {
      const transport = new DisconnectableTransport();
      getBridgeClient().setTransport(transport);
      renderSurface();

      act(() => transport.disconnect());

      expect(screen.getByText(/Dream engine (?:is )?offline/)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Reconnect' })).toBeInTheDocument();
    });
  },
);
