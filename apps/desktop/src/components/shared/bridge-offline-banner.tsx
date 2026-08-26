import { WifiOff } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useBridge } from '@/lib/bridge/hooks';
import { useTranslation } from '@/lib/i18n';

/** Visible, actionable bridge-dead state shared by every manager surface. */
export function BridgeOfflineBanner({ compact = false }: { compact?: boolean }) {
  const { state, reconnect } = useBridge();
  const { t } = useTranslation('common');
  if (state !== 'disconnected') return null;

  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-2 border-b border-warning-fg bg-warning-bg px-3 py-2 text-caption text-warning-fg"
    >
      <WifiOff aria-hidden className="size-4 shrink-0" />
      <span className="min-w-0 flex-1 break-words">
        {compact ? t('bridgeOffline.short') : t('bridgeOffline.description')}
      </span>
      <Button size="sm" variant="secondary" className="ms-auto shrink-0" onClick={reconnect}>
        {t('bridgeOffline.retry')}
      </Button>
    </div>
  );
}
