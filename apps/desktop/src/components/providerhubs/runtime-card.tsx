import {
  Check,
  LoaderCircle,
  RefreshCw,
  Server,
  ShieldCheck,
  TriangleAlert,
  XCircle,
} from 'lucide-react';
import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card';
import { useTranslation } from '@/lib/i18n';
import type { ProbeResult, RuntimeRecord } from '@/lib/bridge/providerhubs';
import { selectModel, testRuntime } from '@/lib/bridge/providerhubs';
import { cn } from '@/utils/cn';

export function RuntimeCard({
  runtime,
  locale,
  onChange,
}: {
  runtime: RuntimeRecord;
  locale: string;
  onChange: (next: RuntimeRecord) => void;
}) {
  const { t } = useTranslation('providerhubs');
  const [busy, setBusy] = useState(false);
  const [probe, setProbe] = useState<ProbeResult | null>(null);

  const privacy = locale === 'fa' ? runtime.privacy_fa : runtime.privacy_en;
  const healthVariant =
    runtime.health === 'healthy' ? 'success' : runtime.health === 'down' ? 'danger' : 'neutral';

  const runTest = async () => {
    setBusy(true);
    try {
      const result = await testRuntime(runtime.id);
      setProbe(result);
    } finally {
      setBusy(false);
    }
  };

  const pickModel = async (model: string) => {
    const next = await selectModel(runtime.id, model);
    onChange(next);
  };

  return (
    <Card aria-labelledby={`runtime-${runtime.id}-title`}>
      <CardHeader>
        <div className="flex items-start gap-3">
          <div className="flex size-10 items-center justify-center rounded-lg bg-accent-soft text-accent-text">
            <Server aria-hidden />
          </div>
          <div className="min-w-0 flex-1">
            <h3
              id={`runtime-${runtime.id}-title`}
              className="text-h3 font-semibold text-fg-primary"
            >
              {runtime.name}
            </h3>
            <p className="ltr-island truncate text-caption text-fg-muted">{runtime.endpoint}</p>
          </div>
          <Badge variant={healthVariant}>
            {runtime.health === 'healthy' ? (
              <Check aria-hidden />
            ) : runtime.health === 'down' ? (
              <XCircle aria-hidden />
            ) : null}
            {t(`status.${runtime.health}`)}
          </Badge>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {runtime.detected && (
            <Badge variant="accent">
              <ShieldCheck aria-hidden />
              {t('detected')}
            </Badge>
          )}
          {runtime.recommended && <Badge variant="success">{t('recommended')}</Badge>}
          <Badge
            variant={
              runtime.tool_calling === 'native'
                ? 'success'
                : runtime.tool_calling === 'fallback'
                  ? 'warning'
                  : 'neutral'
            }
          >
            {runtime.tool_calling === 'fallback' ? <TriangleAlert aria-hidden /> : null}
            {t(`toolCalling.${runtime.tool_calling}`)}
          </Badge>
          {runtime.tool_calling === 'fallback' && (
            <Badge variant="warning">{t('reducedReliability')}</Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-caption text-fg-secondary">{privacy}</p>
        <p className="text-micro text-fg-muted">{runtime.parser_guidance}</p>
        <label className="flex flex-col gap-1 text-caption font-medium text-fg-secondary">
          {t('modelPicker')}
          <select
            className="focus-control h-9 w-full rounded-md border border-border-default bg-canvas px-3 text-body text-fg-primary"
            aria-label={t('modelPicker')}
            value={runtime.selected_model}
            disabled={runtime.models.length === 0}
            onChange={(event) => void pickModel(event.target.value)}
          >
            {runtime.models.length === 0 ? (
              <option value="">{t('noModels')}</option>
            ) : (
              runtime.models.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))
            )}
          </select>
        </label>
        {probe && (
          <p
            role="status"
            className={cn(
              'rounded-md px-3 py-2 text-caption',
              probe.ok ? 'bg-success-bg text-success-fg' : 'bg-warning-bg text-warning-fg',
            )}
          >
            {probe.ok ? t('testOk', { ms: probe.latency_ms }) : t('testFail')}
          </p>
        )}
      </CardContent>
      <CardFooter>
        <Button
          size="sm"
          onClick={() => void runTest()}
          disabled={busy}
          aria-label={t('testAria', { name: runtime.name })}
        >
          {busy ? <LoaderCircle className="animate-spin" aria-hidden /> : <RefreshCw aria-hidden />}
          {busy ? t('testing') : t('test')}
        </Button>
        <span className="text-caption text-fg-muted">{t(`cost.${runtime.cost_tier}`)}</span>
      </CardFooter>
    </Card>
  );
}
