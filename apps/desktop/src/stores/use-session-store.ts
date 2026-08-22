/**
 * Conversation session state.
 *
 * The shell keeps only the session index and the active id. Message bodies and
 * streaming arrive over the Python bridge in P-02, so nothing here talks to a
 * backend yet.
 */

import { create } from 'zustand';

import type { Session } from '@/types';

interface SessionState {
  sessions: Session[];
  activeSessionId: string | null;
  searchQuery: string;

  /** Creates a session, makes it active, and returns it. */
  createSession: (title?: string) => Session;
  setActiveSession: (id: string | null) => void;
  mergeSessions: (sessions: Session[]) => void;
  renameSession: (id: string, title: string) => void;
  deleteSession: (id: string) => void;
  setSearchQuery: (query: string) => void;
  /** Sessions filtered by the current search query. */
  filteredSessions: () => Session[];
}

/** Generates a session id, preferring the platform UUID when available. */
function sessionId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export const useSessionStore = create<SessionState>()((set, get) => ({
  sessions: [],
  activeSessionId: null,
  searchQuery: '',

  createSession: (title) => {
    const now = Date.now();
    const session: Session = {
      id: sessionId(),
      // Presentation layers supply the locale-specific untitled label.
      title: title ?? '',
      createdAt: now,
      updatedAt: now,
      messageCount: 0,
    };
    set((state) => ({
      sessions: [session, ...state.sessions],
      activeSessionId: session.id,
    }));
    return session;
  },

  setActiveSession: (activeSessionId) => set({ activeSessionId }),

  mergeSessions: (incoming) =>
    set((state) => {
      const byId = new Map(incoming.map((session) => [session.id, session]));
      state.sessions.forEach((session) => {
        if (!byId.has(session.id)) byId.set(session.id, session);
      });
      return { sessions: [...byId.values()].sort((a, b) => b.updatedAt - a.updatedAt) };
    }),

  renameSession: (id, title) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === id ? { ...s, title, updatedAt: Date.now() } : s,
      ),
    })),

  deleteSession: (id) =>
    set((state) => ({
      sessions: state.sessions.filter((s) => s.id !== id),
      activeSessionId: state.activeSessionId === id ? null : state.activeSessionId,
    })),

  setSearchQuery: (searchQuery) => set({ searchQuery }),

  filteredSessions: () => {
    const { sessions, searchQuery } = get();
    const query = searchQuery.trim().toLowerCase();
    if (!query) return sessions;
    return sessions.filter((s) => s.title.toLowerCase().includes(query));
  },
}));
