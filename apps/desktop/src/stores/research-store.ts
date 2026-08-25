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
  ResearchProgressEvent,
  ResearchSession,
  ResearchStep,
} from '@/lib/bridge/research-types';

/** Maximum trace events kept in memory per session (bounded buffer). */
const MAX_TRACE_EVENTS = 500;

/** Maximum output lines kept per step. */
const MAX_OUTPUT_LINES = 200;

/** Per-session streaming state. */
interface SessionStreamState {
  steps: ResearchStep[];
  events: ResearchProgressEvent[];
  currentStepId: string | null;
  heartbeatAt: number | null;
  /** True when the sidecar hasn't sent a heartbeat within the threshold. */
  isStale: boolean;
}

interface ResearchState {
  sessions: ResearchSession[];
  activeSessionId: string | null;
  /** Per-session streaming state, keyed by session_id. */
  streams: Record<string, SessionStreamState>;
  /** UI view mode for the active session. */
  view: 'list' | 'composer' | 'plan' | 'trace' | 'report';
  /** Whether the trace inspector panel is open. */
  traceInspectorOpen: boolean;
  /** Filter for the trace inspector. */
  traceFilter: {
    phase: string | null;
    status: string | null;
    tool: string | null;
  };

  // Actions
  setSessions: (sessions: ResearchSession[]) => void;
  upsertSession: (session: ResearchSession) => void;
  setActiveSession: (sessionId: string | null) => void;
  setView: (view: ResearchState['view']) => void;
  setTraceInspectorOpen: (open: boolean) => void;
  setTraceFilter: (filter: Partial<ResearchState['traceFilter']>) => void;

  // Streaming actions
  initStream: (sessionId: string) => void;
  pushEvent: (sessionId: string, event: ResearchProgressEvent) => void;
  updateSteps: (sessionId: string, steps: ResearchStep[]) => void;
  markStale: (sessionId: string, stale: boolean) => void;
  clearStream: (sessionId: string) => void;

  // Selectors
  activeSession: () => ResearchSession | null;
  activeStream: () => SessionStreamState | null;
  filteredSteps: () => ResearchStep[];
}

function emptyStreamState(): SessionStreamState {
  return {
    steps: [],
    events: [],
    currentStepId: null,
    heartbeatAt: null,
    isStale: false,
  };
}

export const useResearchStore = create<ResearchState>()((set, get) => ({
  sessions: [],
  activeSessionId: null,
  streams: {},
  view: 'list',
  traceInspectorOpen: false,
  traceFilter: { phase: null, status: null, tool: null },

  setSessions: (sessions) => set({ sessions }),

  upsertSession: (session) =>
    set((state) => {
      const index = state.sessions.findIndex((s) => s.session_id === session.session_id);
      const sessions =
        index >= 0
          ? state.sessions.map((s, i) => (i === index ? session : s))
          : [session, ...state.sessions];
      return { sessions };
    }),

  setActiveSession: (activeSessionId) => set({ activeSessionId }),

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

  pushEvent: (sessionId, event) =>
    set((state) => {
      const existing = state.streams[sessionId] ?? emptyStreamState();
      const events = [...existing.events, event];
      // Bounded buffer: keep only the last MAX_TRACE_EVENTS
      const trimmed = events.length > MAX_TRACE_EVENTS ? events.slice(-MAX_TRACE_EVENTS) : events;

      let currentStepId = existing.currentStepId;
      let heartbeatAt = existing.heartbeatAt;

      if (event.event_type === 'step_started' && event.step) {
        currentStepId = event.step.step_id;
      }
      if (event.event_type === 'heartbeat') {
        heartbeatAt = Date.now();
      }

      return {
        streams: {
          ...state.streams,
          [sessionId]: {
            ...existing,
            events: trimmed,
            currentStepId,
            heartbeatAt,
            isStale: false,
          },
        },
      };
    }),

  updateSteps: (sessionId, steps) =>
    set((state) => {
      const existing = state.streams[sessionId] ?? emptyStreamState();
      return {
        streams: {
          ...state.streams,
          [sessionId]: { ...existing, steps },
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

  activeSession: () => {
    const { sessions, activeSessionId } = get();
    return sessions.find((s) => s.session_id === activeSessionId) ?? null;
  },

  activeStream: () => {
    const { streams, activeSessionId } = get();
    return activeSessionId ? (streams[activeSessionId] ?? null) : null;
  },

  filteredSteps: () => {
    const stream = get().activeStream();
    if (!stream) return [];
    const { traceFilter } = get();
    return stream.steps.filter((step) => {
      if (traceFilter.phase && step.phase !== traceFilter.phase) return false;
      if (traceFilter.status && step.status !== traceFilter.status) return false;
      if (traceFilter.tool && !step.tool_calls?.some((tc) => tc.tool_name === traceFilter.tool)) {
        return false;
      }
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
