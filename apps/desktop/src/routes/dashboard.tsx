/** Dashboard — the launch screen & Evolution Benchmark Studio. */

import { Database, MessageSquarePlus, Sparkles, Trophy, Wrench } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { FirstRunCard } from '@/components/billing/first-run-card';
import { EvolutionBenchmarkStudio } from '@/components/evals/evolution-benchmark-studio';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/lib/i18n';
import { useSessionStore } from '@/stores/use-session-store';
import { SafeIcon } from '@/utils/icons';
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
  const [showBenchmarkStudio, setShowBenchmarkStudio] = useState(true);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-8 p-6 lg:p-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-display font-bold">{t('dashboard.greeting')}</h2>
          <p className="text-body-lg text-fg-secondary">{t('dashboard.subtitle')}</p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant={showBenchmarkStudio ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setShowBenchmarkStudio((prev) => !prev)}
            className="flex items-center gap-1.5"
          >
            <Trophy className="size-4" />
            <span>Hermes Superiority Arena</span>
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              const session = createSession(t('sessions.untitled'));
              void navigate(`/chat/${session.id}`);
            }}
          >
            <MessageSquarePlus aria-hidden className="mr-1 size-4" />
            {t('dashboard.startSession')}
            <span className="ltr-island ms-1 opacity-70">{formatShortcut(['mod', 'n'])}</span>
          </Button>
        </div>
      </header>

      {/* S05: offline-first onboarding — echo works, Ollama offered, BYOK optional */}
      <FirstRunCard />

      <div className="grid gap-3 sm:grid-cols-3">
        {TILES.map((tile) => (
          <button
            key={tile.to}
            type="button"
            onClick={() => void navigate(tile.to)}
            className="flex flex-col items-start gap-2 rounded-lg border border-border-default bg-surface p-4 text-start transition-colors duration-fast hover:border-border-strong hover:bg-surface-2"
          >
            <SafeIcon icon={tile.icon} className="size-5 text-accent-text" aria-hidden />
            <span className="text-h3 font-semibold">{t(tile.labelKey)}</span>
            <span className="text-caption text-fg-secondary">{t(tile.descKey)}</span>
          </button>
        ))}
      </div>

      {/* Integrated Self-Evolution & Hermes Benchmark Studio */}
      {showBenchmarkStudio && (
        <div className="mt-4 border-t border-border-default pt-6">
          <EvolutionBenchmarkStudio />
        </div>
      )}
    </div>
  );
}
