import {
  Archive,
  ArchiveRestore,
  MessageSquarePlus,
  PanelLeftClose,
  Search,
  Trash2,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { useBridge } from '@/lib/bridge/hooks';
import { SIDEBAR_MAX_WIDTH, SIDEBAR_MIN_WIDTH, useAppStore } from '@/stores/use-app-store';
import { useConversationStore } from '@/stores/use-conversation-store';
import { useSessionStore } from '@/stores/use-session-store';
import type { Session } from '@/types';
import { cn } from '@/utils/cn';

function groupLabel(timestamp: number): string {
  const today = new Date();
  const date = new Date(timestamp);
  const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const days = Math.round((startToday - startDate) / 86_400_000);
  if (days === 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return 'This week';
  if (days < 31) return 'This month';
  return 'Older';
}

export function Sidebar() {
  const navigate = useNavigate();
  const { call } = useBridge();
  const collapsed = useAppStore((state) => state.sidebarCollapsed);
  const width = useAppStore((state) => state.sidebarWidth);
  const setWidth = useAppStore((state) => state.setSidebarWidth);
  const toggleSidebar = useAppStore((state) => state.toggleSidebar);
  const store = useSessionStore();
  const clearConversation = useConversationStore((state) => state.clear);
  const [menu, setMenu] = useState<{ session: Session; x: number; y: number } | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const dragging = useRef(false);

  const onPointerMove = useCallback(
    (event: PointerEvent) => {
      if (!dragging.current) return;
      const rtl = document.documentElement.getAttribute('dir') === 'rtl';
      setWidth(rtl ? window.innerWidth - event.clientX - 48 : event.clientX - 48);
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
  useEffect(() => {
    const close = () => setMenu(null);
    window.addEventListener('click', close);
    return () => window.removeEventListener('click', close);
  }, []);

  if (collapsed) return null;
  const query = store.searchQuery.trim().toLowerCase();
  const visible = store.sessions.filter(
    (session) =>
      Boolean(session.isArchived) === store.showArchived &&
      (!query || session.title.toLowerCase().includes(query)),
  );
  const rows = visible.map((session, index) => ({
    session,
    group: groupLabel(session.updatedAt),
    showHeader:
      index === 0 || groupLabel(visible[index - 1].updatedAt) !== groupLabel(session.updatedAt),
  }));

  const exportSession = async (session: Session, format: 'json' | 'md' | 'html') => {
    const result = await call<{ content: string; content_type: string; filename: string }>(
      'session.export',
      { session_id: session.id, format },
    );
    const url = URL.createObjectURL(new Blob([result.content], { type: result.content_type }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = result.filename;
    anchor.click();
    URL.revokeObjectURL(url);
  };
  const commitRename = (session: Session) => {
    const value = renameValue.trim();
    setRenaming(null);
    if (!value) return;
    store.renameSession(session.id, value);
    void call('session.rename', { session_id: session.id, title: value });
  };

  return (
    <aside
      aria-label="Sessions"
      style={{ width }}
      className="relative flex shrink-0 flex-col border-e border-border-default bg-surface"
    >
      <div className="flex items-center gap-1 px-3 pt-3">
        <h2 className="flex-1 text-h3 font-semibold">Sessions</h2>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="New session"
          onClick={() => {
            const session = store.createSession();
            void navigate(`/chat/${session.id}`);
          }}
        >
          <MessageSquarePlus />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Collapse sidebar"
          onClick={toggleSidebar}
        >
          <PanelLeftClose className="rtl:rotate-180" />
        </Button>
      </div>
      <div className="relative px-3 py-2">
        <Search className="pointer-events-none absolute start-5 top-1/2 size-4 -translate-y-1/2 text-fg-muted" />
        <input
          type="search"
          value={store.searchQuery}
          onChange={(event) => store.setSearchQuery(event.target.value)}
          placeholder="Search sessions"
          aria-label="Search sessions"
          className="selectable h-8 w-full rounded-md border border-border-default bg-sunken ps-8 pe-2 text-body"
        />
      </div>
      <button
        type="button"
        onClick={() => store.setShowArchived(!store.showArchived)}
        className="mx-3 mb-1 flex items-center gap-1 text-caption text-fg-muted hover:text-fg-primary"
      >
        {store.showArchived ? (
          <ArchiveRestore className="size-3.5" />
        ) : (
          <Archive className="size-3.5" />
        )}
        {store.showArchived ? 'Back to active sessions' : 'View archive'}
      </button>
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {visible.length === 0 ? (
          <p className="px-2 py-6 text-center text-caption text-fg-muted">
            {store.sessions.length
              ? 'No sessions match this view.'
              : 'No sessions yet. Start one to begin.'}
          </p>
        ) : (
          <ul>
            {rows.map(({ session, group, showHeader }) => (
              <li key={session.id}>
                {showHeader && (
                  <p className="px-2 pb-1 pt-3 text-micro font-semibold uppercase text-fg-muted">
                    {group}
                  </p>
                )}
                {renaming === session.id ? (
                  <input
                    autoFocus
                    value={renameValue}
                    onChange={(event) => setRenameValue(event.target.value)}
                    onBlur={() => commitRename(session)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') commitRename(session);
                      if (event.key === 'Escape') setRenaming(null);
                    }}
                    className="selectable w-full rounded-md border border-accent bg-sunken px-2 py-1.5"
                  />
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      store.setActiveSession(session.id);
                      void navigate(`/chat/${session.id}`);
                    }}
                    onDoubleClick={() => {
                      setRenaming(session.id);
                      setRenameValue(session.title);
                    }}
                    onContextMenu={(event) => {
                      event.preventDefault();
                      setMenu({ session, x: event.clientX, y: event.clientY });
                    }}
                    className={cn(
                      'w-full rounded-md px-2 py-1.5 text-start hover:bg-surface-2',
                      session.id === store.activeSessionId && 'bg-accent-soft text-accent-text',
                    )}
                  >
                    <span className="block truncate">{session.title}</span>
                    <span className="flex gap-2 text-micro text-fg-muted">
                      <span>{session.modelName || session.modelProvider || 'Echo'}</span>
                      <span>{session.messageCount} messages</span>
                    </span>
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      {menu && (
        <div
          role="menu"
          onClick={(event) => event.stopPropagation()}
          style={{ left: menu.x, top: menu.y }}
          className="fixed z-50 min-w-44 rounded-md border border-border-default bg-overlay p-1 shadow-e2"
        >
          {[
            [
              'Rename',
              () => {
                setRenaming(menu.session.id);
                setRenameValue(menu.session.title);
              },
            ],
            [
              menu.session.isArchived ? 'Restore' : 'Archive',
              () => {
                store.archiveSession(menu.session.id, !menu.session.isArchived);
                void call('session.update', {
                  session_id: menu.session.id,
                  is_archived: !menu.session.isArchived,
                });
              },
            ],
            ['Export JSON', () => void exportSession(menu.session, 'json')],
            ['Export Markdown', () => void exportSession(menu.session, 'md')],
            ['Export HTML', () => void exportSession(menu.session, 'html')],
          ].map(([label, action]) => (
            <button
              key={String(label)}
              role="menuitem"
              type="button"
              onClick={() => {
                (action as () => void)();
                setMenu(null);
              }}
              className="block w-full rounded-sm px-2 py-1.5 text-start hover:bg-accent-soft"
            >
              {String(label)}
            </button>
          ))}
          <hr className="my-1 border-border-default" />
          <button
            role="menuitem"
            type="button"
            className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-danger-fg hover:bg-danger-bg"
            onClick={() => {
              if (window.confirm(`Delete “${menu.session.title}”? This cannot be undone.`)) {
                store.deleteSession(menu.session.id);
                clearConversation(menu.session.id);
                void call('session.delete', { session_id: menu.session.id });
                void navigate('/');
              }
              setMenu(null);
            }}
          >
            <Trash2 className="size-4" />
            Delete
          </button>
        </div>
      )}
      <div
        role="separator"
        aria-label="Resize sidebar"
        aria-orientation="vertical"
        aria-valuenow={width}
        aria-valuemin={SIDEBAR_MIN_WIDTH}
        aria-valuemax={SIDEBAR_MAX_WIDTH}
        tabIndex={0}
        onPointerDown={() => {
          dragging.current = true;
          document.body.style.cursor = 'col-resize';
        }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowLeft') setWidth(width - 16);
          if (event.key === 'ArrowRight') setWidth(width + 16);
        }}
        className="absolute inset-y-0 end-0 w-1.5 translate-x-1/2 cursor-col-resize hover:bg-accent/40"
      />
    </aside>
  );
}
