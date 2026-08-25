/**
 * Research session state (P2).
 *
 * Manages the list of research sessions, the active session, streaming
 * buffers (bounded per the project performance rules), and derived
 * selectors. Per-session streaming state is isolated so one session's
 * trace never leaks into another.
 */

import { create } from 'zustand';

import type {
  ListSummary,
  ResearchEvent,
  SessionRecord,
  SessionSummary,
} from '@/lib/bridge/research-types';

/** Maximum trace events kept in memory per session (bounded buffer). */
const MAX_TRACE_EVENTS = 500;

/** Maximum output lines kept per step. */
const MAX_OUTPUT_LINES = 200;

/** Per-session streaming state. */
interface SessionStreamState {
  events: ResearchEvent[];
  cursor: number;
  heartbeatAt: number | null;
  isStale: boolean;
}

interface ResearchState {
  sessions: ListSummary[];
  activeSessionId: string | null;
  /** Full record for the active session (from research.get). */
  activeRecord: SessionRecord | null;
  /** Latest summary for the active session. */
  activeSummary: SessionSummary | null;
  /** Per-session streaming state, keyed by session_id. */
  streams: Record<string, SessionStreamState>;
  /** UI view mode for the active session. */
  view: 'list' | 'composer' | 'plan' | 'trace' | 'report';
  /** Whether the trace inspector panel is open. */
  traceInspectorOpen: boolean;
  /** Filter for the trace inspector. */
  traceFilter: {
    event: string | null;
  };

  // Actions
  setSessions: (sessions: ListSummary[]) => void;
  upsertSession: (summary: SessionSummary) => void;
  setActiveSession: (sessionId: string | null) => void;
  setActiveRecord: (record: SessionRecord | null) => void;
  setActiveSummary: (summary: SessionSummary | null) => void;
  setView: (view: ResearchState['view']) => void;
  setTraceInspectorOpen: (open: boolean) => void;
  setTraceFilter: (filter: Partial<ResearchState['traceFilter']>) => void;

  // Streaming actions
  initStream: (sessionId: string) => void;
  pushEvent: (sessionId: string, event: ResearchEvent, cursor: number) => void;
  markStale: (sessionId: string, stale: boolean) => void;
  clearStream: (sessionId: string) => void;

  // Selectors
  activeStream: () => SessionStreamState | null;
  filteredEvents: () => ResearchEvent[];
}

function emptyStreamState(): SessionStreamState {
  return {
    events: [],
    cursor: 0,
    heartbeatAt: null,
    isStale: false,
  };
}

export const useResearchStore = create<ResearchState>()((set, get) => ({
  sessions: [],
  activeSessionId: null,
  activeRecord: null,
  activeSummary: null,
  streams: {},
  view: 'list',
  traceInspectorOpen: false,
  traceFilter: { event: null },

  setSessions: (sessions) => set({ sessions }),

  upsertSession: (summary) =>
    set((state) => {
      const listSummary: ListSummary = {
        session_id: summary.session_id,
        topic: summary.topic,
        status: summary.status,
        sections: summary.sections_total,
        created_at: 0,
        updated_at: 0,
        published: summary.published,
        report: summary.report.markdown_path,
      };
      const index = state.sessions.findIndex((s) => s.session_id === summary.session_id);
      const sessions =
        index >= 0
          ? state.sessions.map((s, i) => (i === index ? { ...s, ...listSummary } : s))
          : [listSummary, ...state.sessions];
      return { sessions };
    }),

  setActiveSession: (activeSessionId) =>
    set({ activeSessionId, activeRecord: null, activeSummary: null }),

  setActiveRecord: (activeRecord) => set({ activeRecord }),

  setActiveSummary: (activeSummary) => set({ activeSummary }),

  setView: (view) => set({ view }),

  setTraceInspectorOpen: (traceInspectorOpen) => set({ traceInspectorOpen }),

  setTraceFilter: (filter) =>
    set((state) => ({ traceFilter: { ...state.traceFilter, ...filter } })),

  initStream: (sessionId) =>
    set((state) => ({
      streams: {
        ...state.streams,
        [sessionId]: emptyStreamState(),
      },
    })),

  pushEvent: (sessionId, event, cursor) =>
    set((state) => {
      const existing = state.streams[sessionId] ?? emptyStreamState();
      const events = [...existing.events, event];
      const trimmed = events.length > MAX_TRACE_EVENTS ? events.slice(-MAX_TRACE_EVENTS) : events;
      return {
        streams: {
          ...state.streams,
          [sessionId]: {
            ...existing,
            events: trimmed,
            cursor,
            heartbeatAt: Date.now(),
            isStale: false,
          },
        },
      };
    }),

  markStale: (sessionId, stale) =>
    set((state) => {
      const existing = state.streams[sessionId] ?? emptyStreamState();
      return {
        streams: {
          ...state.streams,
          [sessionId]: { ...existing, isStale: stale },
        },
      };
    }),

  clearStream: (sessionId) =>
    set((state) => {
      const rest = { ...state.streams };
      delete rest[sessionId];
      return { streams: rest };
    }),

  activeStream: () => {
    const { streams, activeSessionId } = get();
    return activeSessionId ? (streams[activeSessionId] ?? null) : null;
  },

  filteredEvents: () => {
    const stream = get().activeStream();
    if (!stream) return [];
    const { traceFilter } = get();
    return stream.events.filter((event) => {
      if (traceFilter.event && event.event !== traceFilter.event) return false;
      return true;
    });
  },
}));

/** Truncate an output string to a bounded number of lines. */
export function truncateOutput(output: string, maxLines = MAX_OUTPUT_LINES): string {
  const lines = output.split('\n');
  if (lines.length <= maxLines) return output;
  return lines.slice(0, maxLines).join('\n') + `\n… (${lines.length - maxLines} more lines)`;
}
