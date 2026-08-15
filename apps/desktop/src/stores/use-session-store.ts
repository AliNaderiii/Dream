import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import type { Session } from '@/types';

interface SessionState {
  sessions: Session[];
  activeSessionId: string | null;
  searchQuery: string;
  showArchived: boolean;
  createSession: (title?: string) => Session;
  setActiveSession: (id: string | null) => void;
  renameSession: (id: string, title: string) => void;
  deleteSession: (id: string) => void;
  archiveSession: (id: string, archived?: boolean) => void;
  recordMessages: (id: string, count: number) => void;
  setSessions: (sessions: Session[]) => void;
  setShowArchived: (show: boolean) => void;
  setSearchQuery: (query: string) => void;
  filteredSessions: () => Session[];
}

function sessionId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export const useSessionStore = create<SessionState>()(
  persist(
    (set, get) => ({
      sessions: [],
      activeSessionId: null,
      searchQuery: '',
      showArchived: false,
      createSession: (title) => {
        const now = Date.now();
        const session: Session = {
          id: sessionId(),
          title: title ?? 'New session',
          createdAt: now,
          updatedAt: now,
          messageCount: 0,
          modelProvider: 'echo',
          isArchived: false,
        };
        set((state) => ({ sessions: [session, ...state.sessions], activeSessionId: session.id }));
        return session;
      },
      setActiveSession: (activeSessionId) => set({ activeSessionId }),
      renameSession: (id, title) => {
        const clean = title.trim();
        if (!clean) return;
        set((state) => ({
          sessions: state.sessions.map((session) =>
            session.id === id ? { ...session, title: clean, updatedAt: Date.now() } : session,
          ),
        }));
      },
      deleteSession: (id) =>
        set((state) => ({
          sessions: state.sessions.filter((session) => session.id !== id),
          activeSessionId: state.activeSessionId === id ? null : state.activeSessionId,
        })),
      archiveSession: (id, archived = true) =>
        set((state) => ({
          sessions: state.sessions.map((session) =>
            session.id === id
              ? { ...session, isArchived: archived, updatedAt: Date.now() }
              : session,
          ),
          activeSessionId: state.activeSessionId === id && archived ? null : state.activeSessionId,
        })),
      recordMessages: (id, count) =>
        set((state) => ({
          sessions: state.sessions.map((session) =>
            session.id === id
              ? {
                  ...session,
                  messageCount: session.messageCount + count,
                  updatedAt: Date.now(),
                }
              : session,
          ),
        })),
      setSessions: (sessions) =>
        set({ sessions: [...sessions].sort((a, b) => b.updatedAt - a.updatedAt) }),
      setShowArchived: (showArchived) => set({ showArchived }),
      setSearchQuery: (searchQuery) => set({ searchQuery }),
      filteredSessions: () => {
        const { sessions, searchQuery, showArchived } = get();
        const query = searchQuery.trim().toLowerCase();
        return sessions.filter(
          (session) =>
            Boolean(session.isArchived) === showArchived &&
            (!query || session.title.toLowerCase().includes(query)),
        );
      },
    }),
    {
      name: 'dream-sessions-v1',
      partialize: (state) => ({ sessions: state.sessions, activeSessionId: state.activeSessionId }),
    },
  ),
);
