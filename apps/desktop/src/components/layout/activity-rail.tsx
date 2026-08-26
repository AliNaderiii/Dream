/**
 * Activity rail — the top-level navigation surface (design-system §7).
 *
 * Three honest modes, persisted in the app store (never a new backend):
 *
 * - `collapsed` — icon-only rail at its historical width, tooltip on hover;
 * - `hover`     — collapsed until the pointer enters the rail; expands, and
 *                 collapses on leave unless pinned;
 * - `expanded`  — wider rail with icon + visible label.
 *
 * The pin control at the bottom toggles the rail open (pinned) vs closed.
 * Icons mirror automatically in RTL because the rail is laid out with logical
 * properties; labels sit after icons with a logical gap.
 */

import {
  AlarmClock,
  BarChart3,
  Bot,
  ChevronsLeft,
  ChevronsRight,
  Database,
  Eye,
  FolderKanban,
  MessageSquare,
  Pin,
  PinOff,
  Radio,
  Settings,
  Sparkles,
  Wrench,
} from 'lucide-react';
import { useState } from 'react';
import type { ComponentType } from 'react';
import { NavLink } from 'react-router-dom';

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useTranslation } from '@/lib/i18n';
import { registeredNav } from '@/lib/route-registry';
import { useAppStore } from '@/stores/use-app-store';
import type { RailMode } from '@/types';
import { cn } from '@/utils/cn';
import { formatShortcut } from '@/utils/platform';

/** A destination in the activity rail. */
interface RailItem {
  to: string;
  labelKey: string;
  icon: ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;
  shortcut?: readonly string[];
  /** Match child routes as active (e.g. `/chat/:id`). */
  end?: boolean;
}

const PRIMARY_ITEMS: RailItem[] = [
  { to: '/', labelKey: 'nav.dashboard', icon: Sparkles, shortcut: ['mod', '1'], end: true },
  { to: '/chat', labelKey: 'nav.chat', icon: MessageSquare },
  { to: '/projects', labelKey: 'nav.projects', icon: FolderKanban, shortcut: ['mod', '2'] },
  { to: '/scheduler', labelKey: 'nav.scheduler', icon: AlarmClock },
  { to: '/memory', labelKey: 'nav.memory', icon: Database, shortcut: ['mod', '3'] },
  { to: '/skills', labelKey: 'nav.skills', icon: Wrench, shortcut: ['mod', '4'] },
  { to: '/subagents', labelKey: 'nav.subagents', icon: Bot },
  { to: '/data', labelKey: 'nav.data', icon: BarChart3 },
  { to: '/connectivity', labelKey: 'nav.connectivity', icon: Radio, shortcut: ['mod', '5'] },
];

// P0 SEAM: new domain pages automatically join primary navigation.
const P0_EXTENSION_ITEMS: RailItem[] = registeredNav
  .filter((route) => !PRIMARY_ITEMS.some((item) => item.to === route.path))
  .map((route) => ({
    to: route.path,
    labelKey: route.label,
    icon: route.icon ?? Sparkles,
  }));

const FOOTER_ITEMS: RailItem[] = [
  { to: '/providers', labelKey: 'nav.providers', icon: Sparkles },
  { to: '/settings', labelKey: 'nav.settings', icon: Settings, shortcut: ['mod', ','] },
];

/** Cycle order of the rail modes; `hover` is the middle, default resting state. */
const MODE_CYCLE: RailMode[] = ['collapsed', 'hover', 'expanded'];

