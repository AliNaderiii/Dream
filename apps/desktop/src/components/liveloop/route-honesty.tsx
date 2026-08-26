import { useEffect, useState } from 'react';

import { useBridge } from '@/lib/bridge/hooks';
import { liveloopRouteSnapshot } from '@/lib/bridge/liveloop';
import { useTranslation } from '@/lib/i18n';
import { useProviderStore } from '@/stores/use-provider-store';

/** Honest chip: Settings provider is not necessarily the chat pane. */
export function RouteHonestyIndicator() {
  const { t } = useTranslation('live');
  const { client } = useBridge();
  const bar = useProviderStore((s) => s.providers.find((p) => p.id === s.activeProviderId));
  const [mismatch, setMismatch] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void liveloopRouteSnapshot(client, bar?.name ?? 'echo')
      .then((shot) => {
        if (!cancelled) setMismatch(shot.echo_bar);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [client, bar?.name]);

  if (!bar || !mismatch) return null;
  return (
    <span className="text-fg-muted" title={t('honestyMismatch')}>
      {t('honestyHint')}
    </span>
  );
}
