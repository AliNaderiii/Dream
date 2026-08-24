/**
 * Status-bar chip for the security engine (SEC Stage B). Visible only while
 * approvals are off — the steady red dot keeps the opt-in state in the
 * owner's peripheral vision on every route. When approvals work normally
 * (manual/smart) nothing renders: silence means the safe default.
 */

import { useSecurityStatus } from '@/lib/bridge/security';
import { useTranslation } from '@/lib/i18n';

export function SecurityStatusIndicator() {
  const { t } = useTranslation('security');
  const status = useSecurityStatus();

  if (!status?.off_active) return null;

  return (
    <span
      className="flex items-center gap-1.5 text-danger-fg"
      title={t('offBannerDetail')}
      aria-label={t('statusBarOff')}
    >
      <span className="size-2 rounded-full bg-danger-fg" aria-hidden />
      <span>{t('statusBarOff')}</span>
    </span>
  );
}
