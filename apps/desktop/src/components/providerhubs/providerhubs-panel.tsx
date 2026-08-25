/**
 * Local runtimes, catalog, optional tool gateway, and tool-call diagnostics.
 * Mounted from `/providers` without rewriting the existing editor/cards.
 */

import { LoaderCircle, Route, ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs } from '@/components/ui/tabs';
import { useTranslation } from '@/lib/i18n';
import { useAppStore } from '@/stores/use-app-store';
import {
  getGateway,
  listCatalog,
  listRuntimes,
  resolveRoute,
  type CatalogEntry,
  type GatewayState,
  type RouteSnapshot,
  type RuntimeRecord,
} from '@/lib/bridge/providerhubs';

import { CatalogSection } from './catalog-section';
import { DiagnosticsPanel } from './diagnostics-panel';
import { RuntimeCard } from './runtime-card';
import { ToolGatewaySection } from './tool-gateway-section';

export function ProviderHubsPanel() {
  const { t } = useTranslation('providerhubs');
  const locale = useAppStore((state) => state.locale);
  const [runtimes, setRuntimes] = useState<RuntimeRecord[]>([]);
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [gateway, setGateway] = useState<GatewayState | null>(null);
  const [route, setRoute] = useState<RouteSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([listRuntimes(), listCatalog(), getGateway(), resolveRoute()])
      .then(([runtimeResult, catalogResult, gatewayResult, routeResult]) => {
        if (cancelled) return;
        setRuntimes(runtimeResult.runtimes);
        setCatalog(catalogResult.catalog);
        setGateway(gatewayResult);
        setRoute(routeResult);
        setError(null);
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setError(t('error'));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refresh, t]);

  const retry = () => {
    setLoading(true);
    setRefresh((value) => value + 1);
  };

  const replaceRuntime = (next: RuntimeRecord) => {
    setRuntimes((current) => current.map((item) => (item.id === next.id ? next : item)));
  };

  return (
    <section className="mt-10 flex flex-col gap-5" aria-labelledby="providerhubs-title">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="providerhubs-title" className="text-h2 font-semibold">
            {t('hubTitle')}
          </h2>
          <Badge variant="accent">{t('recommendedDefault')}</Badge>
        </div>
        <p className="mt-1 max-w-3xl text-body text-fg-secondary">{t('hubSubtitle')}</p>
      </div>

      <div className="flex flex-col gap-2 rounded-md border border-border-default bg-surface px-3 py-3 text-caption text-fg-secondary">
        <p className="flex items-center gap-2 font-medium text-fg-primary">
          <Route className="size-4 shrink-0" aria-hidden />
          {t('routeTitle')}
        </p>
        <p className="ltr-island">
          {route?.priority.join(' → ') ?? 'hosted → aval → ollama → byok → echo'}
        </p>
        <p>{locale === 'fa' ? route?.sentence_fa : (route?.sentence_en ?? t('routeHint'))}</p>
        <p className="flex items-center gap-2">
          <ShieldCheck className="size-4 shrink-0 text-success-fg" aria-hidden />
          {t('honestCost')}
        </p>
      </div>

      {error && (
        <div className="flex items-center justify-between gap-3 rounded-md bg-warning-bg px-3 py-2 text-warning-fg">
          <p role="alert">{error}</p>
          <Button size="sm" onClick={retry}>
            {t('retry')}
          </Button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-12 text-fg-muted">
          <LoaderCircle className="size-5 animate-spin" aria-hidden />
          {t('loading')}
        </div>
      ) : (
        <Tabs
          label={t('tabs.label')}
          items={[
            {
              id: 'runtimes',
              label: t('tabs.runtimes'),
              content: (
                <div className="grid gap-4 md:grid-cols-2">
                  {runtimes.map((runtime) => (
                    <RuntimeCard
                      key={runtime.id}
                      runtime={runtime}
                      locale={locale}
                      onChange={replaceRuntime}
                    />
                  ))}
                </div>
              ),
            },
            {
              id: 'catalog',
              label: t('tabs.catalog'),
              content: <CatalogSection entries={catalog} locale={locale} />,
            },
            {
              id: 'gateway',
              label: t('tabs.gateway'),
              content: gateway ? (
                <ToolGatewaySection gateway={gateway} onChange={setGateway} />
              ) : null,
            },
            {
              id: 'diagnostics',
              label: t('tabs.diagnostics'),
              content: <DiagnosticsPanel runtimes={runtimes} locale={locale} />,
            },
          ]}
        />
      )}
    </section>
  );
}
