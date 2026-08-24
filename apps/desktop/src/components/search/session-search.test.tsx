/**
 * Session search (MEM Stage F) — the pinned laws.
 *
 * Snippet parsing is text-only, matching runs through the shared Persian
 * normalizer (Arabic-spelled queries hit Farsi-spelling transcripts and the
 * highlight keeps the user's own spelling), a corrupt index refuses out
 * loud and recovers on rebuild, and an empty result set is not a failure.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { act } from 'react';
import i18n from 'i18next';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CommandPalette } from '@/components/shared/command-palette';
import {
  markMatches,
  parseSnippet,
  hasHighlight,
  tokenizeQuery,
} from '@/components/search/snippet-model';
import { SessionSearch } from '@/components/search/session-search';
import { EchoSearchRuntime } from '@/lib/bridge/echo-search';
import { getBridgeClient, resetBridgeClient, type BridgeTransport } from '@/lib/bridge/client';
import { useAppStore } from '@/stores/use-app-store';
import type { BridgeConnectionState, RpcId, RpcParams, StreamChunk } from '@/lib/bridge/types';

afterEach(async () => {
  await act(() => i18n.changeLanguage('en'));
  document.documentElement.dir = 'ltr';
  useAppStore.setState({ sessionSearchOpen: false, commandPaletteOpen: false });
});

/** A transport answering only the search.sessions family, with knobs. */
class SearchTransport implements BridgeTransport {
  readonly kind = 'echo' as const;
  readonly runtime = new EchoSearchRuntime();
  delayQuery = false;
  manyResults = false;
  private stateHandler: ((state: BridgeConnectionState) => void) | undefined;

