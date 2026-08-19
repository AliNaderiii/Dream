/**
 * Deterministic echo runtime for `commerce.*` and `route.resolve` (S05).
 *
 * Browser dev and vitest have no sidecar, so the plan/usage/route surfaces
 * render against this in-memory model. The echo transport *is* the offline
 * backend, so the honest defaults are: the `local` plan (free, unlimited),
 * and the `echo` route (nothing leaves the machine). No numeric IRR price is
 * ever fabricated here — the only price carried is `0` for the free plan.
 *
 * The real values come from the Python sidecar via `commerce.plan`,
 * `commerce.usage` and `route.resolve` in `dream/bridge/methods.py`.
 */

import type { CommercePlanDto, CommerceUsageDto, RouteDto } from './types';

/** The echo transport's own plan: free, unlimited, fully local. */
const ECHO_PLAN: CommercePlanDto = {
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

/** No ledger exists in echo mode: usage is unlimited and reads as 0 used. */
const ECHO_USAGE: CommerceUsageDto = {
  plan_id: 'local',
  window: null,
  used: 0,
  limit: null,
  remaining: null,
  unlimited: true,
};

/** Mirrors the `echo` route in `dream/router.py`, including its sentences. */
const ECHO_ROUTE: RouteDto = {
  name: 'echo',
  leaves_machine: false,
  sentence_en: 'Route: echo — fully offline echo backend; no data leaves this machine.',
  sentence_fa:
    'مسیر: آفلاین — این نوبت به صورت کاملاً آفلاین پردازش می‌شود؛ هیچ داده‌ای از این دستگاه خارج نمی‌شود.',
};

/** Deterministic in-memory implementation of the S05 RPC family. */
export class EchoCommerceRuntime {
  /** `commerce.plan` — always the local plan in echo mode. */
  plan(): CommercePlanDto {
    return { ...ECHO_PLAN, limits: { ...ECHO_PLAN.limits } };
  }

  /** `commerce.usage` — unlimited, nothing consumed in echo mode. */
  usage(): CommerceUsageDto {
    return { ...ECHO_USAGE };
  }

  /** `route.resolve` — the echo route: fully offline. */
  route(): RouteDto {
    return { ...ECHO_ROUTE };
  }
}
