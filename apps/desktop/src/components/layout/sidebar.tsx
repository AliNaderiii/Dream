/**
 * Collapsible context sidebar using semantic shell geometry.
 *
 * Hosts the session list today; later phases swap its contents per active rail
 * section. Width is user-resizable via a keyboard-accessible drag handle.
 */

import { MessageSquarePlus, PanelLeftClose, Search } from 'lucide-react';
import { useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useTranslation } from '@/lib/i18n';
import { SIDEBAR_MAX_WIDTH, SIDEBAR_MIN_WIDTH, useAppStore } from '@/stores/use-app-store';
import { useSessionStore } from '@/stores/use-session-store';
import { cn } from '@/utils/cn';
import { formatShortcut } from '@/utils/platform';

/** i18n key of the date bucket a timestamp falls into. */
function groupKey(timestamp: number): string {
  const day = 86_400_000;
  const age = Date.now() - timestamp;
  if (age < day) return 'sessions.groupToday';
  if (age < 7 * day) return 'sessions.groupWeek';
  if (age < 30 * day) return 'sessions.groupMonth';
  return 'sessions.groupOlder';
}

export function Sidebar() {
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const collapsed = useAppStore((s) => s.sidebarCollapsed);
  const width = useAppStore((s) => s.sidebarWidth);
  const setWidth = useAppStore((s) => s.setSidebarWidth);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);

  const sessions = useSessionStore((s) => s.sessions);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const searchQuery = useSessionStore((s) => s.searchQuery);
  const setSearchQuery = useSessionStore((s) => s.setSearchQuery);
  const createSession = useSessionStore((s) => s.createSession);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);

  const dragging = useRef(false);

  const onPointerMove = useCallback(
    (event: PointerEvent) => {
      if (!dragging.current) return;
      // In RTL the sidebar sits on the right, so width grows as x decreases.
      const rtl = document.documentElement.getAttribute('dir') === 'rtl';
      const next = rtl ? window.innerWidth - event.clientX - 48 : event.clientX - 48;
      setWidth(next);
    },
    [setWidth],
  );

  useEffect(() => {
    const stop = () => {
      dragging.current = false;
      document.body.style.cursor = '';
    };
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', stop);
    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', stop);
    };
  }, [onPointerMove]);

  if (collapsed) return null;

  const visible = searchQuery
    ? sessions.filter((s) => s.title.toLowerCase().includes(searchQuery.toLowerCase()))
    : sessions;

  // Precompute the date-group header for each row so rendering stays pure.
  const rows = visible.map((session, index) => {
    const group = groupKey(session.updatedAt);
    const previous = index > 0 ? groupKey(visible[index - 1].updatedAt) : null;
    return { session, group, showHeader: group !== previous };
  });

  return (
    <aside
      aria-label={t('sessions.title')}
      style={{ width }}
      className="relative flex shrink-0 flex-col border-e border-border-default bg-surface"
    >
      <div className="flex items-center gap-1 px-3 pt-3">
        <h2 className="flex-1 text-h3 font-semibold">{t('sessions.title')}</h2>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t('sessions.new')}
              onClick={() => {
                const session = createSession();
                void navigate(`/chat/${session.id}`);
              }}
            >
              <MessageSquarePlus aria-hidden />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {t('sessions.new')} {formatShortcut(['mod', 'n'])}
          </TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t('sessions.collapse')}
              onClick={toggleSidebar}
            >
              <PanelLeftClose aria-hidden className="rtl:rotate-180" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {t('sessions.collapse')} {formatShortcut(['mod', 'b'])}
          </TooltipContent>
        </Tooltip>
      </div>

      <div className="relative px-3 py-2">
        <Search
          aria-hidden
          className="pointer-events-none absolute start-5 top-1/2 size-4 -translate-y-1/2 text-fg-muted"
        />
        <input
          type="search"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder={t('sessions.search')}
          aria-label={t('sessions.search')}
          className="selectable h-8 w-full rounded-md border border-border-default bg-sunken ps-8 pe-2 text-body text-fg-primary placeholder:text-fg-muted focus:border-border-strong"
        />
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {visible.length === 0 ? (
          <p className="px-2 py-6 text-center text-caption text-fg-muted">
            {sessions.length === 0 ? t('sessions.empty') : t('sessions.noMatch')}
          </p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {rows.map(({ session, group, showHeader }) => {
              return (
                <li key={session.id}>
                  {showHeader && (
                    <p className="px-2 pb-1 pt-3 text-micro font-semibold uppercase text-fg-muted">
                      {t(group)}
                    </p>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      setActiveSession(session.id);
                      void navigate(`/chat/${session.id}`);
                    }}
                    className={cn(
                      'w-full truncate rounded-md px-2 py-1.5 text-start text-body transition-colors duration-fast',
                      'hover:bg-surface-2',
                      session.id === activeSessionId && 'bg-accent-soft text-accent-text',
                    )}
                  >
                    {session.title}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Token-sized resize handle with a visible rule and keyboard adjustment. */}
      <div
        role="separator"
        aria-label={t('sessions.resize')}
        aria-orientation="vertical"
        aria-valuenow={width}
        aria-valuemin={SIDEBAR_MIN_WIDTH}
        aria-valuemax={SIDEBAR_MAX_WIDTH}
        tabIndex={0}
        onPointerDown={() => {
          dragging.current = true;
          document.body.style.cursor = 'col-resize';
        }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowLeft') setWidth(width - 16);
          if (e.key === 'ArrowRight') setWidth(width + 16);
        }}
        className="absolute inset-y-0 end-0 w-1.5 translate-x-1/2 cursor-col-resize hover:bg-accent/40"
      />
    </aside>
  );
}
