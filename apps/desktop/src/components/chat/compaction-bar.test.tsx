/**
 * Compaction bar (MEM Stage F) — the pinned laws.
 *
 * Arithmetic never goes negative and rounds to whole percentages, a no-op
 * compact invents no row, the nudge hides when off/sent/unknown, offline
 * disables compression, and the bar works against the echo transport.
 */

import { fireEvent, render, screen, within } from '@testing-library/react';
import { act } from 'react';
import i18n from 'i18next';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CompactionBar } from '@/components/chat/compaction-bar';
import {
  nudgeVisible,
  toCompactionRow,
  type CompactionWirePayload,
} from '@/components/chat/compaction-model';
import {
  EchoBridgeTransport,
  getBridgeClient,
  resetBridgeClient,
  type BridgeTransport,
} from '@/lib/bridge/client';
import type { BridgeConnectionState, RpcId, RpcParams, StreamChunk } from '@/lib/bridge/types';

afterEach(async () => {
  await act(() => i18n.changeLanguage('en'));
  document.documentElement.dir = 'ltr';
});

/** A transport answering nudge.status / conversation.compact with knobs. */
class ChatTransport implements BridgeTransport {
  readonly kind = 'echo' as const;
  nudge: { enabled: boolean; sent: boolean; due: boolean } | 'reject' | null = null;
  compactResult: CompactionWirePayload | 'reject' = {
    compacted: true,
    reason: 'explicit',
    before_tokens: 2400,
    after_tokens: 900,
    preserved_messages: 4,
    summary: '[Context compacted] reason=explicit; dropped_messages=2.',
  };
  calls: string[] = [];
  private stateHandler: ((state: BridgeConnectionState) => void) | undefined;

  request<T>(
    _id: RpcId,
    method: string,
    _params: RpcParams,
    _onChunk?: (chunk: StreamChunk) => void,
  ): Promise<T> {
    this.calls.push(method);
    if (method === 'nudge.status') {
      if (this.nudge === 'reject') return Promise.reject(new Error('nudge unreadable'));
      // A healthy, not-due read unless a test configures otherwise.
      return Promise.resolve((this.nudge ?? { enabled: true, sent: false, due: false }) as T);
    }
    if (method === 'conversation.compact') {
      if (this.compactResult === 'reject') {
        return Promise.reject(new Error('compaction refused by the kernel'));
      }
      return Promise.resolve(this.compactResult as T);
    }
    return Promise.reject(new Error(`unexpected method ${method}`));
  }

  onState(handler: (state: BridgeConnectionState) => void): () => void {
    this.stateHandler = handler;
    return () => {
      this.stateHandler = undefined;
    };
  }

  pushState(state: BridgeConnectionState): void {
    this.stateHandler?.(state);
  }

  reconnect() {}
}

function mountBar(options: Partial<ChatTransport> = {}) {
  const transport = Object.assign(new ChatTransport(), options);
  resetBridgeClient();
  getBridgeClient().setTransport(transport);
  return { transport, ...render(<CompactionBar sessionId="sess-1" />) };
}

describe('compaction arithmetic', () => {
  it('reports tokens saved and never goes negative', () => {
    const row = toCompactionRow({ compacted: true, before_tokens: 100, after_tokens: 50 });
    expect(row?.savedTokens).toBe(50);
    const weird = toCompactionRow({ compacted: true, before_tokens: 100, after_tokens: 140 });
    expect(weird?.savedTokens).toBe(0);
  });

  it('reports the reclaimed share as a whole percentage', () => {
    const row = toCompactionRow({ compacted: true, before_tokens: 2400, after_tokens: 900 });
    expect(row?.reclaimedPercent).toBe(63);
  });

  it('ignores a payload that did not actually compact', () => {
    expect(toCompactionRow({ compacted: false, before_tokens: 10, after_tokens: 10 })).toBeNull();
    expect(toCompactionRow({})).toBeNull();
  });

  it('fills in defaults for a partial payload rather than rendering undefined', () => {
    const row = toCompactionRow({ compacted: true, before_tokens: 100, after_tokens: 40 });
    expect(row).toMatchObject({
      preservedMessages: 0,
      reason: 'threshold',
      summary: '',
      savedTokens: 60,
    });
  });
});

describe('nudge visibility', () => {
  it('is hidden when nudges are switched off, even if one is due', () => {
    expect(nudgeVisible({ enabled: false, sent: false, due: true })).toBe(false);
  });

  it('is hidden when the state is unknown', () => {
    expect(nudgeVisible(null)).toBe(false);
  });

  it('is hidden once the nudge has been sent', () => {
    expect(nudgeVisible({ enabled: true, sent: true, due: true })).toBe(false);
  });

  it('is shown only when enabled, due and not yet sent', () => {
    expect(nudgeVisible({ enabled: true, sent: false, due: true })).toBe(true);
  });
});

