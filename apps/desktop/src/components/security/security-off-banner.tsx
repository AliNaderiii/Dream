/**
 * Persistent red banner shown while the approval engine runs in `off` mode
 * (SEC Stage B, G-05). `off` is an explicit opt-in; the UI's job is to make
 * sure the owner never forgets it is on. The banner is present on every
 * route, cannot be dismissed, and disappears only when the engine leaves
 * `off` mode. The security floor is unaffected and the banner says so.
 */

import { useSecurityStatus } from '@/lib/bridge/security';
import { useTranslation } from '@/lib/i18n';

export function SecurityOffBanner() {
  const { t } = useTranslation('security');
  const status = useSecurityStatus();

  if (!status?.off_active) return null;

  return (
    <div role="alert" aria-live="assertive" className="security-off-banner">
      <p className="text-body font-semibold">{t('offBannerTitle')}</p>
      <p className="mt-0.5 text-caption opacity-90">{t('offBannerDetail')}</p>
    </div>
  );
}
