/** Dashboard — the launch screen. */

import { Database, MessageSquarePlus, Sparkles, Wrench } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { FirstRunCard } from '@/components/billing/first-run-card';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import { useSessionStore } from '@/stores/use-session-store';
import { formatShortcut } from '@/utils/platform';

/** A quick-launch tile on the dashboard. */
const TILES = [
  {
    to: '/memory',
    labelKey: 'dashboard.memoryTitle',
    descKey: 'dashboard.memoryDesc',
    icon: Database,
  },
  {
    to: '/skills',
    labelKey: 'dashboard.skillsTitle',
    descKey: 'dashboard.skillsDesc',
    icon: Wrench,
  },
  {
    to: '/providers',
    labelKey: 'dashboard.providersTitle',
    descKey: 'dashboard.providersDesc',
    icon: Sparkles,
  },
] as const;

export function DashboardRoute() {
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const createSession = useSessionStore((s) => s.createSession);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 p-8">
      <header className="flex flex-col gap-2">
        <h2 className="text-display font-bold">{t('dashboard.greeting')}</h2>
        <p className="text-body-lg text-fg-secondary">{t('dashboard.subtitle')}</p>
      </header>

      <Button
        variant="primary"
        size="lg"
        className="self-start"
        onClick={() => {
          const session = createSession();
          void navigate(`/chat/${session.id}`);
        }}
      >
        <MessageSquarePlus aria-hidden />
        {t('dashboard.startSession')}
        <span className="ltr-island ms-1 opacity-70">{formatShortcut(['mod', 'n'])}</span>
      </Button>

      {/* S05: offline-first onboarding — echo works, Ollama offered, BYOK optional */}
      <FirstRunCard />

      <div className="grid gap-3 sm:grid-cols-3">
        {TILES.map((tile) => {
          const Icon = tile.icon;
          return (
            <button
              key={tile.to}
              type="button"
              onClick={() => void navigate(tile.to)}
              className="flex flex-col items-start gap-2 rounded-lg border border-border-default bg-surface p-4 text-start transition-colors duration-fast hover:border-border-strong hover:bg-surface-2"
            >
              <Icon className="size-5 text-accent-text" aria-hidden />
              <span className="text-h3 font-semibold">{t(tile.labelKey)}</span>
              <span className="text-caption text-fg-secondary">{t(tile.descKey)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
