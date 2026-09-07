/**
 * Mobile bottom navigation — primary destinations rendered as a tab bar
 * when the viewport is at a phone breakpoint.
 *
 * Mirrors in RTL because every edge uses logical properties.
 */

import { useNavigate } from 'react-router-dom';

import { Database, FolderKanban, MessageSquare, Settings, Sparkles } from 'lucide-react';
import { useTranslation } from '@/lib/i18n';
import { cn } from '@/utils/cn';

const DESTINATIONS = [
  { to: '/', labelKey: 'nav.dashboard', icon: Sparkles },
  { to: '/chat', labelKey: 'nav.chat', icon: MessageSquare },
  { to: '/projects', labelKey: 'nav.projects', icon: FolderKanban },
  { to: '/memory', labelKey: 'nav.memory', icon: Database },
  { to: '/settings', labelKey: 'nav.settings', icon: Settings },
];

interface BottomNavProps {
  className?: string;
}

export function BottomNav({ className }: BottomNavProps) {
  const { t } = useTranslation('common');
  const navigate = useNavigate();

  return (
    <nav
      aria-label="Primary"
      className={cn(
        'flex shrink-0 flex-row items-stretch border-t border-border-default bg-surface py-1',
        className,
      )}
    >
      {DESTINATIONS.map((dest) => {
        const Icon = dest.icon;

        return (
          <button
            key={dest.to}
            type="button"
            onClick={() => navigate(dest.to)}
            aria-label={t(dest.labelKey)}
            className={cn(
              'flex flex-1 items-center justify-center gap-1.5 rounded-lg text-fg-secondary transition-colors duration-fast',
              'hover:bg-surface-2 hover:text-fg-primary',
              'focus-visible:outline-2 focus-visible:outline-focus-ring',
            )}
          >
            <Icon className="size-5 shrink-0" aria-hidden />
            <span className="min-w-0 truncate text-micro font-medium">{t(dest.labelKey)}</span>
          </button>
        );
      })}
    </nav>
  );
}
