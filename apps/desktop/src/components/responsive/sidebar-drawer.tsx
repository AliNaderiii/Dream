/**
 * Mobile/tablet sidebar drawer — a full-height sheet that hosts the session
 * list when the viewport is at a drawer breakpoint.
 *
 * Opens via the sidebar toggle (the same control the desktop shell uses) and
 * closes via the Esc key, the close button, or selecting a session. Focus is
 * moved into the sheet on open and returned to the toggle on close.
 */

import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

import { X } from 'lucide-react';
import { useTranslation } from '@/lib/i18n';
import { useViewport } from '@/hooks/use-viewport';
import { useSessionStore } from '@/stores/use-session-store';
import { VirtualList } from '@/components/shared/virtual-list';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { cn } from '@/utils/cn';
import type { Session } from '@/types';
import { formatShortcut } from '@/utils/platform';

interface SessionRow {
  session: Session;
  group: string;
  showHeader: boolean;
}

function groupKey(timestamp: number): string {
  const day = 86_400_000;
  const age = Date.now() - timestamp;
  if (age < day) return 'sessions.groupToday';
  if (age < 7 * day) return 'sessions.groupWeek';
  if (age < 30 * day) return 'sessions.groupMonth';
  return 'sessions.groupOlder';
}

export function SidebarDrawer() {
  const { t } = useTranslation('common');
  const navigate = useNavigate();
  const viewport = useViewport();
  const drawerOpen = viewport.sidebarDrawerOpen;
  const setDrawerOpen = viewport.setSidebarDrawerOpen;
  const sessions = useSessionStore((s) => s.sessions);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);

  const drawerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!drawerOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setDrawerOpen(false);
      }
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [drawerOpen, setDrawerOpen]);

  const rows: SessionRow[] = sessions.map((session, index) => {
    const group = groupKey(session.updatedAt);
    const previous = index > 0 ? groupKey(sessions[index - 1].updatedAt) : null;
    return { session, group, showHeader: group !== previous };
  });

  return (
    <Dialog
      open={drawerOpen}
      onOpenChange={(open) => { if (!open) setDrawerOpen(false); }}
      aria-label={t('sessions.title')}
    >
      <DialogContent className="max-w-none p-0">
        <div className="flex items-center justify-between border-b border-border-default px-3 py-2">
          <h2 className="text-h3 font-semibold">{t('sessions.title')}</h2>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t('sessions.collapse')}
            onClick={() => setDrawerOpen(false)}
            className="shrink-0"
          >
            <X aria-hidden className="rtl:rotate-180" />
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto" ref={drawerRef}>
          {sessions.length === 0 ? (
            <p className="px-3 py-6 text-center text-caption text-fg-muted">
              {t('sessions.empty')}
            </p>
          ) : (
            <VirtualList
              items={rows}
              getKey={({ session }) => session.id}
              estimateSize={(row) => (row.showHeader ? 68 : 36)}
              ariaLabel={t('sessions.title')}
              renderItem={({ session, group, showHeader }) => (
                <div className="h-full pb-0.5">
                  {showHeader && (
                    <p className="px-3 pb-1 pt-3 text-micro font-semibold uppercase text-fg-muted">
                      {t(group)}
                    </p>
                  )}
                  <div className="group flex items-center gap-0.5">
                    <button
                      type="button"
                      onClick={() => {
                        setActiveSession(session.id);
                        navigate(`/chat/${session.id}`);
                        setDrawerOpen(false);
                      }}
                      className={cn(
                        'min-w-0 flex-1 truncate rounded-md px-3 py-1.5 text-start text-body transition-colors duration-fast',
                        'hover:bg-surface-2',
                        session.id === activeSessionId && 'bg-accent-soft text-accent-text',
                      )}
                    >
                      {session.title || t('sessions.untitled')}
                    </button>
                  </div>
                </div>
              )}
            />
          )}
        </div>
        <div className="flex items-center gap-1 px-3 pb-2">
          <span className="text-micro text-fg-muted">{formatShortcut(['mod', 'b'])}</span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
