/**
 * Plan & usage summary (S05).
 *
 * Shows the honest commercial surface of Dream in one card:
 *
 * - the active plan (FA + EN names, quota period);
 * - turns used / limit for the current window (∞ for the unlimited local plan);
 * - the price — only ever `0` for free plans, otherwise the
 *   `TBD after cost measurement` note. A made-up IRR number is never rendered;
 * - the resolved model route and an explicit "does data leave this machine?"
 *   sentence straight from `dream/router.py` (via the sidecar).
 *
 * Data comes from `commerce.plan`, `commerce.usage` and `route.resolve`.
 * In browser echo mode the deterministic `EchoCommerceRuntime` reports the
 * honest offline defaults (local plan, echo route).
 */

import {
  CircleDollarSign,
  Infinity as InfinityIcon,
  LoaderCircle,
  Route as RouteIcon,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useBridge } from '@/lib/bridge/hooks';
import { isRtlLocale, useTranslation } from '@/lib/i18n';
import type { CommercePlanDto, CommerceUsageDto, RouteDto } from '@/lib/bridge/types';

type LoadState =
  | { status: 'loading' }
  | { status: 'error' }
  | {
      status: 'ready';
      plan: CommercePlanDto;
      usage: CommerceUsageDto;
      route: RouteDto;
    };

/** Localised label for the quota period. */
function periodKey(period: CommercePlanDto['period']): string {
  switch (period) {
    case 'day':
      return 'billing.periodDay';
    case 'month':
      return 'billing.periodMonth';
    case 'year':
      return 'billing.periodYear';
    default:
      return 'billing.periodUnlimited';
  }
}

/** Localised label for the resolved route name. */
function routeNameKey(route: RouteDto['name']): string {
  switch (route) {
    case 'hosted':
      return 'billing.routeHosted';
    case 'aval':
      return 'billing.routeAval';
    case 'ollama':
      return 'billing.routeOllama';
    case 'byok':
      return 'billing.routeByok';
    default:
      return 'billing.routeEcho';
  }
}

/** A single labelled row of the summary. */
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-6 py-2.5">
      <dt className="shrink-0 text-caption font-medium uppercase tracking-wide text-fg-secondary">
        {label}
      </dt>
      <dd className="min-w-0 text-end text-body text-fg-primary">{children}</dd>
    </div>
  );
}

/**
 * The billing summary card. Renders inside Settings (general tab); an
 * optional `compact` variant hides the upgrade affordance.
 */
export function BillingSummary({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation('settings');
  const { call } = useBridge();
  const [state, setState] = useState<LoadState>({ status: 'loading' });

  const load = useCallback(async (): Promise<LoadState> => {
    try {
      const [plan, usage, route] = await Promise.all([
        call<CommercePlanDto>('commerce.plan', {}),
        call<CommerceUsageDto>('commerce.usage', {}),
        call<RouteDto>('route.resolve', {}),
      ]);
      return { status: 'ready', plan, usage, route };
    } catch {
      return { status: 'error' };
    }
  }, [call]);

  useEffect(() => {
    let ignore = false;
    void load().then((next) => {
      if (!ignore) setState(next);
    });
    return () => {
      ignore = true;
    };
  }, [load]);

  if (state.status === 'loading') {
    return (
      <div className="flex items-center gap-2 text-caption text-fg-secondary">
        <LoaderCircle className="size-4 animate-spin" aria-hidden />
        {t('billing.unavailable')}
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div className="flex items-center justify-between gap-4">
        <p className="text-caption text-fg-secondary">{t('billing.unavailable')}</p>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            setState({ status: 'loading' });
            void load().then((next) => setState(next));
          }}
        >
          {t('billing.retry')}
        </Button>
      </div>
    );
  }

  const { plan, usage, route } = state;
  const rtl = isRtlLocale();
  const sentence = rtl ? route.sentence_fa : route.sentence_en;

  return (
    <dl className="divide-y divide-border-default">
      <Row label={t('billing.plan')}>
        <span dir="rtl" className="font-medium">
          {plan.name_fa}
        </span>
        <span className="ltr-island ms-1 text-fg-secondary">({plan.name_en})</span>
      </Row>

      <Row label={t('billing.period')}>{t(periodKey(plan.period))}</Row>

      <Row label={t('billing.usage')}>
        {usage.unlimited || usage.limit === null ? (
          <span className="inline-flex items-center gap-1">
            <InfinityIcon className="size-4" aria-hidden />
            {t('billing.turnsUnlimited')}
          </span>
        ) : (
          t('billing.turnsUsed', { used: usage.used, limit: usage.limit })
        )}
      </Row>

      <Row label={t('billing.price')}>
        {plan.price === 0 ? (
          <span className="font-medium text-accent-text">{t('billing.free')}</span>
        ) : (
          <span className="text-fg-secondary">{t('billing.priceTbd')}</span>
        )}
      </Row>

      <Row label={t('billing.route')}>
        <span className="flex flex-col items-end gap-1">
          <span className="inline-flex items-center gap-1.5">
            <RouteIcon className="size-4 text-fg-muted" aria-hidden />
            {t(routeNameKey(route.name))}
            <Badge variant={route.leaves_machine ? 'warning' : 'success'}>
              {route.leaves_machine ? t('billing.leavesMachine') : t('billing.staysLocal')}
            </Badge>
          </span>
          <span className="ltr-island max-w-md text-caption text-fg-secondary" dir="ltr">
            {sentence}
          </span>
        </span>
      </Row>

      {!compact && (
        <div className="flex items-center justify-between gap-4 pt-3">
          <span className="inline-flex items-center gap-1.5 text-caption text-fg-muted">
            <CircleDollarSign className="size-4" aria-hidden />
            {t('billing.plan')}: {plan.name_en}
          </span>
          <Button size="sm" variant="secondary" disabled title={t('billing.priceTbd')}>
            {t('billing.upgrade')}
          </Button>
        </div>
      )}
    </dl>
  );
}
