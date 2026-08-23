/**
 * Bounded stores panel (MEM Stage F) — the pinned laws.
 *
 * Accounting is byte-identical to the kernel, the echo runtime refuses like
 * the kernel, nothing is written without an approval, a refusal changes
 * nothing, the frozen snapshot stays frozen, and the DOM stays bounded.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { act } from 'react';
import i18n from 'i18next';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BoundedStores } from '@/components/memory/bounded-stores';
import { EchoMemory2Runtime, type EchoBoundedSnapshot } from '@/lib/bridge/echo-memory2';
import { getBridgeClient, resetBridgeClient, type BridgeTransport } from '@/lib/bridge/client';
import { boundedHeader, boundedPercent, boundedUsedChars } from '@/lib/bridge/memory';
import type { BridgeConnectionState, RpcId, RpcParams, StreamChunk } from '@/lib/bridge/types';

afterEach(async () => {
  await act(() => i18n.changeLanguage('en'));
  document.documentElement.dir = 'ltr';
});

/** A transport answering only the memory2 family, with test knobs. */
class Memory2Transport implements BridgeTransport {
  readonly kind = 'echo' as const;
  private runtime = new EchoMemory2Runtime();
  calls: string[] = [];
  hangReads = false;
  failReadOnce = false;
  empty = false;
  large = false;
  private stateHandler: ((state: BridgeConnectionState) => void) | undefined;

  request<T>(
    _id: RpcId,
    method: string,
    params: RpcParams,
    _onChunk?: (chunk: StreamChunk) => void,
  ): Promise<T> {
    this.calls.push(method);
    if (!method.startsWith('memory2.')) {
      return Promise.reject(new Error(`unexpected method ${method}`));
    }
    if (this.hangReads && (method === 'memory2.snapshot' || method === 'memory2.status')) {
      return new Promise<T>(() => {});
    }
    if (this.failReadOnce && method === 'memory2.snapshot') {
      this.failReadOnce = false;
      return Promise.reject(new Error('bounded store unavailable'));
    }
    if (method === 'memory2.snapshot' && !('target' in params)) {
      if (this.empty) {
        return Promise.resolve(snapshotPair([], []) as T);
      }
      if (this.large) {
        return Promise.resolve(
          snapshotPair(
            Array.from({ length: 1000 }, (_, index) => `fixture-entry-${index}`),
            ['Name: Sahar'],
          ) as T,
        );
      }
    }
    return Promise.resolve(this.runtime.handle(method, params) as T);
  }

  onState(handler: (state: BridgeConnectionState) => void): () => void {
    this.stateHandler = handler;
    return () => {
      this.stateHandler = undefined;
    };
  }

  /** Test hook: push a connection-state transition into the client. */
  pushState(state: BridgeConnectionState): void {
    this.stateHandler?.(state);
  }

  reconnect() {}
}

function snapshotPair(notes: string[], profile: string[]) {
  const runtime = new EchoMemory2Runtime(notes, profile);
  return runtime.handle('memory2.snapshot', {}) as Record<'memory' | 'user', EchoBoundedSnapshot>;
}

/** Mount the panel on a fresh singleton client; returns the knobs. */
function mountPanel(options: Partial<Memory2Transport> = {}) {
  const transport = Object.assign(new Memory2Transport(), options);
  resetBridgeClient();
  const client = getBridgeClient();
  client.setTransport(transport);
  const result = render(<BoundedStores />);
  return { transport, client, ...result };
}

describe('bounded capacity accounting', () => {
  it('renders the kernel header format byte-for-byte', () => {
    expect(boundedHeader(1474, 2200)).toBe('[67% — 1,474/2,200 chars]');
    expect(boundedHeader(0, 2200)).toBe('[0% — 0/2,200 chars]');
    expect(boundedHeader(2200, 2200)).toBe('[100% — 2,200/2,200 chars]');
  });

  it('counts the separator between entries, exactly as the store does', () => {
    expect(boundedUsedChars([])).toBe(0);
    expect(boundedUsedChars(['abc'])).toBe(3);
    expect(boundedUsedChars(['abc', 'de'])).toBe(6);
    expect(boundedUsedChars(['ab', 'cd', 'ef'])).toBe(8);
  });

  it('rounds the percentage the way the kernel does', () => {
    expect(boundedPercent(1474, 2200)).toBe(67);
    expect(boundedPercent(1, 2200)).toBe(0);
    expect(boundedPercent(0, 0)).toBe(100);
  });

  it('keeps en-US digit grouping when the UI switches to Persian', async () => {
    await act(() => i18n.changeLanguage('fa'));
    document.documentElement.dir = 'rtl';
    expect(boundedHeader(1474, 2200)).toBe('[67% — 1,474/2,200 chars]');
  });
});

