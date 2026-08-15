/** Dashboard — the launch screen. Content arrives in later phases. */

import { Database, MessageSquarePlus, Sparkles, Wrench } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { useSessionStore } from '@/stores/use-session-store';
import { formatShortcut } from '@/utils/platform';

/** A quick-launch tile on the dashboard. */
const TILES = [
  {
    to: '/memory',
    label: 'Memory explorer',
    description: 'Browse what Dream remembers',
    icon: Database,
  },
  { to: '/skills', label: 'Skills', description: 'Manage reusable procedures', icon: Wrench },
  {
    to: '/providers',
    label: 'Providers',
    description: 'Configure models and keys',
    icon: Sparkles,
  },
] as const;

export function DashboardRoute() {
  const navigate = useNavigate();
  const createSession = useSessionStore((s) => s.createSession);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 p-8">
      <header className="flex flex-col gap-2">
        <h2 className="text-display font-bold">Good to see you</h2>
        <p className="text-body-lg text-fg-secondary">
          Dream keeps its memory on this machine and asks before doing anything irreversible.
        </p>
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
        Start a session
        <span className="ltr-island ms-1 opacity-70">{formatShortcut(['mod', 'n'])}</span>
      </Button>

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
              <span className="text-h3 font-semibold">{tile.label}</span>
              <span className="text-caption text-fg-secondary">{tile.description}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
