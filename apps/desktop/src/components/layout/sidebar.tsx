/**
 * Collapsible context sidebar using semantic shell geometry.
 *
 * Hosts the session list today; later phases swap its contents per active rail
 * section. Width is user-resizable via a keyboard-accessible drag handle.
 */

import {
  MessageSquarePlus,
  MoreHorizontal,
  PanelLeftClose,
  Pencil,
  Search,
  Trash2,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { BridgeOfflineBanner } from '@/components/shared/bridge-offline-banner';
import { ConfirmDialog } from '@/components/shared/confirm-dialog';
import { VirtualList } from '@/components/shared/virtual-list';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useBridge } from '@/lib/bridge/hooks';
import type { BridgeSession } from '@/lib/bridge/types';
import { useTranslation } from '@/lib/i18n';
import { SIDEBAR_MAX_WIDTH, SIDEBAR_MIN_WIDTH, useAppStore } from '@/stores/use-app-store';
import { useSessionStore } from '@/stores/use-session-store';
import type { Session } from '@/types';
import { cn } from '@/utils/cn';
import { formatShortcut } from '@/utils/platform';

function bridgeTimestamp(value: number): number {
  return value < 1_000_000_000_000 ? value * 1000 : value;
}

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
  const { call, client } = useBridge();
  const navigate = useNavigate();
  const collapsed = useAppStore((s) => s.sidebarCollapsed);
  const width = useAppStore((s) => s.sidebarWidth);
  const setWidth = useAppStore((s) => s.setSidebarWidth);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);

  const sessions = useSessionStore((s) => s.sessions);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const searchQuery = useSessionStore((s) => s.searchQuery);
  const setSearchQuery = useSessionStore((s) => s.setSearchQuery);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);
  const mergeSessions = useSessionStore((s) => s.mergeSessions);
  const renameSession = useSessionStore((s) => s.renameSession);
  const deleteSession = useSessionStore((s) => s.deleteSession);
  const [renaming, setRenaming] = useState<Session | null>(null);
  const [renameDraft, setRenameDraft] = useState('');
  const [deleting, setDeleting] = useState<Session | null>(null);
  const [loadingSessions, setLoadingSessions] = useState(client.transportKind === 'tauri');
  const [sessionError, setSessionError] = useState<string | null>(null);

  const dragging = useRef(false);

  const loadSessions = useCallback(
    async (signal?: AbortSignal) => {
      setLoadingSessions(true);
      setSessionError(null);
      try {
        const result = await call<{ sessions: BridgeSession[] }>('session.list', {}, { signal });
        mergeSessions(
          result.sessions.map((session) => {
            return {
              id: session.id,
              title: session.title,
              createdAt: bridgeTimestamp(session.created_at),
              updatedAt: bridgeTimestamp(session.updated_at),
              messageCount: session.message_count,
            };
          }),
        );
      } catch (error) {
        if (!signal?.aborted) {
          setSessionError(error instanceof Error ? error.message : t('sessions.loadError'));
        }
      } finally {
        if (!signal?.aborted) setLoadingSessions(false);
      }
    },
    [call, mergeSessions, t],
  );

  useEffect(() => {
    if (client.transportKind !== 'tauri') return;
    const controller = new AbortController();
    void Promise.resolve().then(() => loadSessions(controller.signal));
    return () => controller.abort();
  }, [client, loadSessions]);

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

  const commitRename = () => {
    if (!renaming || !renameDraft.trim()) return;
    const title = renameDraft.trim();
    renameSession(renaming.id, title);
    setRenaming(null);
    void call('session.rename', { session_id: renaming.id, title }).catch((error: unknown) => {
      setSessionError(error instanceof Error ? error.message : t('sessions.renameError'));
    });
  };

  return (
    <>
      <aside
        aria-label={t('sessions.title')}
        aria-busy={loadingSessions}
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
                  const create = async () => {
                    setSessionError(null);
                    try {
                      const created = await call<{
                        session_id: string;
                        title: string;
                        created_at: number;
                      }>('session.create', { title: t('sessions.untitled') });
                      const timestamp = bridgeTimestamp(created.created_at);
                      mergeSessions([
                        {
                          id: created.session_id,
                          title: created.title,
                          createdAt: timestamp,
                          updatedAt: timestamp,
                          messageCount: 0,
                        },
                      ]);
                      setActiveSession(created.session_id);
                      void navigate(`/chat/${created.session_id}`);
                    } catch (error) {
                      setSessionError(
                        error instanceof Error ? error.message : t('sessions.createError'),
                      );
                    }
                  };
                  void create();
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

        <BridgeOfflineBanner compact />

        {sessionError && (
          <div
            role="alert"
            className="flex items-center gap-2 border-b border-danger-fg bg-danger-bg px-3 py-2 text-caption text-danger-fg"
          >
            <span className="min-w-0 flex-1">{sessionError}</span>
            <Button size="sm" variant="secondary" onClick={() => void loadSessions()}>
              {t('sessions.retry')}
            </Button>
          </div>
        )}

        <div className="min-h-0 flex-1 px-2 pb-2">
          {loadingSessions && sessions.length === 0 ? (
            <div
              role="status"
              aria-label={t('sessions.loading')}
              className="flex flex-col gap-2 p-2"
            >
              {Array.from({ length: 5 }, (_, index) => (
                <div
                  key={index}
                  className="h-9 animate-pulse rounded-md bg-surface-2 motion-reduce:animate-none"
                />
              ))}
            </div>
          ) : visible.length === 0 ? (
            <p className="px-2 py-6 text-center text-caption text-fg-muted">
              {sessions.length === 0 ? t('sessions.empty') : t('sessions.noMatch')}
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
                    <p className="px-2 pb-1 pt-3 text-micro font-semibold uppercase text-fg-muted">
                      {t(group)}
                    </p>
                  )}
                  <div className="group flex items-center gap-0.5">
                    <button
                      type="button"
                      onClick={() => {
                        setActiveSession(session.id);
                        void navigate(`/chat/${session.id}`);
                      }}
                      className={cn(
                        'min-w-0 flex-1 truncate rounded-md px-2 py-1.5 text-start text-body transition-colors duration-fast',
                        'hover:bg-surface-2',
                        session.id === activeSessionId && 'bg-accent-soft text-accent-text',
                      )}
                    >
                      {session.title || t('sessions.untitled')}
                    </button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          type="button"
                          size="icon-sm"
                          variant="ghost"
                          className="shrink-0 opacity-0 group-focus-within:opacity-100 group-hover:opacity-100"
                          aria-label={t('sessions.actions', {
                            title: session.title || t('sessions.untitled'),
                          })}
                        >
                          <MoreHorizontal aria-hidden />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onSelect={() => {
                            setRenameDraft(session.title);
                            setRenaming(session);
                          }}
                        >
                          <Pencil aria-hidden />
                          {t('sessions.rename')}
                        </DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => setDeleting(session)}>
                          <Trash2 aria-hidden />
                          {t('sessions.delete')}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              )}
            />
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

      <Dialog open={renaming !== null} onOpenChange={(open) => !open && setRenaming(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('sessions.renameTitle')}</DialogTitle>
            <DialogDescription>{t('sessions.renameDescription')}</DialogDescription>
          </DialogHeader>
          <DialogBody>
            <label htmlFor="session-rename" className="mb-1.5 block text-caption font-medium">
              {t('sessions.name')}
            </label>
            <input
              id="session-rename"
              value={renameDraft}
              maxLength={120}
              autoFocus
              onChange={(event) => setRenameDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') commitRename();
              }}
              className="selectable h-9 w-full rounded-md border border-border-default bg-canvas px-3 text-body text-fg-primary"
            />
          </DialogBody>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setRenaming(null)}>
              {t('confirm.cancel')}
            </Button>
            <Button variant="primary" disabled={!renameDraft.trim()} onClick={commitRename}>
              {t('sessions.rename')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={t('sessions.deleteTitle')}
        description={t('sessions.deleteDescription', {
          title: deleting?.title || t('sessions.untitled'),
        })}
        confirmLabel={t('sessions.delete')}
        onConfirm={() => {
          if (!deleting) return;
          const wasActive = deleting.id === activeSessionId;
          deleteSession(deleting.id);
          setDeleting(null);
          void call('session.delete', { session_id: deleting.id }).catch((error: unknown) => {
            setSessionError(error instanceof Error ? error.message : t('sessions.deleteError'));
          });
          if (wasActive) void navigate('/chat');
        }}
      />
    </>
  );
}