function RailLink({ item, expanded }: { item: RailItem; expanded: boolean }) {
  const { t } = useTranslation('common');
  const direction = useAppStore((state) => state.direction);
  const Icon = item.icon;
  const label = t(item.labelKey);

  const link = (
    <NavLink
      to={item.to}
      end={item.end}
      aria-label={expanded ? undefined : label}
      className={({ isActive }) =>
        cn(
          'relative flex h-10 items-center rounded-md text-fg-secondary transition-colors duration-fast',
          'hover:bg-surface-2 hover:text-fg-primary',
          isActive && 'bg-accent-soft text-accent-text',
          expanded ? 'w-full gap-3 px-2.5' : 'size-10 justify-center',
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
          <Icon className="size-5 shrink-0" aria-hidden />
          {expanded && <span className="min-w-0 truncate text-caption font-medium">{label}</span>}
        </>
      )}
    </NavLink>
  );

  // When expanded the label is visible text — a tooltip would be redundant
  // ("labels not tooltip-only when expanded"). Collapsed keeps the tooltip.
  if (expanded) return link;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side={direction === 'rtl' ? 'left' : 'right'}>
        {label}
        {item.shortcut && (
          <span className="ms-2 text-fg-muted ltr-island">{formatShortcut(item.shortcut)}</span>
        )}
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * Activity rail pinned to the inline-start edge of the shell. When unpinned in
 * `hover` mode the rail peeks open while the pointer is over it; leaving the
 * rail collapses it again. The pin control at the bottom keeps it open.
 */
export function ActivityRail() {
  const { t } = useTranslation('common');
  const railMode = useAppStore((state) => state.railMode);
  const railPinned = useAppStore((state) => state.railPinned);
  const setRailMode = useAppStore((state) => state.setRailMode);
  const setRailPinned = useAppStore((state) => state.setRailPinned);
  const [hovering, setHovering] = useState(false);

  const expanded = railMode === 'expanded' || (railMode === 'hover' && (hovering || railPinned));
  // "Pinned" is the pin control's own state. `expanded` must NOT drive it:
  // during a hover-peek the rail is expanded but still unpinned — clicking the
  // pin there must pin it open, not unpin it.
  const pinned = railPinned || railMode === 'expanded';

  const cycleMode = () => {
    const next = MODE_CYCLE[(MODE_CYCLE.indexOf(railMode) + 1) % MODE_CYCLE.length];
    // Mode is the source of truth for expansion; the pin only refines hover.
    setRailMode(next);
    setRailPinned(false);
  };

  const togglePin = () => {
    if (railMode === 'expanded') {
      // The pin is the "collapse" affordance of an always-expanded rail:
      // clicking it returns to hover-peek.
      setRailMode('hover');
      setRailPinned(false);
    } else if (railPinned) {
      // Unpin: fall back to the resting behaviour (hover peek or collapsed).
      setRailPinned(false);
    } else {
      // Pin open. From `collapsed` this also arms hover so the pin has an
      // effect immediately.
      setRailPinned(true);
      if (railMode === 'collapsed') setRailMode('hover');
    }
  };

  const modeLabelKey = `rail.mode${railMode[0].toUpperCase()}${railMode.slice(1)}` as const;

  return (
    <nav
      aria-label="Primary"
      aria-expanded={expanded}
      onPointerEnter={() => setHovering(true)}
      onPointerLeave={() => setHovering(false)}
      className={cn(
        'flex shrink-0 flex-col items-stretch justify-between border-e border-border-default bg-surface py-2',
        'transition-[width] duration-fast ease-standard',
        expanded ? 'w-44' : 'w-12',
      )}
    >
      <div className="flex flex-col items-center gap-1 px-1.5">
        {[...PRIMARY_ITEMS, ...P0_EXTENSION_ITEMS].map((item) => (
          <RailLink key={item.to} item={item} expanded={expanded} />
        ))}
      </div>
      <div className="flex flex-col items-center gap-1 px-1.5">
        {FOOTER_ITEMS.map((item) => (
          <RailLink key={item.to} item={item} expanded={expanded} />
        ))}

        {/* Rail drawer controls — pinned at the bottom, inline-start edge. */}
        <div className="mt-2 flex w-full flex-col items-center gap-1 border-t border-border-default pt-2">
          <button
            type="button"
            onClick={togglePin}
            aria-pressed={pinned}
            aria-label={pinned ? t('rail.unpin') : t('rail.pin')}
            title={pinned ? t('rail.unpin') : t('rail.pin')}
            className="flex size-8 items-center justify-center rounded-md text-fg-muted transition-colors duration-fast hover:bg-surface-2 hover:text-fg-primary focus-visible:outline-2 focus-visible:outline-focus-ring"
          >
            {pinned ? (
              <Pin className="size-4" aria-hidden />
            ) : (
              <PinOff className="size-4" aria-hidden />
            )}
          </button>
          <button
            type="button"
            onClick={cycleMode}
            aria-label={t(modeLabelKey)}
            title={t(modeLabelKey)}
            className="flex size-8 items-center justify-center rounded-md text-fg-muted transition-colors duration-fast hover:bg-surface-2 hover:text-fg-primary focus-visible:outline-2 focus-visible:outline-focus-ring"
          >
            {railMode === 'expanded' ? (
              <ChevronsLeft className="size-4" aria-hidden />
            ) : railMode === 'hover' ? (
              <Eye className="size-4" aria-hidden />
            ) : (
              <ChevronsRight className="size-4" aria-hidden />
            )}
          </button>
        </div>
      </div>
    </nav>
  );
}
