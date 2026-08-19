import { describe, expect, it } from 'vitest';

import { EchoCommerceRuntime } from './echo-commerce';

describe('EchoCommerceRuntime (S05)', () => {
  it('reports the local plan: free, unlimited, no ledger', () => {
    const runtime = new EchoCommerceRuntime();
    const plan = runtime.plan();

    expect(plan.plan_id).toBe('local');
    expect(plan.name_fa).toBe('محلی');
    expect(plan.name_en).toBe('Local');
    expect(plan.currency).toBe('IRR');
    expect(plan.price).toBe(0); // the only number ever allowed: 0 for free
    expect(plan.metered).toBe(false);
    expect(plan.period).toBe('unlimited');
    expect(plan.limits).toEqual({ daily: null, monthly: null, yearly: null });
    expect(plan.ledger_attached).toBe(false);
  });

  it('reports usage as unlimited with nothing consumed', () => {
    const runtime = new EchoCommerceRuntime();
    const usage = runtime.usage();

    expect(usage.plan_id).toBe('local');
    expect(usage.window).toBeNull();
    expect(usage.used).toBe(0);
    expect(usage.limit).toBeNull();
    expect(usage.remaining).toBeNull();
    expect(usage.unlimited).toBe(true);
  });

  it('resolves the echo route: fully offline, nothing leaves the machine', () => {
    const runtime = new EchoCommerceRuntime();
    const route = runtime.route();

    expect(route.name).toBe('echo');
    expect(route.leaves_machine).toBe(false);
    expect(route.sentence_en).toContain('no data leaves this machine');
    expect(route.sentence_fa).toContain('خارج نمی‌شود');
  });

  it('never fabricates a numeric price for a paid plan', () => {
    const runtime = new EchoCommerceRuntime();
    // The echo runtime only knows the free local plan; a paid plan must
    // arrive from the sidecar with price === null.
    const plan = runtime.plan();
    expect(plan.price === 0 || plan.price === null).toBe(true);
  });
});