describe('CompactionBar', () => {
  it('offers the /compress affordance alongside the button', () => {
    mountBar();
    expect(screen.getByRole('button', { name: 'Compress' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '/compress' })).toBeInTheDocument();
  });

  it('records a row with the before/after cost and what was preserved', async () => {
    mountBar();
    fireEvent.click(screen.getByRole('button', { name: 'Compress' }));
    const list = await screen.findByRole('list', { name: 'Compaction events' });
    expect(within(list).getByText('2400 → 900 tokens (63% reclaimed)')).toBeInTheDocument();
    expect(within(list).getByText('4 messages preserved verbatim')).toBeInTheDocument();
    expect(within(list).getByText('1500 tokens freed')).toBeInTheDocument();
    expect(within(list).getByText('Explicit (/compress)')).toBeInTheDocument();
    expect(within(list).getByText(/\[Context compacted\] reason=explicit/)).toBeInTheDocument();
  });

  it('says nothing was compacted instead of inventing a row', async () => {
    const { transport } = mountBar();
    fireEvent.click(screen.getByRole('button', { name: 'Compress' }));
    await screen.findByRole('list', { name: 'Compaction events' });
    transport.compactResult = { compacted: false, before_tokens: 900, after_tokens: 900 };
    fireEvent.click(screen.getByRole('button', { name: 'Compress' }));
    expect(await screen.findByText('Nothing eligible for compaction.')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
  });

  it('renders a refusal without losing the affordance', async () => {
    const { transport } = mountBar();
    transport.compactResult = 'reject';
    fireEvent.click(screen.getByRole('button', { name: 'Compress' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/compaction refused by the kernel/i);
    expect(screen.getByRole('button', { name: 'Compress' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '/compress' })).toBeInTheDocument();
  });

  it('shows the nudge indicator while one is due', async () => {
    mountBar({ nudge: { enabled: true, sent: false, due: true } });
    expect(await screen.findByText('Memory nudge due')).toBeInTheDocument();
  });

  it('hides the nudge indicator when the switch is off', async () => {
    mountBar({ nudge: { enabled: false, sent: false, due: true } });
    await act(async () => {});
    expect(screen.queryByText('Memory nudge due')).toBeNull();
  });

  it('hides the nudge indicator when its state cannot be read', async () => {
    mountBar({ nudge: 'reject' });
    await act(async () => {});
    expect(screen.queryByText('Memory nudge due')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('disables compression while the bridge is offline', async () => {
    const transport = new ChatTransport();
    resetBridgeClient();
    getBridgeClient().setTransport(transport);
    queueMicrotask(() => transport.pushState('disconnected'));
    render(<CompactionBar sessionId="sess-1" />);
    await act(async () => {});
    expect(screen.getByRole('button', { name: 'Compress' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '/compress' })).toBeDisabled();
  });

  it('cancels the nudge read on unmount', async () => {
    const transport = new ChatTransport();
    resetBridgeClient();
    const client = getBridgeClient();
    client.setTransport(transport);
    const callSpy = vi.spyOn(client, 'call');
    const { unmount } = render(<CompactionBar sessionId="sess-1" />);
    await act(async () => {});
    unmount();
    const read = callSpy.mock.calls.find(([method]) => method === 'nudge.status');
    expect(read).toBeDefined();
    expect(read?.[2]?.signal?.aborted).toBe(true);
  });

  it('works against the echo transport end to end', async () => {
    resetBridgeClient();
    const client = getBridgeClient();
    client.setTransport(new EchoBridgeTransport());
    const created = await client.call<{ session_id: string }>('session.create', {
      title: 'Long session',
    });
    render(<CompactionBar sessionId={created.session_id} />);
    fireEvent.click(screen.getByRole('button', { name: '/compress' }));
    expect(await screen.findByText('2400 → 900 tokens (63% reclaimed)')).toBeInTheDocument();
    expect(screen.getByText('4 messages preserved verbatim')).toBeInTheDocument();
    expect(screen.getByText('1500 tokens freed')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Compress' })).toBeInTheDocument();
  });
});

describe('CompactionBar in Persian', () => {
  it('renders the bar in Persian with no English fallback', async () => {
    await act(() => i18n.changeLanguage('fa'));
    document.documentElement.dir = 'rtl';
    mountBar();
    expect(screen.getByRole('button', { name: 'فشرده کن' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'فشرده‌سازی بافتار' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Compress' })).toBeNull();
  });

  it('keeps the /compress token readable inside RTL', async () => {
    await act(() => i18n.changeLanguage('fa'));
    document.documentElement.dir = 'rtl';
    mountBar();
    const chip = screen.getByRole('button', { name: '/compress' });
    expect(chip.textContent).toBe('/compress');
    expect(chip.className).toContain('ltr-island');
  });
});
