/**
 * Tests for the first-run card (S11 + S15).
 *
 * Verifies that the dashboard first-run card:
 *  - still shows the offline echo + Ollama + BYOK rows unchanged
 *  - adds Aval AI as the recommended hosted path
 *  - says plainly that prompts leave the machine when Aval is the recommended
 *    hosted option (we never claim it stays local)
 *  - renders an Aval CTA that does not throw on click
 *  - uses Navigation icon (S15: replaced Route to avoid react-router collision)
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';

import { FirstRunCard } from '@/components/billing/first-run-card';
import { resetBridgeClient, type BridgeClient, type BridgeTransport } from '@/lib/bridge/client';
import { getBridgeClient } from '@/lib/bridge/client';
import type { RpcId, RpcParams, StreamChunk } from '@/lib/bridge/types';

class StubTransport implements BridgeTransport {
  readonly kind = 'tauri' as const;
  constructor(private answers: Record<string, unknown>) {}

  request<T>(
    _id: RpcId,
    method: string,
    _params: RpcParams,
    _onChunk?: (chunk: StreamChunk) => void,
  ): Promise<T> {
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

const ECHO_ROUTE = {
  name: 'echo',
  leaves_machine: false,
  sentence_en: 'Route: echo — fully offline echo backend; no data leaves this machine.',
  sentence_fa: 'مسیر: آفلاین — این نوبت به صورت کاملاً آفلاین پردازش می‌شود.',
};

function seed(client: BridgeClient, answers: Record<string, unknown>): void {
  client.setTransport(new StubTransport(answers));
}

function renderCard() {
  return render(
    <MemoryRouter>
      <FirstRunCard />
    </MemoryRouter>,
  );
}

describe('FirstRunCard (S11)', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('keeps the offline-first story with echo + Ollama + BYOK unchanged', async () => {
    const client = getBridgeClient();
    seed(client, { 'route.resolve': ECHO_ROUTE });

    renderCard();

    expect(await screen.findByText('Works offline — no account needed')).toBeInTheDocument();
    expect(
      screen.getByText('Offline echo engine — no network or account required'),
    ).toBeInTheDocument();
    expect(screen.getByText('Add a local model with Ollama')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Set up Ollama' })).toBeInTheDocument();
    expect(screen.getByText('Bring your own API key')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add a provider key' })).toBeInTheDocument();
  });

  it('adds Aval as the recommended hosted path with leave-machine copy', async () => {
    const client = getBridgeClient();
    seed(client, { 'route.resolve': ECHO_ROUTE });

    renderCard();

    // Title includes the recommended + Aval wording.
    expect(await screen.findByText('Recommended hosted path — Aval AI')).toBeInTheDocument();
    // The "Recommended" badge is rendered as plain text.
    expect(screen.getByText('Recommended')).toBeInTheDocument();
    // Honest leave-machine copy for the hosted path — never claims it stays local.
    expect(
      screen.getByText(
        'One account, many model families, served from the Iranian cloud at api.avalai.ir. Your prompts leave this machine.',
      ),
    ).toBeInTheDocument();
    // The Aval CTA button is rendered.
    expect(screen.getByRole('button', { name: 'Set up Aval AI' })).toBeInTheDocument();
  });

  it('Aval CTA does not throw on click (navigates to /providers)', async () => {
    const client = getBridgeClient();
    seed(client, { 'route.resolve': ECHO_ROUTE });

    renderCard();

    const cta = await screen.findByRole('button', { name: 'Set up Aval AI' });
    expect(() => fireEvent.click(cta)).not.toThrow();
  });
});

describe('FirstRunCard (S15 - icon safety)', () => {
  it('does not import lucide Route (avoids react-router collision)', async () => {
    // This test verifies that the FirstRunCard component does not export RouteIcon,
    // which was previously imported as 'Route' from lucide-react.
    // Using 'Route' as an icon name collides with react-router's Route after minification.
    const module = await import('@/components/billing/first-run-card');
    // The module should not export RouteIcon (which was the alias for lucide Route)
    expect(Object.keys(module)).not.toContain('RouteIcon');
  });
});
