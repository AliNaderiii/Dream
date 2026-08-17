/**
 * 48px activity rail — the top-level navigation surface (design-system §7).
 *
 * Icons mirror automatically in RTL because the rail is laid out with logical
 * properties; the icons themselves are non-directional.
 */

import {
  BarChart3,
  Bot,
  Database,
  FolderKanban,
  MessageSquare,
  Radio,
  Settings,
  Sparkles,
  Wrench,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { NavLink } from 'react-router-dom';

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useTranslation } from '@/lib/i18n';
import { cn } from '@/utils/cn';
import { formatShortcut } from '@/utils/platform';

/** A destination in the activity rail. */
interface RailItem {
  to: string;
  labelKey: string;
  icon: LucideIcon;
  shortcut?: readonly string[];
  /** Match child routes as active (e.g. `/chat/:id`). */
  end?: boolean;
}

const PRIMARY_ITEMS: RailItem[] = [
  { to: '/', labelKey: 'nav.dashboard', icon: Sparkles, shortcut: ['mod', '1'], end: true },
  { to: '/chat', labelKey: 'nav.chat', icon: MessageSquare },
  { to: '/projects', labelKey: 'nav.projects', icon: FolderKanban, shortcut: ['mod', '2'] },
  { to: '/memory', labelKey: 'nav.memory', icon: Database, shortcut: ['mod', '3'] },
  { to: '/skills', labelKey: 'nav.skills', icon: Wrench, shortcut: ['mod', '4'] },
  { to: '/subagents', labelKey: 'nav.subagents', icon: Bot },
  { to: '/data', labelKey: 'nav.data', icon: BarChart3 },
  { to: '/connectivity', labelKey: 'nav.connectivity', icon: Radio, shortcut: ['mod', '5'] },
];

const FOOTER_ITEMS: RailItem[] = [
  { to: '/providers', labelKey: 'nav.providers', icon: Sparkles },
  { to: '/settings', labelKey: 'nav.settings', icon: Settings, shortcut: ['mod', ','] },
];

function RailLink({ item }: { item: RailItem }) {
  const { t } = useTranslation('common');
  const Icon = item.icon;
  const label = t(item.labelKey);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <NavLink
          to={item.to}
          end={item.end}
          aria-label={label}
          className={({ isActive }) =>
            cn(
              'relative flex size-10 items-center justify-center rounded-md text-fg-secondary transition-colors duration-fast',
              'hover:bg-surface-2 hover:text-fg-primary',
              isActive && 'bg-accent-soft text-accent-text',
            )
          }
        >
          {({ isActive }) => (
            <>
              {/* Active marker: a bar on the inline-start edge, mirrored in RTL. */}
              {isActive && (
                <span
                  aria-hidden
                  className="absolute inset-y-1.5 start-0 w-0.5 rounded-full bg-accent"
                />
              )}
              <Icon className="size-5" aria-hidden />
            </>
          )}
        </NavLink>
      </TooltipTrigger>
      <TooltipContent side="right">
        {label}
        {item.shortcut && (
          <span className="ms-2 text-fg-muted ltr-island">{formatShortcut(item.shortcut)}</span>
        )}
      </TooltipContent>
    </Tooltip>
  );
}

/** Vertical icon rail pinned to the inline-start edge of the shell. */
export function ActivityRail() {
  return (
    <nav
      aria-label="Primary"
      className="flex w-12 shrink-0 flex-col items-center justify-between border-e border-border-default bg-surface py-2"
    >
      <div className="flex flex-col items-center gap-1">
        {PRIMARY_ITEMS.map((item) => (
          <RailLink key={item.to} item={item} />
        ))}
      </div>
      <div className="flex flex-col items-center gap-1">
        {FOOTER_ITEMS.map((item) => (
          <RailLink key={item.to} item={item} />
        ))}
      </div>
    </nav>
  );
}