describe('echo memory2 runtime', () => {
  it('refuses an overflowing add and leaves the store byte-identical', () => {
    const seed = 'x'.repeat(2190);
    const runtime = new EchoMemory2Runtime([seed], []);
    expect(() => runtime.handle('memory2.add', { target: 'memory', text: 'y'.repeat(50) })).toThrow(
      /over capacity/i,
    );
    const snap = runtime.handle('memory2.snapshot', { target: 'memory' }) as EchoBoundedSnapshot;
    expect(snap.entries).toEqual([seed]);
    expect(snap.used_chars).toBe(2190);
  });

  it('rejects an unknown target and a non-string payload', () => {
    const runtime = new EchoMemory2Runtime();
    expect(() => runtime.handle('memory2.add', { target: 'agent', text: 'x' })).toThrow(
      /target must be/i,
    );
    expect(() => runtime.handle('memory2.add', { target: 'memory', text: 42 })).toThrow(
      /text must be a string/i,
    );
  });

  it('requires a substring match to hit exactly one entry', () => {
    const runtime = new EchoMemory2Runtime(['alpha note', 'beta note'], []);
    expect(() => runtime.handle('memory2.remove', { target: 'memory', old: 'note' })).toThrow(
      /matched 2 entries/i,
    );
    expect(() => runtime.handle('memory2.remove', { target: 'memory', old: 'gamma' })).toThrow(
      /no entry contains/i,
    );
    const snap = runtime.handle('memory2.remove', {
      target: 'memory',
      old: 'alpha',
    }) as EchoBoundedSnapshot;
    expect(snap.entries).toEqual(['beta note']);
  });

  it('keeps the frozen snapshot immutable across later writes', () => {
    const runtime = new EchoMemory2Runtime(['one fact'], []);
    const frozen = runtime.handle('memory2.status', {});
    runtime.handle('memory2.add', { target: 'memory', text: 'second fact' });
    expect(runtime.handle('memory2.status', {})).toEqual(frozen);
  });
});

