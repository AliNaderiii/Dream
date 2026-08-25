import { Stethoscope, TriangleAlert } from 'lucide-react';
import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { useTranslation } from '@/lib/i18n';
import type { DiagnoseResult, RuntimeKind, RuntimeRecord } from '@/lib/bridge/providerhubs';
import { diagnoseRuntime } from '@/lib/bridge/providerhubs';

export function DiagnosticsPanel({
  runtimes,
  locale,
}: {
  runtimes: RuntimeRecord[];
  locale: string;
}) {
  const { t } = useTranslation('providerhubs');
  const [runtimeId, setRuntimeId] = useState<RuntimeKind>(runtimes[0]?.id ?? 'ollama');
  const [result, setResult] = useState<DiagnoseResult | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      setResult(await diagnoseRuntime(runtimeId));
    } finally {
      setBusy(false);
    }
  };

  const reason = result ? (locale === 'fa' ? result.reason_fa : result.reason) : '';
  const fix = result ? (locale === 'fa' ? result.fix_fa : result.fix) : '';

  return (
    <section aria-labelledby="providerhubs-diagnostics-title">
      <Card>
        <CardHeader>
          <h3 id="providerhubs-diagnostics-title" className="text-h3 font-semibold text-fg-primary">
            {t('diagnostics.title')}
          </h3>
          <CardDescription>{t('diagnostics.subtitle')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-caption font-medium text-fg-secondary">
            {t('diagnostics.runtime')}
            <select
              className="focus-control h-9 w-full rounded-md border border-border-default bg-canvas px-3 text-body text-fg-primary"
              value={runtimeId}
              onChange={(event) => setRuntimeId(event.target.value as RuntimeKind)}
            >
              {runtimes.map((runtime) => (
                <option key={runtime.id} value={runtime.id}>
                  {runtime.name}
                </option>
              ))}
            </select>
          </label>
          <Button onClick={() => void run()} disabled={busy}>
            <Stethoscope aria-hidden />
            {t('diagnostics.action')}
          </Button>
          {result && (
            <div
              role="status"
              className="flex flex-col gap-2 rounded-md border border-border-default bg-surface p-3"
            >
              <div className="flex flex-wrap gap-2">
                <Badge variant={result.firing ? 'success' : 'warning'}>
                  {result.firing ? t('diagnostics.firing') : t('diagnostics.notFiring')}
                </Badge>
                {result.reduced_reliability && (
                  <Badge variant="warning">
                    <TriangleAlert aria-hidden />
                    {t('reducedReliability')}
                  </Badge>
                )}
              </div>
              <p className="text-body text-fg-primary">{reason}</p>
              <p className="text-caption text-fg-secondary">{fix}</p>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
