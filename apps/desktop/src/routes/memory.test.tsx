import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import {
  EchoBridgeTransport,
  getBridgeClient,
  resetBridgeClient,
  type BridgeTransport,
} from '@/lib/bridge/client';
import type { BridgeConnectionState, RpcId, RpcParams, StreamChunk } from '@/lib/bridge/types';
import { MemoryRoute } from '@/routes/memory';

class MemoryStateTransport implements BridgeTransport {
  readonly kind = 'echo' as const;
  private readonly echo = new EchoBridgeTransport();
  listCalls = 0;
  failListOnce = false;
  hangFirstList = false;
  empty = false;
  large = false;

  request<T>(id: RpcId, method: string, params: RpcParams, onChunk?: (chunk: StreamChunk) => void) {
    if (method === 'memory.list') {
      this.listCalls += 1;
      if (this.hangFirstList && this.listCalls === 1) return new Promise<T>(() => {});
      if (this.failListOnce) {
        this.failListOnce = false;
        return Promise.reject(new Error('memory index unavailable'));
      }
      if (this.empty) {
        return Promise.resolve({ memories: [], total: 0, next_cursor: null, has_more: false } as T);
      }
      if (this.large) {
        const memories = Array.from({ length: 1000 }, (_, index) => ({
          id: index,
          kind: 'semantic',
          content: `Memory ${index}`,
          tags: [],
          importance: 0.5,
          created_at: 1_700_000_000 + index,
          last_used_at: 0,
          use_count: 0,
          source: 'fixture',
          archived: false,
          pinned: false,
          score: 0,
        }));
        return Promise.resolve({ memories, total: 1000, next_cursor: null, has_more: false } as T);
      }
    }
    if (method === 'memory.count' && this.hangFirstList) return new Promise<T>(() => {});
    if (method === 'memory.count' && this.empty) {
      return Promise.resolve({ total: 0, by_kind: {} } as T);
    }
    if (method === 'memory.count' && this.large) {
      return Promise.resolve({ total: 1000, by_kind: { semantic: 1000 } } as T);
    }
    return this.echo.request<T>(id, method, params, onChunk);
  }

  onState(_handler: (state: BridgeConnectionState) => void) {
    return () => {};
  }

  reconnect() {}
}

describe('MemoryRoute', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('renders the seeded memories with count badges', async () => {
    render(<MemoryRoute />);
    await screen.findByText(/Dream stores memories as semantic/);

    const semanticTab = screen.getByRole('tab', { name: /Semantic/ });
    expect(within(semanticTab).getByText('4')).toBeInTheDocument();
  });

  it('filters the list by kind', async () => {
    const user = userEvent.setup();
    render(<MemoryRoute />);
    await screen.findByText(/Dream stores memories as semantic/);

    await user.click(screen.getByRole('tab', { name: /Procedural/ }));

    await waitFor(() => {
      expect(screen.queryByText(/Dream stores memories as semantic/)).not.toBeInTheDocument();
    });
    expect(screen.getByText(/To export a skill/)).toBeInTheDocument();
  });

  it('debounces the search box before querying', async () => {
    const user = userEvent.setup();
    render(<MemoryRoute />);
    await screen.findByText(/Dream stores memories as semantic/);

    await user.type(screen.getByRole('searchbox', { name: /search memories/i }), 'skills');

    // The unrelated row survives only until the debounced query lands.
    await waitFor(
      () => {
        expect(screen.queryByText(/Dream stores memories as semantic/)).not.toBeInTheDocument();
      },
      { timeout: 3000 },
    );
    expect(screen.getByText(/Paired on the skills import validation/)).toBeInTheDocument();
  });

  it('opens the detail drawer for a memory', async () => {
    const user = userEvent.setup();
    render(<MemoryRoute />);
    const card = await screen.findByText(/Dream stores memories as semantic/);

    await user.click(card);

    const drawer = await screen.findByRole('dialog');
    expect(within(drawer).getByText('Memory detail')).toBeInTheDocument();
    expect(within(drawer).getByRole('button', { name: 'Edit' })).toBeInTheDocument();
  });

  it('switches to the timeline view and keeps the filters', async () => {
    const user = userEvent.setup();
    render(<MemoryRoute />);
    await screen.findByText(/Dream stores memories as semantic/);

    await user.click(screen.getByRole('tab', { name: /Episodic/ }));
    await waitFor(() => {
      expect(screen.queryByText(/Dream stores memories as semantic/)).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Timeline/ }));

    expect(screen.getByRole('group', { name: 'Timeline zoom' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Episodic/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText(/Reviewed the P-05 memory explorer/)).toBeInTheDocument();
  });

  it('renders a five-row loading skeleton', () => {
    const transport = new MemoryStateTransport();
    transport.hangFirstList = true;
    getBridgeClient().setTransport(transport);
    const { container } = render(<MemoryRoute />);
    expect(screen.getByRole('status', { name: 'Loading memories…' })).toBeInTheDocument();
    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(5);
  });

  it('keeps a 1,000-memory fixture below the mounted-row bound', async () => {
    const transport = new MemoryStateTransport();
    transport.large = true;
    getBridgeClient().setTransport(transport);
    render(<MemoryRoute />);

    await screen.findByText('Memory 0');
    const mountedRows = screen.getAllByRole('listitem').length;
    expect(mountedRows).toBeLessThan(60);
    console.info(`memory_fixture_rows=1000 mounted_rows=${mountedRows}`);
  });

  it('renders the real empty state', async () => {
    const transport = new MemoryStateTransport();
    transport.empty = true;
    getBridgeClient().setTransport(transport);
    render(<MemoryRoute />);
    expect(await screen.findByText('No memories yet')).toBeInTheDocument();
  });

  it('retries an error and re-invokes the memory bridge', async () => {
    const user = userEvent.setup();
    const transport = new MemoryStateTransport();
    transport.failListOnce = true;
    getBridgeClient().setTransport(transport);
    render(<MemoryRoute />);
    expect(await screen.findByRole('alert')).toHaveTextContent('memory index unavailable');
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText(/Dream stores memories as semantic/)).toBeInTheDocument();
    expect(transport.listCalls).toBe(2);
  });

  it('cancels a superseded load without leaving the skeleton active', async () => {
    const user = userEvent.setup();
    const transport = new MemoryStateTransport();
    transport.hangFirstList = true;
    getBridgeClient().setTransport(transport);
    render(<MemoryRoute />);
    await user.type(screen.getByRole('searchbox', { name: 'Search memories…' }), 'skills');
    expect(await screen.findByText(/Paired on the skills import validation/)).toBeInTheDocument();
    expect(screen.queryByRole('status', { name: 'Loading memories…' })).not.toBeInTheDocument();
    expect(transport.listCalls).toBe(2);
  });
});
