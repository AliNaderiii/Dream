/**
 * Tests for the CouncilButton (S11).
 *
 * Verifies that:
 *  - The button is rendered with the locale-backed "Council review" label.
 *  - Clicking it with composer text calls `council.run` with that prompt.
 *  - Clicking it with empty composer + last user message uses the last
 *    user message as the prompt.
 *  - A ledger `refusal` is shown inline; the button does not throw.
 *  - The Send / conversation.send path is *not* triggered by the council
 *    button (we never call `conversation.send` from this component).
 *  - Empty input + empty transcript shows the locale-backed empty hint
 *    instead of calling `council.run`.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';

import { CouncilButton } from '@/components/chat/council-button';
import { resetBridgeClient, type BridgeClient, type BridgeTransport } from '@/lib/bridge/client';
import { getBridgeClient } from '@/lib/bridge/client';
import type { Message } from '@/types';
import type { RpcId, RpcParams, StreamChunk } from '@/lib/bridge/types';

class StubTransport implements BridgeTransport {
  readonly kind = 'tauri' as const;
  /** Records every method invoked so we can assert which RPCs ran. */
  readonly calls: { method: string; params: RpcParams }[] = [];
  constructor(private answers: Record<string, unknown>) {}

  request<T>(
    _id: RpcId,
    method: string,
    params: RpcParams,
    _onChunk?: (chunk: StreamChunk) => void,
  ): Promise<T> {
    this.calls.push({ method, params: params ?? {} });
    if (!(method in this.answers)) {
      throw new Error(`StubTransport: no answer for ${method}`);
    }
    return Promise.resolve(this.answers[method] as T);
  }

  onState(): () => void {
    return () => {};
  }

  reconnect(): void {}
}

function seed(client: BridgeClient, transport: StubTransport): void {
  client.setTransport(transport);
}

function renderButton(props: { input?: string; messages?: Message[] } = {}) {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route
          path="*"
          element={<CouncilButton input={props.input ?? ''} messages={props.messages ?? []} />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('CouncilButton (S11)', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('renders a "Council review" button next to Send', () => {
    renderButton();
    expect(screen.getByRole('button', { name: 'Council review' })).toBeInTheDocument();
  });

  it('calls council.run with the composer text when the button is clicked', async () => {
    const client = getBridgeClient();
    const transport = new StubTransport({
      'council.run': {
        council_id: 'c-1',
        pipeline_id: 'p-1',
        members: [],
        winner: 'w',
        turns_consumed: 3,
        leaves_machine_any: false,
        sentence_en: 'Council done.',
        sentence_fa: 'شورا تمام شد.',
        refusal: null,
      },
    });
    seed(client, transport);

    renderButton({ input: 'Should we ship weekly?' });

    fireEvent.click(screen.getByRole('button', { name: 'Council review' }));

    await waitFor(() => {
      const calls = transport.calls.filter((c) => c.method === 'council.run');
      expect(calls).toHaveLength(1);
      expect(calls[0].params).toEqual({ prompt: 'Should we ship weekly?' });
    });
    // The council button must never call conversation.send.
    expect(transport.calls.some((c) => c.method === 'conversation.send')).toBe(false);
  });

  it('falls back to the last user message when the composer is empty', async () => {
    const client = getBridgeClient();
    const transport = new StubTransport({
      'council.run': {
        council_id: 'c-2',
        pipeline_id: 'p-2',
        members: [],
        winner: null,
        turns_consumed: 3,
        leaves_machine_any: false,
        sentence_en: '...',
        sentence_fa: '...',
        refusal: null,
      },
    });
    seed(client, transport);

    const messages: Message[] = [
      {
        id: 'u1',
        role: 'user',
        content: 'Earlier prompt',
        createdAt: 1,
      },
      {
        id: 'a1',
        role: 'assistant',
        content: 'Earlier reply',
        createdAt: 2,
      },
      {
        id: 'u2',
        role: 'user',
        content: 'Most recent user prompt',
        createdAt: 3,
      },
    ];
    renderButton({ input: '', messages });

    fireEvent.click(screen.getByRole('button', { name: 'Council review' }));

    await waitFor(() => {
      const calls = transport.calls.filter((c) => c.method === 'council.run');
      expect(calls).toHaveLength(1);
      expect(calls[0].params).toEqual({ prompt: 'Most recent user prompt' });
    });
  });

  it('shows the empty hint and does not call council.run when both are empty', async () => {
    const client = getBridgeClient();
    const transport = new StubTransport({});
    seed(client, transport);

    renderButton({ input: '', messages: [] });

    fireEvent.click(screen.getByRole('button', { name: 'Council review' }));

    expect(
      await screen.findByText('Type a message first to send it to the council.'),
    ).toBeInTheDocument();
    expect(transport.calls.filter((c) => c.method === 'council.run')).toHaveLength(0);
  });

  it('shows a refusal banner when the ledger refuses the council', async () => {
    const client = getBridgeClient();
    const transport = new StubTransport({
      'council.run': {
        council_id: 'c-3',
        pipeline_id: 'p-3',
        members: [],
        winner: null,
        turns_consumed: 0,
        leaves_machine_any: false,
        sentence_en: '',
        sentence_fa: '',
        refusal: 'سهمیهٔ روزانهٔ شما تمام شده است.',
      },
    });
    seed(client, transport);

    renderButton({ input: 'Refuse me' });

    fireEvent.click(screen.getByRole('button', { name: 'Council review' }));

    expect(
      await screen.findByText(/Council refused: سهمیهٔ روزانهٔ شما تمام شده است\./),
    ).toBeInTheDocument();
    // No winner text was fabricated; council.run completed without throwing.
    expect(transport.calls.filter((c) => c.method === 'council.run')).toHaveLength(1);
  });
});
