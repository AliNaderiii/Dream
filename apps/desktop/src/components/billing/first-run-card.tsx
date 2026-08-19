/**
 * First-run card (S05) — the honest offline-first story on the dashboard.
 *
 * - The offline echo engine works with zero network and no account.
 * - Ollama is offered as the local upgrade path (still nothing leaves the
 *   machine).
 * - BYOK is optional and says plainly that prompts then leave the machine.
 *
 * The current route line comes from `route.resolve` (sidecar) with the
 * deterministic echo fallback in the browser.
 */

import { KeyRound, PlugZap, Route as RouteIcon, WifiOff } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { useBridge } from '@/lib/bridge/hooks';
import { isRtlLocale, useTranslation } from '@/lib/i18n';
import type { RouteDto } from '@/lib/bridge/types';

export function FirstRunCard() {
  const { t } = useTranslation('common');
  const { call } = useBridge();
  const navigate = useNavigate();
  const [route, setRoute] = useState<RouteDto | null>(null);

  useEffect(() => {
    let ignore = false;
    void call<RouteDto>('route.resolve', {})
      .then((resolved) => {
        if (!ignore) setRoute(resolved);
      })
      .catch(() => {
        // Echo fallback covers the no-sidecar case; silence the rest.
      });
    return () => {
      ignore = true;
    };
  }, [call]);

  const sentence = route ? (isRtlLocale() ? route.sentence_fa : route.sentence_en) : null;

  return (
    <section
      aria-labelledby="first-run-title"
      className="rounded-xl border border-border-default bg-surface p-5 shadow-sm"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h3 id="first-run-title" className="flex items-center gap-2 text-h3 font-semibold">
            <WifiOff className="size-5 text-accent-text" aria-hidden />
            {t('firstRun.title')}
          </h3>
          <p className="text-body text-fg-secondary">{t('firstRun.desc')}</p>
          <p className="ltr-island mt-1 text-caption text-fg-muted">{t('firstRun.echo')}</p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-2 rounded-lg border border-border-default bg-surface-2 p-4">
          <span className="flex items-center gap-2 text-body font-medium">
            <PlugZap className="size-4 text-accent-text" aria-hidden />
            {t('firstRun.ollamaTitle')}
          </span>
          <p className="text-caption text-fg-secondary">{t('firstRun.ollamaDesc')}</p>
          <Button
            variant="secondary"
            size="sm"
            className="self-start"
            onClick={() => void navigate('/providers')}
          >
            {t('firstRun.ollamaCta')}
          </Button>
        </div>

        <div className="flex flex-col gap-2 rounded-lg border border-border-default bg-surface-2 p-4">
          <span className="flex items-center gap-2 text-body font-medium">
            <KeyRound className="size-4 text-accent-text" aria-hidden />
            {t('firstRun.byokTitle')}
          </span>
          <p className="text-caption text-fg-secondary">{t('firstRun.byokDesc')}</p>
          <Button
            variant="secondary"
            size="sm"
            className="self-start"
            onClick={() => void navigate('/providers')}
          >
            {t('firstRun.byokCta')}
          </Button>
        </div>
      </div>

      {route && (
        <div className="mt-4 flex items-center gap-2 rounded-lg bg-surface-2 px-3 py-2">
          <RouteIcon className="size-4 shrink-0 text-fg-muted" aria-hidden />
          <span className="text-caption font-medium">{t('firstRun.routeTitle')}:</span>
          <span
            className={
              route.leaves_machine
                ? 'text-caption font-semibold text-warning-fg'
                : 'text-caption font-semibold text-success-fg'
            }
          >
            {route.leaves_machine ? t('firstRun.leavesMachine') : t('firstRun.staysLocal')}
          </span>
          {sentence && (
            <span className="ltr-island min-w-0 truncate text-caption text-fg-muted" dir="ltr">
              {sentence}
            </span>
          )}
        </div>
      )}
    </section>
  );
}
