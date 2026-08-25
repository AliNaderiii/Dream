import { Badge } from '@/components/ui/badge';
import { useTranslation } from '@/lib/i18n';

export function ModeIndicator({
  mode,
  live,
  running,
  cancelled,
}: {
  mode: 'chat' | 'plan' | 'goal';
  live: boolean;
  running: boolean;
  cancelled: boolean;
}) {
  const { t } = useTranslation('workspace');
  const variant = cancelled ? 'warning' : running ? 'accent' : 'success';
  return (
    <div className="flex flex-wrap items-center gap-2" aria-live="polite">
      <Badge variant={variant}>{t(`agents.mode.${mode}`)}</Badge>
      {live && <Badge variant="success">{t('agents.live')}</Badge>}
      {running && <Badge variant="accent">{t('agents.running')}</Badge>}
      {cancelled && <Badge variant="warning">{t('agents.cancelled')}</Badge>}
    </div>
  );
}
