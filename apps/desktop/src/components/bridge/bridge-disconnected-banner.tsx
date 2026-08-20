/**
 * Honest, calm, bilingual banner shown when the Python-sidecar bridge is
 * disconnected — for example when the owner installed the desktop shell but
 * has no Python kernel. It tells the truth (the app is offline because the
 * kernel is missing) and offers the single most useful action: reconnect, once
 * the kernel is installed. It never pretends the model is local.
 *
 * This is the intentional "kernel missing" empty state: one sentence EN + FA,
 * one primary action, no panic. See `errors.bridgeKernelMissing` /
 * `errors.bridgeKernelHelp` in the locale tree.
 */

import { PlugZap } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useBridge } from '@/lib/bridge/hooks';
import { useTranslation } from '@/lib/i18n';

export function BridgeDisconnectedBanner() {
  const { t } = useTranslation('errors');
  const { t: tc } = useTranslation('common');
  const { state, reconnect } = useBridge();

  if (state !== 'disconnected') return null;

  return (
    <div role="status" aria-live="polite" className="bridge-banner">
      <PlugZap className="mt-0.5 size-4 shrink-0 text-danger-fg" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-body font-medium text-fg-primary">{t('bridgeKernelMissing')}</p>
        <p className="mt-0.5 break-words text-caption text-fg-secondary">{t('bridgeKernelHelp')}</p>
      </div>
      <Button variant="primary" size="sm" className="shrink-0" onClick={() => reconnect()}>
        {tc('error.retry')}
      </Button>
    </div>
  );
}