  request<T>(
    _id: RpcId,
    method: string,
    params: RpcParams,
    _onChunk?: (chunk: StreamChunk) => void,
  ): Promise<T> {
    if (!method.startsWith('search.sessions.')) {
      return Promise.reject(new Error(`unexpected method ${method}`));
    }
    if (this.manyResults && method === 'search.sessions.query') {
      const results = Array.from({ length: 1000 }, (_, index) => ({
        session_id: `sess-${index}`,
        title: `Conversation ${index}`,
        snippet: `matched text ${index}`,
        score: 1,
        matched_in_title: false,
        updated_at: 1_780_000_000 + index,
        source: 'desktop',
      }));
      return Promise.resolve({ results } as T);
    }
    if (this.delayQuery && method === 'search.sessions.query') {
      return new Promise<T>((resolve) => {
        setTimeout(() => resolve(this.runtime.handle(method, params) as T), 400);
      });
    }
    return Promise.resolve(this.runtime.handle(method, params) as T);
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

function mountSearch(options: Partial<SearchTransport> = {}) {
  const transport = Object.assign(new SearchTransport(), options);
  resetBridgeClient();
  getBridgeClient().setTransport(transport);
  useAppStore.setState({ sessionSearchOpen: true });
  return { transport, ...render(<SessionSearch onOpenSession={() => {}} />) };
}

describe('snippet parsing', () => {
  it('splits marked runs from plain runs', () => {
    expect(parseSnippet('the [quick] fox')).toEqual([
      { text: 'the ', highlight: false },
      { text: 'quick', highlight: true },
      { text: ' fox', highlight: false },
    ]);
  });

  it('returns nothing for an empty snippet', () => {
    expect(parseSnippet('')).toEqual([]);
  });

  it('treats an unbalanced marker as plain text rather than blanking the snippet', () => {
    expect(parseSnippet('oops [unclosed')).toEqual([{ text: 'oops [unclosed', highlight: false }]);
  });

  it('keeps escaped literal brackets out of the highlight', () => {
    const segments = parseSnippet('a [[b]] and [real] marks');
    expect(segments).toContainEqual({ text: 'a [b] and ', highlight: false });
    expect(segments).toContainEqual({ text: 'real', highlight: true });
    expect(segments.every((segment) => !segment.text.includes('[['))).toBe(true);
  });

  it('reports whether a snippet carries any highlight', () => {
    expect(hasHighlight(parseSnippet('no marks here'))).toBe(false);
    expect(hasHighlight(parseSnippet('one [mark] here'))).toBe(true);
  });

  it('never emits markup — the segments are text only', () => {
    const segments = parseSnippet('the [match] text');
    expect(segments.length).toBeGreaterThan(0);
    for (const segment of segments) {
      expect(typeof segment.text).toBe('string');
      expect(segment.text).not.toContain('<');
    }
  });
});

describe('normalized matching in the original text', () => {
  it('tokenises a query through the shared Persian normalizer', () => {
    expect(tokenizeQuery('\u0643\u062a\u0627\u0628')).toEqual(['\u06a9\u062a\u0627\u0628']);
    expect(tokenizeQuery('!!!')).toEqual([]);
    expect(tokenizeQuery('\u06f1\u06f2\u06f3 books')).toEqual(['123', 'books']);
  });

  it('highlights the Persian spelling for an Arabic-spelled query', () => {
    const marked = markMatches(
      '\u062f\u0631\u0628\u0627\u0631\u0647\u0654 \u06a9\u062a\u0627\u0628\u200c\u0647\u0627\u06cc \u062a\u0627\u0631\u06cc\u062e',
      '\u0643\u062a\u0627\u0628',
    );
    expect(marked).toContain('[\u06a9\u062a\u0627\u0628\u200c\u0647\u0627\u06cc]');
    expect(marked).not.toContain('\u0643\u062a\u0627\u0628');
  });

  it('highlights inside an English sentence too', () => {
    expect(markMatches('rolled out the bridge today', 'bridge')).toContain('[bridge]');
  });
});

describe('echo search runtime', () => {
  it('fails closed when the query normalises to no tokens', () => {
    const runtime = new EchoSearchRuntime();
    expect(() => runtime.handle('search.sessions.query', { query: '!!!' })).toThrow(
      /no searchable tokens/i,
    );
  });

  it('rejects a non-string query at the boundary', () => {
    const runtime = new EchoSearchRuntime();
    expect(() => runtime.handle('search.sessions.query', { query: 42 })).toThrow(
      /query must be a string/i,
    );
  });

  it('refuses every read while the index is corrupt, and recovers on rebuild', () => {
    const runtime = new EchoSearchRuntime();
    runtime.setCorrupt(true);
    expect(() => runtime.handle('search.sessions.status', {})).toThrow(/corrupt|unreadable/i);
    expect(() => runtime.handle('search.sessions.query', { query: 'bridge' })).toThrow(
      /corrupt|unreadable/i,
    );
    expect(runtime.handle('search.sessions.rebuild', {})).toEqual({ rebuilt: 3 });
    expect(runtime.handle('search.sessions.status', {})).toEqual({ healthy: true, documents: 3 });
  });

  it('ranks a title match above a body match', () => {
    const runtime = new EchoSearchRuntime();
    const out = runtime.handle('search.sessions.query', { query: 'bridge' }) as {
      results: Array<{ session_id: string }>;
    };
    expect(out.results.map((hit) => hit.session_id)).toEqual(['sess-bridge', 'sess-budget']);
  });

  it('finds a Persian conversation from an Arabic-spelled query', () => {
    const runtime = new EchoSearchRuntime();
    const out = runtime.handle('search.sessions.query', {
      query: '\u0643\u062a\u0627\u0628',
    }) as { results: Array<{ session_id: string; snippet: string }> };
    expect(out.results).toHaveLength(1);
    expect(out.results[0].session_id).toBe('sess-books');
    expect(out.results[0].snippet).toContain('[\u06a9\u062a\u0627\u0628\u200c\u0647\u0627\u06cc]');
    expect(out.results[0].snippet).not.toContain('\u0643\u062a\u0627\u0628');
  });
});

describe('SessionSearch dialog', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('prompts before anything has been typed', async () => {
    mountSearch();
    const dialog = await screen.findByRole('dialog', { name: 'Conversation search' });
    expect(within(dialog).getByText(/Ctrl\/\u2318\+P opens this search/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/No conversations match/i)).toBeInTheDocument();
    expect(within(dialog).queryByRole('alert')).toBeNull();
  });

  it('reports index health and the document count', async () => {
    mountSearch();
    expect(await screen.findByText(/Index healthy — 3 conversations/i)).toBeInTheDocument();
  });

  it('finds a Persian conversation from an Arabic-spelled query and highlights it', async () => {
    mountSearch();
    const input = await screen.findByLabelText('Search conversations');
    fireEvent.change(input, { target: { value: '\u0643\u062a\u0627\u0628' } });
    const mark = await screen.findByText('\u06a9\u062a\u0627\u0628\u200c\u0647\u0627\u06cc');
    expect(mark.tagName).toBe('MARK');
    expect(screen.getByText('Book notes')).toBeInTheDocument();
  });

  it('reports an empty result set without claiming a failure', async () => {
    mountSearch();
    const input = await screen.findByLabelText('Search conversations');
    fireEvent.change(input, { target: { value: 'zzzz-no-such-thing' } });
    expect(await screen.findByText(/No conversations match/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('renders the index refusal instead of an empty list', async () => {
    const { transport } = mountSearch();
    transport.runtime.setCorrupt(true);
    const input = await screen.findByLabelText('Search conversations');
    fireEvent.change(input, { target: { value: 'bridge' } });
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/corrupt|unreadable/i);
  });

  it('recovers after a rebuild', async () => {
    const { transport } = mountSearch();
    transport.runtime.setCorrupt(true);
    const input = await screen.findByLabelText('Search conversations');
    fireEvent.change(input, { target: { value: 'bridge' } });
    const alert = await screen.findByRole('alert');
    fireEvent.click(within(alert).getByRole('button', { name: 'Rebuild index' }));
    expect(await screen.findByText('Bridge rollout runbook')).toBeInTheDocument();
  });

  it('shows a searching state while the index is slow', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      mountSearch({ delayQuery: true });
      const input = await screen.findByLabelText('Search conversations');
      fireEvent.change(input, { target: { value: 'bridge' } });
      await act(() => Promise.resolve(vi.advanceTimersByTime(300)));
      expect(screen.getAllByText(/Searching…/i).length).toBeGreaterThan(0);
      await act(() => Promise.resolve(vi.advanceTimersByTime(500)));
      expect(await screen.findByText('Bridge rollout runbook')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('disables rebuild while the bridge is offline', async () => {
    const transport = new SearchTransport();
    transport.runtime.setCorrupt(true);
    resetBridgeClient();
    getBridgeClient().setTransport(transport);
    useAppStore.setState({ sessionSearchOpen: true });
    queueMicrotask(() => transport.pushState('disconnected'));
    render(<SessionSearch onOpenSession={() => {}} />);
    const input = await screen.findByLabelText('Search conversations');
    fireEvent.change(input, { target: { value: 'bridge' } });
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByRole('button', { name: 'Rebuild index' })).toBeDisabled();
  });

  it('keeps a 1,000-result set below the mounted-row bound', async () => {
    mountSearch({ manyResults: true });
    const input = await screen.findByLabelText('Search conversations');
    fireEvent.change(input, { target: { value: 'bridge' } });
    await screen.findAllByRole('listitem');
    // The dialog renders in a portal attached to the body, not the container.
    const mounted = document.body.querySelectorAll('[role="listitem"]').length;
    console.info(`search_fixture_rows=1000 mounted_rows=${mounted}`);
    expect(mounted).toBeGreaterThan(0);
    expect(mounted).toBeLessThan(60);
  });
});

describe('SessionSearch in Persian', () => {
  it('renders the dialog chrome in Persian without an English fallback', async () => {
    await act(() => i18n.changeLanguage('fa'));
    document.documentElement.dir = 'rtl';
    mountSearch();
    expect(await screen.findByRole('dialog', { name: 'جستجوی گفتگوها' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('جستجوی گفتگوها…')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Search conversations…')).toBeNull();
  });

  it('keeps an English title readable inside an RTL dialog', async () => {
    await act(() => i18n.changeLanguage('fa'));
    document.documentElement.dir = 'rtl';
    mountSearch();
    const input = await screen.findByRole('searchbox', { name: 'جستجوی گفتگوها' });
    fireEvent.change(input, { target: { value: 'bridge' } });
    const title = await screen.findByText('Bridge rollout runbook');
    expect(title.getAttribute('dir')).toBe('auto');
    expect(title.className).toContain('bidi-isolate');
  });
});

describe('conversation results inside the command palette', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  function mountPalette(onOpenSession: (id: string) => void) {
    const transport = new SearchTransport();
    resetBridgeClient();
    getBridgeClient().setTransport(transport);
    useAppStore.setState({ commandPaletteOpen: true });
    return {
      transport,
      ...render(<CommandPalette commands={[]} onOpenSession={onOpenSession} />),
    };
  }

  it('lists index hits under their own group and opens one', async () => {
    const openSpy = vi.fn();
    mountPalette(openSpy);
    const input = await screen.findByLabelText('Search commands');
    fireEvent.change(input, { target: { value: 'bridge' } });
    expect(await screen.findByText('Conversations')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Bridge rollout runbook'));
    expect(openSpy).toHaveBeenCalledWith('sess-bridge');
    expect(useAppStore.getState().commandPaletteOpen).toBe(false);
  });

  it('shows the index refusal in the palette rather than dropping it', async () => {
    const { transport } = mountPalette(() => {});
    transport.runtime.setCorrupt(true);
    const input = await screen.findByLabelText('Search commands');
    fireEvent.change(input, { target: { value: 'bridge' } });
    const group = await screen.findByText('Conversations');
    const alert = await waitFor(() => {
      const found = screen.getByRole('alert');
      expect(found).toBeInTheDocument();
      return found;
    });
    expect(group).toBeInTheDocument();
    expect(alert).toHaveTextContent(/corrupt|unreadable/i);
  });
});