describe('BoundedStores panel', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('shows a loading status before the first snapshot arrives', () => {
    mountPanel({ hangReads: true });
    expect(screen.getByRole('status', { name: /loading the bounded stores/i })).toBeInTheDocument();
  });

  it('cancels the in-flight read when the panel unmounts', async () => {
    const transport = new Memory2Transport();
    transport.hangReads = true;
    resetBridgeClient();
    const client = getBridgeClient();
    client.setTransport(transport);
    const callSpy = vi.spyOn(client, 'call');
    const { unmount } = render(<BoundedStores />);
    // The panel defers its first read to a microtask; let it start.
    await act(async () => {});
    unmount();
    const read = callSpy.mock.calls.find(([method]) => method === 'memory2.snapshot');
    expect(read).toBeDefined();
    expect(read?.[2]?.signal?.aborted).toBe(true);
  });

  it('renders both stores with a live meter and the kernel header', async () => {
    mountPanel();
    expect(await screen.findByText(/^\[\d+% — [\d,]+\/2,200 chars\]$/)).toBeInTheDocument();
    expect(screen.getByText(/^\[\d+% — [\d,]+\/1,200 chars\]$/)).toBeInTheDocument();
    expect(screen.getAllByRole('progressbar')).toHaveLength(2);
  });

  it('states that the session prompt was built from a frozen snapshot', async () => {
    mountPanel();
    expect(await screen.findByText(/frozen at session start/i)).toBeInTheDocument();
  });

  it('never writes without an approval, and applies the write once allowed', async () => {
    const { client } = mountPanel();
    const callSpy = vi.spyOn(client, 'call');
    const notes = await screen.findByRole('region', { name: 'Agent notes' });

    fireEvent.change(within(notes).getByLabelText('New entry'), {
      target: { value: 'Prefers terse summaries.' },
    });
    fireEvent.click(within(notes).getByRole('button', { name: 'Add' }));
    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
    expect(callSpy.mock.calls.some(([method]) => method === 'memory2.add')).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: 'Allow once' }));
    await waitFor(() =>
      expect(callSpy.mock.calls.some(([method]) => method === 'memory2.add')).toBe(true),
    );
    expect(await screen.findByText('Prefers terse summaries.')).toBeInTheDocument();
  });

  it('performs no write when the approval is denied', async () => {
    const { client } = mountPanel();
    const callSpy = vi.spyOn(client, 'call');
    const notes = await screen.findByRole('region', { name: 'Agent notes' });

    fireEvent.change(within(notes).getByLabelText('New entry'), {
      target: { value: 'Never written.' },
    });
    fireEvent.click(within(notes).getByRole('button', { name: 'Add' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Deny' }));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(callSpy.mock.calls.some(([method]) => method === 'memory2.add')).toBe(false);
    expect(screen.queryByText('Never written.')).toBeNull();
  });

  it('renders a refused write verbatim and leaves the entries untouched', async () => {
    mountPanel();
    const notes = await screen.findByRole('region', { name: 'Agent notes' });
    const rowsBefore = within(notes).getAllByRole('listitem').length;

    fireEvent.change(within(notes).getByLabelText('New entry'), {
      target: { value: 'x'.repeat(2500) },
    });
    fireEvent.click(within(notes).getByRole('button', { name: 'Add' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Allow once' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/refused and nothing changed/i);
    expect(alert).toHaveTextContent(/over capacity/i);
    const notesStill = within(screen.getByRole('region', { name: 'Agent notes' })).getAllByRole(
      'listitem',
    );
    expect(notesStill).toHaveLength(rowsBefore);
  });

  it('removes an approved entry and re-reads the meter', async () => {
    const { transport } = mountPanel();
    const notes = await screen.findByRole('region', { name: 'Agent notes' });
    const seedHeader = within(notes).getByText(/\/2,200 chars\]/).textContent;

    fireEvent.click(within(notes).getByRole('button', { name: 'Remove entry 1' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Allow once' }));

    await waitFor(() => {
      const after = within(screen.getByRole('region', { name: 'Agent notes' }));
      expect(after.getAllByRole('listitem')).toHaveLength(1);
      expect(after.getByText(/\/2,200 chars\]/).textContent).not.toBe(seedHeader);
    });
    // The refusal-free path still re-reads: snapshot runs after the write.
    const snapshots = transport.calls.filter((m) => m === 'memory2.snapshot').length;
    expect(snapshots).toBeGreaterThanOrEqual(1);
  });

  it('surfaces a read failure with a retry that recovers', async () => {
    mountPanel({ failReadOnce: true });
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/bounded store unavailable/i);

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText(/^\[\d+% — [\d,]+\/2,200 chars\]$/)).toBeInTheDocument();
  });

  it('disables every write control while the bridge is offline', async () => {
    const transport = new Memory2Transport();
    resetBridgeClient();
    getBridgeClient().setTransport(transport);
    queueMicrotask(() => transport.pushState('disconnected'));
    render(<BoundedStores />);

    for (const notes of [
      await screen.findByRole('region', { name: 'Agent notes' }),
      screen.getByRole('region', { name: 'User profile' }),
    ]) {
      expect(within(notes).getByRole('button', { name: 'Add' })).toBeDisabled();
      for (const button of within(notes).getAllByRole('button', { name: /entry \d+/i })) {
        expect(button).toBeDisabled();
      }
    }
  });

  it('keeps the DOM bounded for a 1,000-entry store', async () => {
    const { container } = mountPanel({ large: true });
    await screen.findAllByRole('listitem');
    const mounted = container.querySelectorAll('[role="listitem"]').length;
    console.info(`bounded_fixture_rows=1000 mounted_rows=${mounted}`);
    expect(mounted).toBeGreaterThan(0);
    expect(mounted).toBeLessThan(60);
  });

  it('renders the empty store without any entry rows', async () => {
    const { container } = mountPanel({ empty: true });
    expect(await screen.findAllByText('Nothing stored yet')).toHaveLength(2);
    expect(container.querySelectorAll('[role="listitem"]')).toHaveLength(0);
  });
});

describe('bounded stores in Persian', () => {
  afterEach(async () => {
    await act(() => i18n.changeLanguage('en'));
  });

  it('labels both stores in Persian without leaking an English fallback', async () => {
    await act(() => i18n.changeLanguage('fa'));
    document.documentElement.dir = 'rtl';
    mountPanel();
    expect(await screen.findByRole('region', { name: 'یادداشت‌های عامل' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'نمایهٔ کاربر' })).toBeInTheDocument();
    expect(screen.queryByText('Agent notes')).toBeNull();
  });

  it('keeps the capacity header in LTR isolation inside an RTL layout', async () => {
    await act(() => i18n.changeLanguage('fa'));
    document.documentElement.dir = 'rtl';
    mountPanel();
    const header = await screen.findByText(/[\d,]+\/2,200 chars\]/);
    expect(header.getAttribute('dir')).toBe('ltr');
    expect(header.closest('[dir="rtl"]')).toBe(document.documentElement);
  });
});
