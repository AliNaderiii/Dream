import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { BillingSummary } from '@/components/billing/billing-summary';
import { resetBridgeClient, type BridgeClient, type BridgeTransport } from '@/lib/bridge/client';
import { getBridgeClient } from '@/lib/bridge/client';
import type { RpcId, RpcParams, StreamChunk } from '@/lib/bridge/types';

/** A transport with canned per-method answers for the S05 RPCs. */
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

const LOCAL_PLAN = {
  plan_id: 'local',
  name_fa: 'محلی',
  name_en: 'Local',
  currency: 'IRR',
  price: 0,
  price_note: 'free — unlimited',
  metered: false,
  period: 'unlimited',
  limits: { daily: null, monthly: null, yearly: null },
  ledger_attached: false,
};

const GUEST_PLAN = {
  ...LOCAL_PLAN,
  plan_id: 'guest',
  name_fa: 'مهمان',
  name_en: 'Guest',
  metered: true,
  period: 'day',
  limits: { daily: 20, monthly: null, yearly: null },
  ledger_attached: true,
};

const ECHO_ROUTE = {
  name: 'echo',
  leaves_machine: false,
  sentence_en: 'Route: echo — fully offline echo backend; no data leaves this machine.',
  sentence_fa: 'مسیر: آفلاین — این نوبت به صورت کاملاً آفلاین پردازش می‌شود.',
};

const HOSTED_ROUTE = {
  name: 'hosted',
  leaves_machine: true,
  sentence_en:
    'Route: hosted — this turn is sent to a cloud model service; your message leaves this machine.',
  sentence_fa: 'مسیر: سرویس ابری — پیام شما از این دستگاه خارج می‌شود.',
};

function seed(client: BridgeClient, answers: Record<string, unknown>): void {
  client.setTransport(new StubTransport(answers));
}

describe('BillingSummary', () => {
  beforeEach(() => {
    resetBridgeClient();
  });

  it('renders plan, period, unlimited usage, free price, and the local route', async () => {
    const client = getBridgeClient();
    seed(client, {
      'commerce.plan': LOCAL_PLAN,
      'commerce.usage': {
        plan_id: 'local',
        window: null,
        used: 0,
        limit: null,
        remaining: null,
        unlimited: true,
      },
      'route.resolve': ECHO_ROUTE,
    });

    render(<BillingSummary />);

    // Plan name in both languages.
    expect(await screen.findByText('محلی')).toBeInTheDocument();
    expect(screen.getByText('(Local)')).toBeInTheDocument();
    // Period and usage.
    expect(screen.getByText('Unlimited')).toBeInTheDocument();
    expect(screen.getByText('Unlimited turns')).toBeInTheDocument();
    // Price: only "Free" for price === 0.
    expect(screen.getByText('Free')).toBeInTheDocument();
    expect(screen.queryByText(/IRR|تومان|rial/i)).not.toBeInTheDocument();
    // Route: offline, stays local.
    expect(screen.getByText('Offline echo')).toBeInTheDocument();
    expect(screen.getByText('Prompts never leave this machine')).toBeInTheDocument();
    // Disabled upgrade affordance.
    expect(screen.getByRole('button', { name: 'Upgrade (coming)' })).toBeDisabled();
  });

  it('shows used/limit turns and a TBD price for a metered plan', async () => {
    const client = getBridgeClient();
    seed(client, {
      'commerce.plan': GUEST_PLAN,
      'commerce.usage': {
        plan_id: 'guest',
        window: 'day',
        used: 3,
        limit: 20,
        remaining: 17,
        unlimited: false,
      },
      'route.resolve': ECHO_ROUTE,
    });

    render(<BillingSummary />);

    expect(await screen.findByText('3 of 20 turns used')).toBeInTheDocument();
    expect(screen.getByText('Per day')).toBeInTheDocument();
    // Guest is free too.
    expect(screen.getByText('Free')).toBeInTheDocument();
  });

  it('never renders a numeric IRR for a paid plan — only the TBD note', async () => {
    const client = getBridgeClient();
    seed(client, {
      'commerce.plan': {
        ...GUEST_PLAN,
        plan_id: 'individual_monthly',
        name_fa: 'ماهانه فردی',
        name_en: 'Individual (monthly)',
        price: null,
        price_note: 'TBD after cost measurement',
        period: 'month',
        limits: { daily: null, monthly: 1000, yearly: null },
      },
      'commerce.usage': {
        plan_id: 'individual_monthly',
        window: 'month',
        used: 10,
        limit: 1000,
        remaining: 990,
        unlimited: false,
      },
      'route.resolve': HOSTED_ROUTE,
    });

    render(<BillingSummary />);

    expect(await screen.findByText('TBD after cost measurement')).toBeInTheDocument();
    // No number, no currency, no invented toman/rial anywhere.
    expect(screen.queryByText(/IRR|تومان|rial/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/\d[\d,]*\s*(IRR|تومان|rial)/i)).not.toBeInTheDocument();
  });

  it('says plainly that prompts leave the machine when the route is hosted', async () => {
    const client = getBridgeClient();
    seed(client, {
      'commerce.plan': LOCAL_PLAN,
      'commerce.usage': {
        plan_id: 'local',
        window: null,
        used: 0,
        limit: null,
        remaining: null,
        unlimited: true,
      },
      'route.resolve': HOSTED_ROUTE,
    });

    render(<BillingSummary />);

    await waitFor(() => {
      expect(screen.getByText('Prompts leave this machine')).toBeInTheDocument();
    });
    // The route sentence from the router is shown verbatim.
    expect(screen.getByText(HOSTED_ROUTE.sentence_en)).toBeInTheDocument();
  });

  it('recovers from a failed load with Retry', async () => {
    const client = getBridgeClient();
    client.setTransport(new StubTransport({}));
    render(<BillingSummary />);

    expect(await screen.findByText('Plan info is unavailable right now.')).toBeInTheDocument();

    // Now the sidecar "comes back": swap in working answers and retry.
    seed(client, {
      'commerce.plan': LOCAL_PLAN,
      'commerce.usage': {
        plan_id: 'local',
        window: null,
        used: 0,
        limit: null,
        remaining: null,
        unlimited: true,
      },
      'route.resolve': ECHO_ROUTE,
    });
    const retry = screen.getByRole('button', { name: 'Retry' });
    act(() => {
      retry.click();
    });

    expect(await screen.findByText('محلی')).toBeInTheDocument();
  });
});
